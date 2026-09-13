import re
import sqlite3
import unicodedata

import requests
from bs4 import BeautifulSoup
from flask import flash, redirect, render_template, url_for

from app import candidate_key, extract_city

MIYAGI_DETAIL_URL = "https://www.pref.miyagi.jp/site/miyagiminpaku/list.html"
MIYAGI_DETAIL_SOURCE = "宮城県公式 民泊届出施設紹介"
MAX_HTML_BYTES = 3 * 1024 * 1024
CORPORATE_WORDS = ("株式会社", "有限会社", "合同会社", "一般社団法人", "一般財団法人", "NPO法人", "特定非営利活動法人")


def _clean(value):
    text = unicodedata.normalize("NFKC", value or "").strip()
    return "" if text in {"", "-", "ー", "―"} else text


def normalize_match_address(value):
    text = unicodedata.normalize("NFKC", value or "").strip()
    text = re.sub(r"〒?\s*\d{3}-?\d{4}", "", text)
    text = text.replace("宮城県", "")
    text = re.sub(r"[\s\u3000]+", "", text)
    text = re.sub(r"[‐‑‒–—―ー−﹣－]+", "-", text)
    return text.lower().strip("-,")


def parse_miyagi_detail_html(html):
    soup = BeautifulSoup(html, "html.parser")
    records = []
    for row in soup.select("table tr"):
        cells = row.find_all("td")
        if len(cells) < 8:
            continue
        name = _clean(cells[2].get_text(" ", strip=True))
        operator = _clean(cells[3].get_text(" ", strip=True))
        address = _clean(cells[4].get_text(" ", strip=True))
        phone = _clean(cells[5].get_text(" ", strip=True))
        if not address:
            continue

        email = ""
        for link in cells[6].find_all("a", href=True):
            href = link.get("href", "")
            if href.lower().startswith("mailto:"):
                email = href.split(":", 1)[1].split("?", 1)[0].strip()
                break

        official_url = ""
        for link in cells[7].find_all("a", href=True):
            href = link.get("href", "").strip()
            if href.startswith(("http://", "https://")):
                official_url = href
                break

        records.append({
            "name": name,
            "operator": operator,
            "address": address,
            "phone": phone,
            "email": email,
            "official_url": official_url,
        })
    return records


def fetch_miyagi_detail_records(url=MIYAGI_DETAIL_URL):
    response = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0 TohokuLodgingSalesAI/1.0",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ja,en;q=0.7",
        },
    )
    response.raise_for_status()
    if len(response.content) > MAX_HTML_BYTES:
        raise ValueError("宮城県の施設紹介ページが想定サイズを超えています。")
    records = parse_miyagi_detail_html(response.text)
    if not records:
        raise ValueError("宮城県の施設紹介ページから施設情報を抽出できませんでした。")
    return records


def _record_index(records):
    index = {}
    for record in records:
        key = normalize_match_address(record["address"])
        if key:
            index.setdefault(key, record)
    return index


def _find_record(address, index):
    key = normalize_match_address(address)
    if not key:
        return None
    if key in index:
        return index[key]
    if len(key) >= 12:
        candidates = [record for record_key, record in index.items() if key in record_key or record_key in key]
        if len(candidates) == 1:
            return candidates[0]
    return None


def _company_name(operator):
    return operator if operator and any(word in operator for word in CORPORATE_WORDS) else ""


def import_miyagi_official_records(database, records, source_url=MIYAGI_DETAIL_URL):
    """Create or enrich candidates directly from Miyagi's official minpaku facility table."""
    inserted = updated = duplicates = 0
    with sqlite3.connect(database) as con:
        con.row_factory = sqlite3.Row
        for record in records:
            address = record.get("address", "").strip()
            if not address:
                continue
            city = extract_city(address)
            key = candidate_key("宮城県", city, address)
            existing = con.execute(
                "SELECT * FROM lead_candidates WHERE normalized_key=?", (key,)
            ).fetchone()
            company = _company_name(record.get("operator", ""))
            note = "[宮城県公式民泊一覧] 公開施設情報から自動取込"
            if record.get("operator"):
                note += f" / 届出者: {record['operator']}"
            note += f" / 出典: {source_url}"

            if existing:
                duplicates += 1
                changes = {}
                for column, value in (
                    ("name", record.get("name", "")),
                    ("company_name", company),
                    ("phone", record.get("phone", "")),
                    ("email", record.get("email", "")),
                    ("official_url", record.get("official_url", "")),
                ):
                    if value and not existing[column]:
                        changes[column] = value
                current_notes = existing["research_notes"] or ""
                if note not in current_notes:
                    changes["research_notes"] = (current_notes + "\n" + note).strip()
                if existing["research_status"] == "unresearched":
                    changes["research_status"] = "researching"
                if changes:
                    assignments = ", ".join(f"{column}=?" for column in changes)
                    con.execute(
                        f"UPDATE lead_candidates SET {assignments}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        [*changes.values(), existing["id"]],
                    )
                    updated += 1
                continue

            con.execute(
                """INSERT INTO lead_candidates
                (name,company_name,prefecture,city,address,official_url,phone,email,contact_url,
                 source_url,source_type,normalized_key,status,research_status,research_notes)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'pending','researching',?)""",
                (
                    record.get("name", ""), company, "宮城県", city, address,
                    record.get("official_url", ""), record.get("phone", ""), record.get("email", ""), "",
                    source_url, MIYAGI_DETAIL_SOURCE, key, note,
                ),
            )
            inserted += 1
    return {"source_records": len(records), "inserted": inserted, "updated": updated, "duplicates": duplicates}


def enrich_pending_candidates(database, records, source_url=MIYAGI_DETAIL_URL):
    index = _record_index(records)
    matched = 0
    changed = 0
    with sqlite3.connect(database) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT * FROM lead_candidates
               WHERE status='pending' AND prefecture='宮城県'"""
        ).fetchall()
        for candidate in rows:
            record = _find_record(candidate["address"], index)
            if not record:
                continue
            matched += 1
            updates = {}
            if not candidate["name"] and record["name"]:
                updates["name"] = record["name"]
            if not candidate["phone"] and record["phone"]:
                updates["phone"] = record["phone"]
            if not candidate["email"] and record["email"]:
                updates["email"] = record["email"]
            if not candidate["official_url"] and record["official_url"]:
                updates["official_url"] = record["official_url"]
            if not candidate["company_name"] and record["operator"] and any(word in record["operator"] for word in CORPORATE_WORDS):
                updates["company_name"] = record["operator"]

            note_bits = ["[宮城県公式HTML自動照合] 施設紹介ページで住所一致"]
            if record["operator"]:
                note_bits.append(f"届出者: {record['operator']}")
            note_bits.append(f"出典: {source_url}")
            new_note = " / ".join(note_bits)
            current_notes = candidate["research_notes"] or ""
            if new_note not in current_notes:
                updates["research_notes"] = (current_notes + "\n" + new_note).strip()
            if candidate["research_status"] == "unresearched":
                updates["research_status"] = "researching"

            if updates:
                assignments = ", ".join(f"{column}=?" for column in updates)
                con.execute(
                    f"UPDATE lead_candidates SET {assignments}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    [*updates.values(), candidate["id"]],
                )
                changed += 1
    return {"matched": matched, "changed": changed, "source_records": len(records)}


def register_miyagi_enrichment(app):
    if "enrich_miyagi_candidates" in app.view_functions:
        return app

    @app.get("/enrichment", endpoint="enrichment_page")
    def enrichment_page():
        return render_template("enrichment.html", source_url=MIYAGI_DETAIL_URL)

    @app.post("/targets/import-miyagi", endpoint="import_miyagi_targets")
    def import_miyagi_targets():
        try:
            records = fetch_miyagi_detail_records()
            stats = import_miyagi_official_records(app.config["DATABASE"], records)
            flash(
                f"宮城県公式民泊一覧 {stats['source_records']}件を確認。新規{stats['inserted']}件、既存更新{stats['updated']}件です。",
                "success",
            )
        except (requests.RequestException, ValueError, OSError) as exc:
            app.logger.warning("Miyagi official import failed: %s", exc)
            flash("宮城県公式民泊一覧を取得できませんでした。時間を置いて再度お試しください。", "error")
        return redirect("/targets?prefecture=宮城県")

    @app.post("/candidates/enrich-miyagi", endpoint="enrich_miyagi_candidates")
    def enrich_miyagi_candidates():
        try:
            records = fetch_miyagi_detail_records()
            stats = enrich_pending_candidates(app.config["DATABASE"], records)
            flash(
                f"宮城県公式ページ {stats['source_records']}件を確認し、住所一致{stats['matched']}件・更新{stats['changed']}件でした。",
                "success",
            )
        except (requests.RequestException, ValueError, OSError) as exc:
            app.logger.warning("Miyagi HTML enrichment failed: %s", exc)
            flash("宮城県の施設紹介ページを取得できませんでした。時間を置いて再度お試しください。", "error")
        return redirect(url_for("candidates", status="pending"))

    return app
