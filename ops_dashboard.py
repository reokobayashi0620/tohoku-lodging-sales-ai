import csv
import io
import sqlite3
from datetime import datetime, timezone

from flask import Response, render_template

from follow_up import build_follow_up_rows
from sales_priority import score_candidate


def _rows(app, sql, params=()):
    con = sqlite3.connect(app.config["DATABASE"])
    con.row_factory = sqlite3.Row
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def _safe_count(app, sql, params=()):
    con = sqlite3.connect(app.config["DATABASE"])
    try:
        try:
            return con.execute(sql, params).fetchone()[0]
        except sqlite3.OperationalError:
            return 0
    finally:
        con.close()


def build_ops_snapshot(app):
    candidates = _rows(app, "SELECT * FROM lead_candidates WHERE status='pending' ORDER BY id DESC")
    ranked = []
    for row in candidates:
        scored = score_candidate(row)
        if scored["band"] in {"S", "A"}:
            ranked.append({"candidate": row, **scored})
    ranked.sort(key=lambda item: ({"S": 0, "A": 1}[item["band"]], -item["score"], item["candidate"]["id"]))

    try:
        activity_rows = _rows(
            app,
            """SELECT a.*, c.name, c.company_name, c.prefecture, c.city, c.address, c.email, c.phone, c.contact_url
               FROM sales_activities a JOIN lead_candidates c ON c.id=a.candidate_id
               ORDER BY a.candidate_id, a.created_at DESC, a.id DESC""",
        )
    except sqlite3.OperationalError:
        activity_rows = []
    follow_queue = build_follow_up_rows(activity_rows)
    due_follow = [item for item in follow_queue if item["due"]]

    stats = {
        "pending_candidates": len(candidates),
        "ready_sales": len(ranked),
        "due_follow_up": len(due_follow),
        "verified_candidates": sum(1 for row in candidates if row["research_status"] == "verified"),
        "sent": _safe_count(app, "SELECT COUNT(*) FROM sales_activities WHERE activity_type='sent'"),
        "replied": _safe_count(app, "SELECT COUNT(*) FROM sales_activities WHERE activity_type='replied'"),
        "estimate": _safe_count(app, "SELECT COUNT(*) FROM sales_activities WHERE activity_type='estimate'"),
        "won": _safe_count(app, "SELECT COUNT(*) FROM sales_activities WHERE activity_type='won'"),
    }
    stats["reply_rate"] = round(stats["replied"] / stats["sent"] * 100, 1) if stats["sent"] else 0.0
    stats["win_rate"] = round(stats["won"] / stats["sent"] * 100, 1) if stats["sent"] else 0.0

    return {
        "stats": stats,
        "ready_sales": ranked[:10],
        "due_follow_up": due_follow[:10],
    }


def register_ops_dashboard(app):
    @app.get("/ops")
    def ops_dashboard():
        return render_template("ops_dashboard.html", **build_ops_snapshot(app))

    @app.get("/ops/export.csv")
    def ops_export_csv():
        con = sqlite3.connect(app.config["DATABASE"])
        con.row_factory = sqlite3.Row
        try:
            candidates = con.execute(
                """SELECT id,name,company_name,prefecture,city,address,phone,email,contact_url,
                          pet_friendly,whole_house,wood_floor,multiple_facilities,research_status,status,updated_at
                   FROM lead_candidates ORDER BY id"""
            ).fetchall()
            try:
                activities = con.execute(
                    """SELECT a.id,a.candidate_id,a.activity_type,a.theme_key,a.channel,a.note,a.created_at,
                              c.name AS candidate_name,c.prefecture
                       FROM sales_activities a JOIN lead_candidates c ON c.id=a.candidate_id
                       ORDER BY a.id"""
                ).fetchall()
            except sqlite3.OperationalError:
                activities = []
        finally:
            con.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["# 東北リペア営業ノート バックアップ", datetime.now(timezone.utc).isoformat()])
        writer.writerow([])
        writer.writerow(["[候補]"])
        writer.writerow(["id","施設名","運営会社","都道府県","市区町村","住所","電話","メール","問い合わせURL","ペット可","一棟貸し","木質床","複数施設","調査状態","候補状態","更新日時"])
        for row in candidates:
            writer.writerow(list(row))
        writer.writerow([])
        writer.writerow(["[営業活動]"])
        writer.writerow(["id","candidate_id","活動種別","提案テーマ","連絡手段","メモ","日時","施設名","都道府県"])
        for row in activities:
            writer.writerow(list(row))

        return Response(
            "\ufeff" + output.getvalue(),
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=tohoku-sales-backup.csv"},
        )

    return app
