import sqlite3
from datetime import datetime, timezone

from flask import flash, redirect, render_template, request

from auto_discovery import PREFECTURES, fetch_osm_records, import_records
from operator_enrichment import operator_batch
from sales_action import build_sales_draft, recommend_theme
from sales_priority import score_candidate


def build_ready_queue(database, prefecture="", limit=30):
    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    try:
        sql = "SELECT * FROM lead_candidates WHERE status='pending'"
        params = []
        if prefecture:
            sql += " AND prefecture=?"
            params.append(prefecture)
        sql += " ORDER BY updated_at DESC, id DESC"
        rows = con.execute(sql, params).fetchall()
    finally:
        con.close()

    queue = []
    for row in rows:
        scored = score_candidate(row)
        if scored["band"] not in {"S", "A"}:
            continue
        theme = recommend_theme(row)
        draft = build_sales_draft(row, theme)
        queue.append({"candidate": row, **scored, "theme": theme, "draft": draft})
    queue.sort(key=lambda item: ({"S": 0, "A": 1}[item["band"]], -item["score"], item["candidate"]["id"]))
    return queue[:limit]


def run_pipeline(database, prefecture, discovery=True, research_limit=20):
    stats = {
        "prefecture": prefecture,
        "discovered": 0,
        "inserted": 0,
        "duplicates": 0,
        "researched": 0,
        "updated": 0,
        "companies": 0,
        "contacts": 0,
        "failed": 0,
    }
    if discovery:
        records = fetch_osm_records(prefecture)
        inserted, skipped = import_records(database, records)
        stats.update(discovered=len(records), inserted=inserted, duplicates=skipped)

    research = operator_batch(database, limit=research_limit)
    stats.update(
        researched=research["checked"],
        updated=research["updated"],
        companies=research["company_found"],
        contacts=research["contact_found"],
        failed=research["failed"],
    )
    stats["ready"] = len(build_ready_queue(database, prefecture=prefecture, limit=100))
    stats["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return stats


def register_discovery_pipeline(app):
    @app.get("/pipeline")
    def discovery_pipeline():
        prefecture = request.args.get("prefecture", "").strip()
        if prefecture not in PREFECTURES:
            prefecture = ""
        return render_template(
            "discovery_pipeline.html",
            prefectures=PREFECTURES,
            selected_prefecture=prefecture,
            ready=build_ready_queue(app.config["DATABASE"], prefecture=prefecture),
        )

    @app.post("/pipeline/run")
    def discovery_pipeline_run():
        prefecture = request.form.get("prefecture", "").strip()
        if prefecture not in PREFECTURES:
            flash("対象県を選択してください。", "error")
            return redirect("/pipeline")
        try:
            stats = run_pipeline(app.config["DATABASE"], prefecture, discovery=True, research_limit=20)
            flash(
                f"{prefecture} 一括処理完了: 発見{stats['discovered']}件 / 新規{stats['inserted']}件 / "
                f"運営会社調査{stats['researched']}件 / 更新{stats['updated']}件 / "
                f"会社名{stats['companies']}件 / 連絡先{stats['contacts']}件 / 営業準備S/A {stats['ready']}件。",
                "success",
            )
        except Exception:
            app.logger.exception("discovery pipeline failed")
            flash("一括パイプラインの実行に失敗しました。公開データ側が混雑している場合は時間を置いて再実行してください。", "error")
        return redirect(f"/pipeline?prefecture={prefecture}")

    @app.post("/pipeline/research-only")
    def discovery_pipeline_research_only():
        prefecture = request.form.get("prefecture", "").strip()
        if prefecture not in PREFECTURES:
            flash("対象県を選択してください。", "error")
            return redirect("/pipeline")
        try:
            stats = run_pipeline(app.config["DATABASE"], prefecture, discovery=False, research_limit=20)
            flash(
                f"既存候補を調査しました: {stats['researched']}件確認 / {stats['updated']}件更新 / "
                f"会社名{stats['companies']}件 / 連絡先{stats['contacts']}件。",
                "success" if stats["updated"] else "info",
            )
        except Exception:
            app.logger.exception("pipeline research failed")
            flash("既存候補の調査に失敗しました。", "error")
        return redirect(f"/pipeline?prefecture={prefecture}")

    return app
