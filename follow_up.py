import sqlite3
from datetime import datetime, timezone

from flask import render_template, request

from sales_activity import ACTIVITY_TYPES
from sales_action import THEMES

FOLLOW_UP_ORDER = {
    "estimate_followup": 0,
    "reply_action": 1,
    "no_reply": 2,
    "waiting": 3,
}


def _parse_sqlite_datetime(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def classify_follow_up(activity_type, created_at, now=None):
    """Classify the latest activity into an explainable follow-up queue bucket."""
    now = now or datetime.now(timezone.utc)
    created = _parse_sqlite_datetime(created_at)
    age_days = max((now - created).days, 0) if created else 0

    if activity_type in {"won", "lost"}:
        return None
    if activity_type == "estimate":
        return {
            "bucket": "estimate_followup",
            "label": "見積提出後",
            "action": "見積内容の不明点・検討状況を確認",
            "due": age_days >= 3,
            "age_days": age_days,
        }
    if activity_type == "replied":
        return {
            "bucket": "reply_action",
            "label": "返信あり",
            "action": "返信内容を確認して次の提案・見積へ進める",
            "due": True,
            "age_days": age_days,
        }
    if activity_type == "sent":
        due = age_days >= 3
        return {
            "bucket": "no_reply" if due else "waiting",
            "label": "未返信" if due else "送信後待機",
            "action": "短い追客文で再連絡" if due else "3日経過まで待機",
            "due": due,
            "age_days": age_days,
        }
    return None


def build_follow_up_rows(rows, now=None):
    result = []
    seen = set()
    for row in rows:
        candidate_id = row["candidate_id"]
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        follow = classify_follow_up(row["activity_type"], row["created_at"], now=now)
        if not follow:
            continue
        result.append({"row": row, **follow})

    result.sort(key=lambda item: (
        0 if item["due"] else 1,
        FOLLOW_UP_ORDER.get(item["bucket"], 9),
        -item["age_days"],
        item["row"]["candidate_id"],
    ))
    return result


def register_follow_up(app):
    @app.get("/follow-up")
    def follow_up():
        bucket_filter = request.args.get("bucket", "").strip()
        due_only = request.args.get("due", "1") == "1"

        con = sqlite3.connect(app.config["DATABASE"])
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                """SELECT a.*, c.name, c.company_name, c.prefecture, c.city, c.address,
                          c.email, c.phone, c.contact_url
                   FROM sales_activities a
                   JOIN lead_candidates c ON c.id=a.candidate_id
                   ORDER BY a.candidate_id, a.created_at DESC, a.id DESC"""
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        finally:
            con.close()

        queue = build_follow_up_rows(rows)
        summary = {
            key: sum(1 for item in queue if item["bucket"] == key)
            for key in FOLLOW_UP_ORDER
        }
        if bucket_filter in FOLLOW_UP_ORDER:
            queue = [item for item in queue if item["bucket"] == bucket_filter]
        if due_only:
            queue = [item for item in queue if item["due"]]

        return render_template(
            "follow_up.html",
            queue=queue,
            summary=summary,
            bucket_filter=bucket_filter,
            due_only=due_only,
            activity_types=ACTIVITY_TYPES,
            themes=THEMES,
        )

    return app
