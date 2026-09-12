import re
import sqlite3
import unicodedata
from io import BytesIO
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from flask import flash, redirect, render_template, request, url_for
from pypdf import PdfReader

SOURCES = {
    "aomori": {
        "prefecture": "青森県",
        "title": "住宅宿泊事業法届出住宅一覧",
        "url": "https://opendata.pref.aomori.lg.jp/dataset/2047.html",
        "format": "XLSX（オープンデータ）",
        "mode": "source_only",
        "note": "公式オープンデータ。XLSX列構成を固定せず安全に取り込む処理を次段で追加。",
    },
    "iwate": {
        "prefecture": "岩手県",
        "title": "民泊（住宅宿泊事業）について",
        "url": "https://www.pref.iwate.jp/kurashikankyou/anzenanshin/seikatsueisei/1016554/1016555.html",
        "format": "PDF（届出状況一覧）",
        "mode": "source_only",
        "note": "公式PDFは届出状況の集計中心。個別住所を誤抽出しないため自動登録は停止。",
    },
    "akita": {
        "prefecture": "秋田県",
        "title": "住宅宿泊事業者一覧",
        "url": "https://www.pref.akita.lg.jp/pages/archive/31592",
        "format": "PDF（届出者・住宅所在地・電話）",
        "mode": "source_only",
        "note": "届出者住所と届出住宅所在地が同じ表にあるため、誤登録防止の専用解析を次段で追加。",
    },
    "yamagata": {
        "prefecture": "山形県",
        "title": "住宅宿泊事業者一覧",
        "url": "https://www.pref.yamagata.jp/020071/kenfuku/doubutsuaigo/eisei/seikatsueisei/minpaku/minpaku.html",
        "format": "PDF（届出住宅所在地）",
        "mode": "import",
        "note": "県公式PDFが届出住宅所在地を一覧公開しているため、安全に住所候補として取り込み。",
    },
    "fukushima": {
        "prefecture": "福島県",
        "title": "住宅宿泊事業法の受理済み届出住宅一覧",
        "url": "https://www.pref.fukushima.lg.jp/sec/32031a/minpaku-04.html",
        "format": "HTML（商号・屋号・住所等）",
        "mode": "import",
        "note": "県公式HTMLの表から商号・屋号・届出住宅住所・公開電話を取り込み。",
    },
}

CORPORATE_WORDS = ("株式会社", "有限会社", "合同会社", "一般社団法人", "一般財団法人", "（株）", "(株)", "（有）", "(有)")
MAX_BYTES = 10 * 1024 * 1024


def _normalize(value):
    text = unicodedata.normalize("NFKC", value or "").strip().lower()
    text = re.sub(r"[\s\u3000]+", "", text)
    text = re.sub(r"[‐‑‒–—―ー−﹣－]+", "-", text)
    return text


def _candidate_key(prefecture, city, address):
    return "|".join(_normalize(part) for part in (prefecture, city, address))


def _extract_city(address):
    text = (address or "").strip()
    match = re.match(r"^(.+?郡.+?[町村]|.+?[市区町村])", text)
    return match.group(1) if match else ""


def _get(url, accept="text/html,*/*"):
    response = requests.get(url, timeout=20, headers={
        "User-Agent": "Mozilla/5.0 TohokuLodgingSalesAI/1.0",
        "Accept": accept,
        "Accept-Language": "ja,en;q=0.7",
    }, allow_redirects=True)
    response.raise_for_status()
    if len(response.content) > MAX_BYTES:
        raise ValueError("公式資料のサイズが想定上限を超えています。")
    return response


def discover_yamagata_pdf(page_html, base_url):
    soup = BeautifulSoup(page_html, "html.parser")
    for link in soup.find_all("a", href=True):
        label = link.get_text(" ", strip=True)
        href = link.get("href", "")
        if "住宅宿泊事業者一覧" in label and ".pdf" in href.lower():
            return urljoin(base_url, href)
    raise ValueError("山形県の住宅宿泊事業者一覧PDFを見つけられませんでした。")


def parse_yamagata_pdf(pdf_bytes):
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf_bytes)).pages)
    addresses = []
    seen = set()
    for raw in text.splitlines():
        line = unicodedata.normalize("NFKC", raw).strip()
        line = re.sub(r"^\s*\d+[.)]?\s*", "", line)
        if not line or "届出住宅" in line or "住宅宿泊" in line or "現在" in line:
            continue
        if not re.match(r"^(.+?郡.+?[町村]|.+?[市町村])", line):
            continue
        key = _normalize(line)
        if key not in seen:
            seen.add(key)
            addresses.append(line)
    return addresses


def fetch_yamagata_records():
    page = _get(SOURCES["yamagata"]["url"])
    pdf_url = discover_yamagata_pdf(page.text, SOURCES["yamagata"]["url"])
    pdf = _get(pdf_url, "application/pdf,*/*").content
    if not pdf.startswith(b"%PDF"):
        raise ValueError("山形県の取得資料がPDFではありません。")
    return [{"address": address, "name": "", "company_name": "", "phone": "", "official_url": ""} for address in parse_yamagata_pdf(pdf)], pdf_url


def parse_fukushima_html(html):
    soup = BeautifulSoup(html, "html.parser")
    records = []
    for row in soup.select("table tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
        if len(cells) < 3:
            continue
        company, name, address = (cells[0].strip(), cells[1].strip(), cells[2].strip())
        phone = cells[3].strip() if len(cells) > 3 else ""
        if not address or not re.search(r"[市町村郡]", address):
            continue
        records.append({
            "address": address,
            "name": name,
            "company_name": company if any(word in company for word in CORPORATE_WORDS) else "",
            "phone": phone,
            "official_url": "",
        })
    return records


def fetch_fukushima_records():
    response = _get(SOURCES["fukushima"]["url"])
    records = parse_fukushima_html(response.text)
    if not records:
        raise ValueError("福島県の公式一覧から候補を抽出できませんでした。")
    return records, SOURCES["fukushima"]["url"]


def import_records(database, source_key, records, source_url):
    source = SOURCES[source_key]
    prefecture = source["prefecture"]
    new_count = duplicate_count = 0
    with sqlite3.connect(database) as con:
        for record in records:
            address = record["address"].strip()
            city = _extract_city(address)
            key = _candidate_key(prefecture, city, address)
            if con.execute("SELECT id FROM lead_candidates WHERE normalized_key=?", (key,)).fetchone():
                duplicate_count += 1
                continue
            con.execute(
                """INSERT INTO lead_candidates
                   (name,company_name,prefecture,city,address,official_url,phone,source_url,source_type,normalized_key,status,research_status,research_notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,'pending','unresearched',?)""",
                (
                    record.get("name", ""), record.get("company_name", ""), prefecture, city, address,
                    record.get("official_url", ""), record.get("phone", ""), source_url,
                    f"{prefecture} {source['title']}", key, f"[{prefecture}公式資料から収集] {source_url}",
                ),
            )
            new_count += 1
    return {"total": len(records), "new": new_count, "duplicate": duplicate_count}


def register_regional_sources(app):
    if "regional_sources" in app.view_functions:
        return app

    @app.get("/regional-sources", endpoint="regional_sources")
    def regional_sources():
        return render_template("regional_sources.html", sources=SOURCES)

    @app.post("/regional-sources/import", endpoint="import_regional_source")
    def import_regional_source():
        source_key = request.form.get("source", "")
        source = SOURCES.get(source_key)
        if not source or source["mode"] != "import":
            flash("この公式資料は安全な自動取込の対象外です。公式ページから個別確認してください。", "error")
            return redirect(url_for("regional_sources"))
        try:
            if source_key == "yamagata":
                records, source_url = fetch_yamagata_records()
            elif source_key == "fukushima":
                records, source_url = fetch_fukushima_records()
            else:
                raise ValueError("未対応の公式資料です。")
            stats = import_records(app.config["DATABASE"], source_key, records, source_url)
            flash(
                f"{source['prefecture']}：公式資料{stats['total']}件を確認し、新規{stats['new']}件・重複{stats['duplicate']}件でした。",
                "success",
            )
        except (requests.RequestException, ValueError, OSError) as exc:
            app.logger.warning("Regional source import failed (%s): %s", source_key, exc)
            flash(f"{source['prefecture']}の公式資料を取得・解析できませんでした。時間を置いて再度お試しください。", "error")
        return redirect(url_for("regional_sources"))

    return app
