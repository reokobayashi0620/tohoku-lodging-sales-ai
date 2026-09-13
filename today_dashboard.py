import sqlite3

from flask import render_template

from follow_up import build_follow_up_rows
from sales_priority import PREFECTURE_RANK, score_candidate


def _rank_candidates(rows):
    ranked = []
    for row in rows:
        scored = score_candidate(row)
        if scored["band"] not in {"S", "A"}:
            continue
        ranked.append({"candidate": row, **scored})
    ranked.sort(key=lambda item: (
        0 if item["band"] == "S" else 1,
        -item["score"],
        PREFECTURE_RANK.get(item["candidate"]["prefecture"], 9),
        item["candidate"]["id"],
    ))
    return ranked


def register_today_dashboard(app):
    @app.get("/today")
    def today_dashboard():
        con = sqlite3.connect(app.config["DATABASE"])
        con.row_factory = sqlite3.Row
        try:
            candidates = con.execute(
                "SELECT * FROM lead_candidates WHERE status='pending' ORDER BY id"
            ).fetchall()
            try:
                activity_rows = con.execute(
                    """SELECT a.*, c.name, c.company_name, c.prefecture, c.city, c.address,
                              c.email, c.phone, c.contact_url
                       FROM sales_activities a
                       JOIN lead_candidates c ON c.id=a.candidate_id
                       ORDER BY a.candidate_id, a.created_at DESC, a.id DESC"""
                ).fetchall()
            except sqlite3.OperationalError:
                activity_rows = []
        finally:
            con.close()

        ranked = _rank_candidates(candidates)
        queue = build_follow_up_rows(activity_rows)
        due = [item for item in queue if item["due"]]
        replies = [item for item in due if item["bucket"] == "reply_action"]
        estimates = [item for item in due if item["bucket"] == "estimate_followup"]

        return render_template(
            "today_dashboard.html",
            stats={
                "pending": len(candidates),
                "ready": len(ranked),
                "due": len(due),
                "replies": len(replies),
                "estimates": len(estimates),
            },
            ranked=ranked[:8],
            due=due[:8],
        )

    return app
