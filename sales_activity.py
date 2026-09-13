import sqlite3
from flask import abort, flash, redirect, render_template, request

from sales_action import THEMES

ACTIVITY_TYPES = {
    "sent": "送信済み",
    "replied": "返信あり",
    "estimate": "見積",
    "won": "成約",
    "lost": "見送り",
}
CHANNELS = {
    "email": "メール",
    "form": "問い合わせフォーム",
    "phone": "電話",
    "other": "その他",
}


def _ensure_table(app):
    con = sqlite3.connect(app.config["DATABASE"])
    try:
        con.execute(
            """CREATE TABLE IF NOT EXISTS sales_activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id INTEGER NOT NULL,
                activity_type TEXT NOT NULL,
                theme_key TEXT DEFAULT '',
                channel TEXT DEFAULT '',
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (candidate_id) REFERENCES lead_candidates(id)
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_sales_activities_candidate ON sales_activities(candidate_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sales_activities_type ON sales_activities(activity_type)")
        con.commit()
    finally:
        con.close()


def register_sales_activity(app):
    _ensure_table(app)

    @app.post("/sales-activities/<int:candidate_id>")
    def add_sales_activity(candidate_id):
        activity_type = request.form.get("activity_type", "").strip()
        theme_key = request.form.get("theme_key", "").strip()
        channel = request.form.get("channel", "").strip()
        note = request.form.get("note", "").strip()[:2000]

        if activity_type not in ACTIVITY_TYPES:
            flash("営業活動の種類を選択してください。", "error")
            return redirect(f"/sales-action/{candidate_id}")
        if theme_key not in THEMES:
            theme_key = ""
        if channel not in CHANNELS:
            channel = ""

        con = sqlite3.connect(app.config["DATABASE"])
        try:
            candidate = con.execute("SELECT id FROM lead_candidates WHERE id=?", (candidate_id,)).fetchone()
            if not candidate:
                abort(404)
            con.execute(
                "INSERT INTO sales_activities (candidate_id,activity_type,theme_key,channel,note) VALUES (?,?,?,?,?)",
                (candidate_id, activity_type, theme_key, channel, note),
            )
            con.commit()
        finally:
            con.close()
        flash(f"営業活動「{ACTIVITY_TYPES[activity_type]}」を記録しました。", "success")
        return redirect(f"/sales-action/{candidate_id}")

    @app.get("/sales-activities")
    def sales_activities():
        con = sqlite3.connect(app.config["DATABASE"])
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                """SELECT a.*, c.name, c.company_name, c.prefecture, c.city, c.address
                   FROM sales_activities a
                   JOIN lead_candidates c ON c.id=a.candidate_id
                   ORDER BY a.created_at DESC, a.id DESC"""
            ).fetchall()
            counts = dict(con.execute(
                "SELECT activity_type, COUNT(*) FROM sales_activities GROUP BY activity_type"
            ).fetchall())
            theme_counts = con.execute(
                """SELECT theme_key, activity_type, COUNT(*) AS count
                   FROM sales_activities
                   WHERE theme_key <> ''
                   GROUP BY theme_key, activity_type"""
            ).fetchall()
        finally:
            con.close()

        funnel = {key: counts.get(key, 0) for key in ACTIVITY_TYPES}
        theme_summary = {}
        for row in theme_counts:
            summary = theme_summary.setdefault(row["theme_key"], {key: 0 for key in ACTIVITY_TYPES})
            summary[row["activity_type"]] = row["count"]

        return render_template(
            "sales_activities.html",
            rows=rows,
            funnel=funnel,
            activity_types=ACTIVITY_TYPES,
            channels=CHANNELS,
            themes=THEMES,
            theme_summary=theme_summary,
        )

    return app
