import re
import sqlite3
import unicodedata
from io import BytesIO
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from flask import flash, redirect, render_template, url_for
from pypdf import PdfReader

from regional_sources import SOURCES

IWATE_SOURCE_URL = SOURCES["iwate"]["url"]
MAX_BYTES = 10 * 1024 * 1024
PREFECTURES = ("宮城県", "青森県", "岩手県", "秋田県", "山形県", "福島県")


def ensure_snapshot_table(database):
    with sqlite3.connect(database) as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS official_source_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_key TEXT NOT NULL,
                area_name TEXT NOT NULL,
                reported_count INTEGER NOT NULL DEFAULT 0,
                snapshot_label TEXT DEFAULT '',
                source_url TEXT DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_key, area_name)
            )"""
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_official_source_snapshots_source ON official_source_snapshots(source_key)"
        )


def _get(url, accept="text/html,*/*"):
    response = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0 TohokuLodgingSalesAI/1.0",
            "Accept": accept,
            "Accept-Language": "ja,en;q=0.7",
        },
        allow_redirects=True,
    )
    response.raise_for_status()
    if len(response.content) > MAX_BYTES:
        raise ValueError("岩手県の公式資料が想定サイズを超えています。")
    return response


def discover_iwate_status_pdf(page_html, base_url=IWATE_SOURCE_URL):
    soup = BeautifulSoup(page_html, "html.parser")
    candidates = []
    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        label = link.get_text(" ", strip=True)
        if ".pdf" not in href.lower():
            continue
        score = 0
        if "住宅宿泊事業法に基づく届出状況一覧" in label:
            score += 10
        if "届出状況一覧" in label:
            score += 5
        if "todokede" in href.lower():
            score += 2
        if score:
            candidates.append((score, urljoin(base_url, href), label))
    if not candidates:
        raise ValueError("岩手県の届出状況一覧PDFを見つけられませんでした。")
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1], candidates[0][2]


def _pdf_text(pdf_bytes):
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf_bytes)).pages)


def _clean_line(value):
    text = unicodedata.normalize("NFKC", value or "").strip()
    return re.sub(r"\s+", " ", text)


def parse_iwate_municipality_counts(pdf_bytes):
    text = _pdf_text(pdf_bytes)
    lines = [_clean_line(line) for line in text.splitlines() if _clean_line(line)]
    municipalities = {}

    # The official PDF is a statistical summary, not a property-address list.
    # Extract only municipality/count pairs so we can prioritize manual research areas safely.
    municipality_pattern = r"([一-龥々ヶケぁ-んァ-ヶー]+(?:市|町|村))"
    for line in lines:
        for match in re.finditer(municipality_pattern, line):
            name = match.group(1)
            tail = line[match.end():]
            count_match = re.search(r"(?:^|\s)(\d{1,4})(?:\s|件|$)", tail)
            if count_match:
                municipalities[name] = int(count_match.group(1))

    # pypdf may split a two-column table into alternating lines.
    for index, line in enumerate(lines[:-1]):
        if re.fullmatch(municipality_pattern, line):
            next_line = lines[index + 1]
            if re.fullmatch(r"\d{1,4}", next_line):
                municipalities[line] = int(next_line)

    # Remove table totals and administrative labels if OCR/text extraction glues them to names.
    cleaned = {
        name: count
        for name, count in municipalities.items()
        if name not in {"合計市", "合計町", "合計村"} and 0 <= count < 10000
    }
    if not cleaned:
        raise ValueError("岩手県PDFから市町村別の届出件数を抽出できませんでした。")
    return sorted(cleaned.items(), key=lambda item: (-item[1], item[0]))


def _snapshot_label(text):
    normalized = unicodedata.normalize("NFKC", text or "")
    match = re.search(r"(令和\d+年\d+月\d+日)(?:現在|時点)?", normalized)
    return match.group(1) if match else ""


def fetch_iwate_research_plan():
    page = _get(IWATE_SOURCE_URL)
    pdf_url, label = discover_iwate_status_pdf(page.text, IWATE_SOURCE_URL)
    pdf = _get(pdf_url, "application/pdf,*/*")
    if not pdf.content.startswith(b"%PDF"):
        raise ValueError("岩手県の取得資料がPDFではありません。")
    counts = parse_iwate_municipality_counts(pdf.content)
    snapshot = _snapshot_label(label) or _snapshot_label(_pdf_text(pdf.content))
    return counts, snapshot, pdf_url


def save_iwate_snapshot(database, counts, snapshot_label, source_url):
    ensure_snapshot_table(database)
    with sqlite3.connect(database) as con:
        for area_name, reported_count in counts:
            con.execute(
                """INSERT INTO official_source_snapshots
                   (source_key, area_name, reported_count, snapshot_label, source_url, updated_at)
                   VALUES ('iwate',?,?,?,?,CURRENT_TIMESTAMP)
                   ON CONFLICT(source_key, area_name) DO UPDATE SET
                     reported_count=excluded.reported_count,
                     snapshot_label=excluded.snapshot_label,
                     source_url=excluded.source_url,
                     updated_at=CURRENT_TIMESTAMP""",
                (area_name, reported_count, snapshot_label, source_url),
            )
        placeholders = ",".join("?" for _ in counts)
        if counts:
            con.execute(
                f"DELETE FROM official_source_snapshots WHERE source_key='iwate' AND area_name NOT IN ({placeholders})",
                [name for name, _ in counts],
            )
    return len(counts)


def collection_summary(database):
    ensure_snapshot_table(database)
    with sqlite3.connect(database) as con:
        con.row_factory = sqlite3.Row
        candidate_rows = con.execute(
            """SELECT prefecture,
                      COUNT(*) AS total,
                      SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending,
                      SUM(CASE WHEN status='promoted' THEN 1 ELSE 0 END) AS promoted,
                      SUM(CASE WHEN status='excluded' THEN 1 ELSE 0 END) AS excluded,
                      SUM(CASE WHEN status='pending' AND research_status='unresearched' THEN 1 ELSE 0 END) AS unresearched,
                      SUM(CASE WHEN status='pending' AND research_status='researching' THEN 1 ELSE 0 END) AS researching,
                      SUM(CASE WHEN status='pending' AND research_status='verified' THEN 1 ELSE 0 END) AS verified
               FROM lead_candidates GROUP BY prefecture"""
        ).fetchall()
        facility_rows = con.execute(
            "SELECT prefecture, COUNT(*) AS count FROM facilities GROUP BY prefecture"
        ).fetchall()
        iwate_rows = con.execute(
            """SELECT area_name, reported_count, snapshot_label, source_url, updated_at
               FROM official_source_snapshots WHERE source_key='iwate'
               ORDER BY reported_count DESC, area_name"""
        ).fetchall()

    candidate_map = {row["prefecture"]: dict(row) for row in candidate_rows}
    facility_map = {row["prefecture"]: row["count"] for row in facility_rows}
    summary = []
    for prefecture in PREFECTURES:
        item = candidate_map.get(prefecture, {})
        summary.append({
            "prefecture": prefecture,
            "total": item.get("total", 0) or 0,
            "pending": item.get("pending", 0) or 0,
            "promoted": item.get("promoted", 0) or 0,
            "excluded": item.get("excluded", 0) or 0,
            "unresearched": item.get("unresearched", 0) or 0,
            "researching": item.get("researching", 0) or 0,
            "verified": item.get("verified", 0) or 0,
            "facilities": facility_map.get(prefecture, 0),
        })
    return summary, [dict(row) for row in iwate_rows]


def register_collection_dashboard(app):
    if "collection_dashboard" in app.view_functions:
        return app

    ensure_snapshot_table(app.config["DATABASE"])

    @app.get("/collection-dashboard", endpoint="collection_dashboard")
    def dashboard():
        summary, iwate_rows = collection_summary(app.config["DATABASE"])
        coverage = [
            {"label": "宮城県", "status": "自動収集＋公式照合", "active": True},
            {"label": "仙台市", "status": "自動収集", "active": True},
            {"label": "青森県", "status": "XLSX自動取込", "active": True},
            {"label": "岩手県", "status": "市町村別件数→調査優先順位", "active": False},
            {"label": "秋田県", "status": "PDF自動取込", "active": True},
            {"label": "山形県", "status": "PDF自動取込", "active": True},
            {"label": "福島県", "status": "HTML自動取込", "active": True},
        ]
        return render_template(
            "collection_dashboard.html",
            summary=summary,
            coverage=coverage,
            iwate_rows=iwate_rows,
            iwate_source_url=IWATE_SOURCE_URL,
        )

    @app.post("/collection-dashboard/iwate-refresh", endpoint="refresh_iwate_plan")
    def refresh_iwate_plan():
        try:
            counts, snapshot, source_url = fetch_iwate_research_plan()
            save_iwate_snapshot(app.config["DATABASE"], counts, snapshot, source_url)
            total = sum(count for _, count in counts)
            flash(
                f"岩手県公式PDFから{len(counts)}市町村・届出件数合計{total}件を読み取り、調査優先順位を更新しました。",
                "success",
            )
        except (requests.RequestException, ValueError, OSError) as exc:
            app.logger.warning("Iwate research plan refresh failed: %s", exc)
            flash("岩手県の公式届出状況を取得・解析できませんでした。公式ページは引き続き確認できます。", "error")
        return redirect(url_for("collection_dashboard"))

    return app
