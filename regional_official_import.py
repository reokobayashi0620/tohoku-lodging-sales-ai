import re
import sqlite3
import unicodedata

import requests
from bs4 import BeautifulSoup
from flask import flash, redirect

from app import candidate_key, download_pdf, extract_city, pdf_text

YAMAGATA_PAGE_URL = "https://www.pref.yamagata.jp/020071/kenfuku/doubutsuaigo/eisei/seikatsueisei/minpaku/minpaku.html"
YAMAGATA_SOURCE_TYPE = "山形県公式 住宅宿泊事業者一覧"
FUKUSHIMA_LIST_URL = "https://www.pref.fukushima.lg.jp/sec/32031a/minpaku-04.html"
FUKUSHIMA_SOURCE_TYPE = "福島県公式 住宅宿泊事業法受理済み届出住宅一覧"
CORPORATE_WORDS = ("株式会社", "有限会社", "合同会社", "一般社団法人", "一般財団法人", "（株）", "(株)", "（有）", "(有)")


def _clean(value):
    return unicodedata.normalize("NFKC", value or "").strip()


def _latest_yamagata_pdf(page_url=YAMAGATA_PAGE_URL):
    response = requests.get(page_url, timeout=20, headers={"User-Agent": "Mozilla/5.0 TohokuLodgingSalesAI/1.0", "Accept-Language": "ja,en;q=0.7"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    matches = []
    for anchor in soup.find_all("a", href=True):
        label = _clean(anchor.get_text(" ", strip=True))
        href = anchor.get("href", "")
        if "住宅宿泊事業者一覧" not in label or ".pdf" not in href.lower():
            continue
        matches.append(requests.compat.urljoin(page_url, href))
    if not matches:
        raise ValueError("山形県公式ページから住宅宿泊事業者一覧PDFを特定できませんでした。")
    return matches[-1]


def parse_yamagata_pdf(pdf_bytes):
    text = pdf_text(pdf_bytes)
    records = []
    seen = set()
    for raw_line in text.splitlines():
        line = _clean(raw_line)
        match = re.match(r"^\s*\d+\s+(.+)$", line)
        if not match:
            continue
        address = match.group(1).strip()
        if not re.search(r"[市町村]", address):
            continue
        key = address.lower()
        if key in seen:
            continue
        seen.add(key)
        records.append({"name": "", "operator": "", "address": address, "phone": ""})
    return records


def fetch_yamagata_records(page_url=YAMAGATA_PAGE_URL):
    pdf_url = _latest_yamagata_pdf(page_url)
    records = parse_yamagata_pdf(download_pdf(pdf_url))
    if not records:
        raise ValueError("山形県公式PDFから所在地を抽出できませんでした。")
    return records, pdf_url


def parse_fukushima_html(html):
    soup = BeautifulSoup(html, "html.parser")
    records = []
    seen = set()
    for row in soup.select("table tr"):
        cells = [_clean(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
        if len(cells) < 3:
            continue
        company, name, address = cells[:3]
        phone = cells[3] if len(cells) > 3 else ""
        if not address or not re.search(r"[市町村]", address):
            continue
        key = address.lower()
        if key in seen:
            continue
        seen.add(key)
        records.append({"name": name, "operator": company, "address": address, "phone": phone})
    return records


def fetch_fukushima_records(url=FUKUSHIMA_LIST_URL):
    response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 TohokuLodgingSalesAI/1.0", "Accept-Language": "ja,en;q=0.7"})
    response.raise_for_status()
    records = parse_fukushima_html(response.text)
    if not records:
        raise ValueError("福島県公式一覧から施設情報を抽出できませんでした。")
    return records


def _company(operator):
    return operator if operator and any(word in operator for word in CORPORATE_WORDS) else ""


def import_official_records(database, prefecture, records, source_url, source_type):
    inserted = updated = duplicates = 0
    with sqlite3.connect(database) as con:
        con.row_factory = sqlite3.Row
        for record in records:
            address = _clean(record.get("address"))
            if not address:
                continue
            city = extract_city(address)
            key = candidate_key(prefecture, city, address)
            existing = con.execute("SELECT * FROM lead_candidates WHERE normalized_key=?", (key,)).fetchone()
            company = _company(_clean(record.get("operator")))
            name = _clean(record.get("name"))
            phone = _clean(record.get("phone"))
            note = f"[{source_type}] 公式公開情報から自動取込 / 出典: {source_url}"
            if existing:
                duplicates += 1
                changes = {}
                for column, value in (("name", name), ("company_name", company), ("phone", phone)):
                    if value and not existing[column]:
                        changes[column] = value
                current_notes = existing["research_notes"] or ""
                if note not in current_notes:
                    changes["research_notes"] = (current_notes + "\n" + note).strip()
                if changes:
                    assignments = ", ".join(f"{column}=?" for column in changes)
                    con.execute(f"UPDATE lead_candidates SET {assignments}, updated_at=CURRENT_TIMESTAMP WHERE id=?", [*changes.values(), existing["id"]])
                    updated += 1
                continue
            con.execute("""INSERT INTO lead_candidates
                (name,company_name,prefecture,city,address,official_url,phone,email,contact_url,source_url,source_type,normalized_key,status,research_status,research_notes)
                VALUES (?,?,?,?,?,'',?,'','',?,?,?,'pending','unresearched',?)""",
                (name, company, prefecture, city, address, phone, source_url, source_type, key, note))
            inserted += 1
    return {"source_records": len(records), "inserted": inserted, "updated": updated, "duplicates": duplicates}


def register_regional_official_import(app):
    @app.post("/targets/import-yamagata", endpoint="import_yamagata_targets")
    def import_yamagata_targets():
        try:
            records, source_url = fetch_yamagata_records()
            stats = import_official_records(app.config["DATABASE"], "山形県", records, source_url, YAMAGATA_SOURCE_TYPE)
            flash(f"山形県公式民泊一覧 {stats['source_records']}件を確認。新規{stats['inserted']}件、既存更新{stats['updated']}件です。", "success")
        except (requests.RequestException, ValueError, OSError) as exc:
            app.logger.warning("Yamagata official import failed: %s", exc)
            flash("山形県公式民泊一覧を取得できませんでした。時間を置いて再度お試しください。", "error")
        return redirect("/targets?prefecture=山形県")

    @app.post("/targets/import-fukushima", endpoint="import_fukushima_targets")
    def import_fukushima_targets():
        try:
            records = fetch_fukushima_records()
            stats = import_official_records(app.config["DATABASE"], "福島県", records, FUKUSHIMA_LIST_URL, FUKUSHIMA_SOURCE_TYPE)
            flash(f"福島県公式民泊一覧 {stats['source_records']}件を確認。新規{stats['inserted']}件、既存更新{stats['updated']}件です。", "success")
        except (requests.RequestException, ValueError, OSError) as exc:
            app.logger.warning("Fukushima official import failed: %s", exc)
            flash("福島県公式民泊一覧を取得できませんでした。時間を置いて再度お試しください。", "error")
        return redirect("/targets?prefecture=福島県")

    return app
