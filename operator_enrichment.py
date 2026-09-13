import json
import re
import sqlite3
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import flash, redirect, render_template

from auto_discovery import CORPORATE_WORDS, SOURCE_TYPE, _clean, _robots_allowed, _safe_get, _safe_url
from sales_priority import score_candidate

OPERATOR_PAGE_RE = re.compile(
    r"会社概要|運営会社|運営者|企業情報|法人情報|about|company|corporate|operator|profile|特定商取引|事業者情報",
    re.I,
)


def _company_candidates(text):
    text = _clean(text)
    patterns = [
        r"(?:運営会社|運営者|会社名|法人名|事業者名|販売事業者)\s*[:：]?\s*([^|｜/／<>]{2,80})",
        r"((?:株式会社|合同会社|有限会社|一般社団法人|一般財団法人)[^|｜/／<>\n]{1,60})",
        r"([^|｜/／<>\n]{1,60}(?:株式会社|合同会社|有限会社))",
    ]
    found = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            value = _clean(match.group(1))
            value = re.split(r"\s{2,}|(?:電話|TEL|住所|所在地|代表|メール|E-mail|Email)", value)[0].strip(" -:：|｜")
            if 2 <= len(value) <= 80 and any(word in value for word in CORPORATE_WORDS):
                if value not in found:
                    found.append(value)
    return found


def extract_operator_evidence(html, base_url, facility_name=""):
    soup = BeautifulSoup(html, "html.parser")
    result = {"company_name": "", "phone": "", "email": "", "contact_url": "", "evidence": []}

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (TypeError, json.JSONDecodeError):
            continue
        queue = data if isinstance(data, list) else [data]
        for obj in queue:
            if not isinstance(obj, dict):
                continue
            for key in ("parentOrganization", "provider", "brand", "seller", "publisher", "organizer"):
                org = obj.get(key)
                if isinstance(org, dict):
                    name = _clean(org.get("name", ""))
                    if name and name != facility_name and any(word in name for word in CORPORATE_WORDS):
                        result["company_name"] = name
                        result["evidence"].append(f"JSON-LD {key}")
                        break
                elif isinstance(org, str):
                    name = _clean(org)
                    if name and name != facility_name and any(word in name for word in CORPORATE_WORDS):
                        result["company_name"] = name
                        result["evidence"].append(f"JSON-LD {key}")
                        break
            if result["company_name"]:
                break
        if result["company_name"]:
            break

    text = soup.get_text("\n")
    if not result["company_name"]:
        candidates = _company_candidates(text)
        if candidates:
            result["company_name"] = candidates[0]
            result["evidence"].append("ページ本文の法人名表記")

    if not result["company_name"]:
        footer = soup.find("footer")
        footer_text = footer.get_text(" ") if footer else ""
        candidates = _company_candidates(footer_text)
        if candidates:
            result["company_name"] = candidates[0]
            result["evidence"].append("フッター法人名表記")

    for tag in soup.select('a[href^="mailto:"]'):
        value = tag.get("href", "")[7:].split("?")[0].strip()
        if value:
            result["email"] = value
            result["evidence"].append("メールリンク")
            break
    for tag in soup.select('a[href^="tel:"]'):
        value = tag.get("href", "")[4:].strip()
        if value:
            result["phone"] = value
            result["evidence"].append("電話リンク")
            break
    for tag in soup.find_all("a", href=True):
        label = _clean(tag.get_text(" "))
        href = tag.get("href", "")
        if re.search(r"お問い合わせ|問い合わせ|お問合せ|contact|inquiry", label + " " + href, re.I):
            result["contact_url"] = urljoin(base_url, href)
            result["evidence"].append("問い合わせ導線")
            break
    return result


def discover_operator_pages(html, base_url, max_pages=3):
    soup = BeautifulSoup(html, "html.parser")
    base = urlparse(base_url)
    pages = []
    for tag in soup.find_all("a", href=True):
        label = _clean(tag.get_text(" "))
        href = tag.get("href", "")
        if not OPERATOR_PAGE_RE.search(label + " " + href):
            continue
        url = urljoin(base_url, href)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != base.netloc:
            continue
        if url not in pages:
            pages.append(url)
        if len(pages) >= max_pages:
            break
    return pages


def research_operator(candidate):
    root = candidate["official_url"]
    if not root or not _safe_url(root) or not _robots_allowed(root):
        return None, "公式URLの安全性またはrobots.txtによりスキップ"

    response, final_url = _safe_get(root)
    pages = [(final_url, response.text)]
    for url in discover_operator_pages(response.text, final_url):
        if not _safe_url(url) or not _robots_allowed(url):
            continue
        try:
            page_response, page_final = _safe_get(url)
        except (requests.RequestException, ValueError, OSError):
            continue
        pages.append((page_final, page_response.text))

    merged = {"company_name": "", "phone": "", "email": "", "contact_url": "", "evidence": [], "pages": []}
    for url, html in pages:
        extracted = extract_operator_evidence(html, url, candidate["name"] or "")
        merged["pages"].append(url)
        for field in ("company_name", "phone", "email", "contact_url"):
            if not merged[field] and extracted[field]:
                merged[field] = extracted[field]
        merged["evidence"].extend(extracted["evidence"])
    merged["evidence"] = list(dict.fromkeys(merged["evidence"]))
    return merged, "調査完了"


def operator_batch(database, limit=10):
    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """SELECT * FROM lead_candidates
               WHERE status='pending' AND official_url<>''
                 AND (company_name='' OR phone='' OR email='' OR contact_url='')
               ORDER BY CASE source_type WHEN ? THEN 0 ELSE 1 END, updated_at DESC, id DESC
               LIMIT ?""",
            (SOURCE_TYPE, limit),
        ).fetchall()
    finally:
        con.close()

    stats = {"checked": 0, "updated": 0, "company_found": 0, "contact_found": 0, "failed": 0}
    for row in rows:
        stats["checked"] += 1
        try:
            result, _ = research_operator(row)
            if not result:
                continue
            changes = {}
            if not row["company_name"] and result["company_name"]:
                changes["company_name"] = result["company_name"]
                stats["company_found"] += 1
            contact_before = bool(row["phone"] or row["email"] or row["contact_url"])
            for field in ("phone", "email", "contact_url"):
                if not row[field] and result[field]:
                    changes[field] = result[field]
            contact_after = contact_before or any(result[field] for field in ("phone", "email", "contact_url"))
            if contact_after and not contact_before:
                stats["contact_found"] += 1
            evidence = "、".join(result["evidence"]) or "追加根拠なし"
            page_list = " / ".join(result["pages"][:4])
            note = f"[運営会社自動調査] 根拠: {evidence} / 確認ページ: {page_list}"
            changes["research_notes"] = ((row["research_notes"] or "") + "\n" + note).strip()
            changes["research_status"] = "researching"
            if changes:
                set_sql = ", ".join(f"{key}=?" for key in changes)
                with sqlite3.connect(database) as write_con:
                    write_con.execute(
                        f"UPDATE lead_candidates SET {set_sql}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        list(changes.values()) + [row["id"]],
                    )
                stats["updated"] += 1
        except (requests.RequestException, ValueError, OSError):
            stats["failed"] += 1
    return stats


def ready_candidates(database, limit=20):
    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT * FROM lead_candidates WHERE status='pending' ORDER BY updated_at DESC, id DESC").fetchall()
    finally:
        con.close()
    ranked = []
    for row in rows:
        scored = score_candidate(row)
        if scored["band"] in {"S", "A"}:
            ranked.append({"candidate": row, **scored})
    ranked.sort(key=lambda item: ({"S": 0, "A": 1}[item["band"]], -item["score"], item["candidate"]["id"]))
    return ranked[:limit]


def register_operator_enrichment(app):
    @app.get("/operator-enrichment")
    def operator_enrichment():
        con = sqlite3.connect(app.config["DATABASE"])
        try:
            unresolved = con.execute(
                "SELECT COUNT(*) FROM lead_candidates WHERE status='pending' AND official_url<>'' AND company_name=''"
            ).fetchone()[0]
            reachable_missing = con.execute(
                "SELECT COUNT(*) FROM lead_candidates WHERE status='pending' AND official_url<>'' AND phone='' AND email='' AND contact_url=''"
            ).fetchone()[0]
        finally:
            con.close()
        return render_template(
            "operator_enrichment.html",
            unresolved=unresolved,
            reachable_missing=reachable_missing,
            ready=ready_candidates(app.config["DATABASE"]),
        )

    @app.post("/operator-enrichment/run")
    def operator_enrichment_run():
        stats = operator_batch(app.config["DATABASE"], limit=10)
        flash(
            f"運営会社自動調査: {stats['checked']}件確認 / {stats['updated']}件更新 / 会社名{stats['company_found']}件 / 新規連絡先{stats['contact_found']}件 / 失敗{stats['failed']}件。",
            "success" if stats["updated"] else "info",
        )
        return redirect("/operator-enrichment")

    return app
