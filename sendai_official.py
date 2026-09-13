import sqlite3

import requests
from flask import flash, redirect

from app import candidate_key, fetch_sendai_candidates

SENDAI_LIST_PAGE = "https://www.city.sendai.jp/sekatsuese/jigyosha/kankyo/shokuhin/minpaku/todokedeichiran.html"
SENDAI_SOURCE_TYPE = "仙台市公式 住宅宿泊事業法届出住宅一覧"


def import_sendai_official_records(database, addresses, source_url):
    inserted = duplicates = 0
    with sqlite3.connect(database) as con:
        con.row_factory = sqlite3.Row
        for raw_address in addresses:
            address = (raw_address or "").strip()
            if not address:
                continue
            city = "仙台市"
            key = candidate_key("宮城県", city, address)
            existing = con.execute(
                "SELECT id FROM lead_candidates WHERE normalized_key=?", (key,)
            ).fetchone()
            if existing:
                duplicates += 1
                continue
            note = f"[仙台市公式民泊一覧] 届出住宅所在地から自動取込 / 出典: {source_url}"
            con.execute(
                """INSERT INTO lead_candidates
                (name,company_name,prefecture,city,address,official_url,phone,email,contact_url,
                 source_url,source_type,normalized_key,status,research_status,research_notes)
                VALUES ('','','宮城県',?,?, '', '', '', '', ?,?,?, 'pending','unresearched',?)""",
                (city, address, source_url, SENDAI_SOURCE_TYPE, key, note),
            )
            inserted += 1
    return {"source_records": len(addresses), "inserted": inserted, "duplicates": duplicates}


def register_sendai_official(app):
    @app.post("/targets/import-sendai", endpoint="import_sendai_targets")
    def import_sendai_targets():
        try:
            addresses = fetch_sendai_candidates(app.config["SENDAI_SOURCE_URL"])
            source_url = getattr(addresses, "source_url", None) or app.config["SENDAI_SOURCE_URL"]
            stats = import_sendai_official_records(app.config["DATABASE"], addresses, source_url)
            flash(
                f"仙台市公式民泊一覧 {stats['source_records']}件を確認。新規{stats['inserted']}件、重複{stats['duplicates']}件です。",
                "success",
            )
        except (requests.RequestException, ValueError, OSError) as exc:
            app.logger.warning("Sendai official import failed: %s", exc)
            flash("仙台市公式民泊一覧を取得できませんでした。時間を置いて再度お試しください。", "error")
        return redirect("/targets?prefecture=宮城県")

    return app
