import re
import sqlite3
import unicodedata

from flask import flash, redirect, request

from target_finder import PREFECTURES, is_official_registry_candidate, is_osm_candidate


def normalize_address(value):
    text = unicodedata.normalize("NFKC", value or "").lower()
    text = re.sub(r"(?:〒\s*)?\d{3}-?\d{4}", "", text)
    text = text.replace("ヶ", "ケ").replace("之", "の")
    text = re.sub(r"(丁目|番地|番|号)", "-", text)
    text = re.sub(r"[‐‑‒–—―ー−]+", "-", text)
    text = re.sub(r"[\s　,，.。・]+", "", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def _match_key(row):
    address = normalize_address(row["address"] or "")
    prefecture = normalize_address(row["prefecture"] or "")
    if prefecture and address.startswith(prefecture):
        address = address[len(prefecture):]
    return address


def reconcile_candidates(database, prefecture=""):
    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT * FROM lead_candidates WHERE status='pending' ORDER BY id").fetchall()
        osm_by_key = {}
        for row in rows:
            if not is_osm_candidate(row):
                continue
            if prefecture and row["prefecture"] != prefecture:
                continue
            key = (row["prefecture"], _match_key(row))
            if key[1] and key not in osm_by_key:
                osm_by_key[key] = row

        stats = {"official_checked": 0, "matched": 0, "updated": 0}
        for row in rows:
            if not is_official_registry_candidate(row):
                continue
            if prefecture and row["prefecture"] != prefecture:
                continue
            stats["official_checked"] += 1
            key = (row["prefecture"], _match_key(row))
            osm = osm_by_key.get(key)
            if not osm:
                continue
            stats["matched"] += 1
            changes = {}
            for field in ("name", "official_url", "phone", "email", "contact_url"):
                if not row[field] and osm[field]:
                    changes[field] = osm[field]
            for field in ("pet_friendly", "whole_house", "multiple_facilities", "wood_floor"):
                if not row[field] and osm[field]:
                    changes[field] = osm[field]
            note = f"[候補自動照合] 同一所在地のOpenStreetMap公開POI「{osm['name'] or '名称未設定'}」と照合。営業前に公式サイトで最終確認。"
            current_notes = row["research_notes"] or ""
            if note not in current_notes:
                changes["research_notes"] = (current_notes + "\n" + note).strip()
            if changes:
                assignments = ", ".join(f"{field}=?" for field in changes)
                con.execute(
                    f"UPDATE lead_candidates SET {assignments}, research_status='researching', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    [*changes.values(), row["id"]],
                )
                stats["updated"] += 1
        con.commit()
        return stats
    finally:
        con.close()


def register_candidate_reconciliation(app):
    @app.post("/targets/reconcile", endpoint="reconcile_targets")
    def reconcile_targets():
        prefecture = request.form.get("prefecture", "").strip()
        if prefecture not in PREFECTURES:
            prefecture = ""
        stats = reconcile_candidates(app.config["DATABASE"], prefecture)
        flash(
            f"公式届出と公開POIを照合: 公式{stats['official_checked']}件 / 同一所在地{stats['matched']}件 / 情報更新{stats['updated']}件。",
            "success" if stats["updated"] else "info",
        )
        suffix = f"?prefecture={prefecture}" if prefecture else ""
        return redirect(f"/targets{suffix}")

    return app
