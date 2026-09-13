import sqlite3
from datetime import datetime, timedelta, timezone

from app import create_app
from follow_up import build_follow_up_rows, classify_follow_up, register_follow_up
from sales_activity import register_sales_activity


def _ts(days_ago):
    value = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def test_classify_follow_up_rules():
    now = datetime(2026, 9, 13, 3, 0, 0, tzinfo=timezone.utc)
    assert classify_follow_up("replied", "2026-09-13 02:00:00", now)["bucket"] == "reply_action"
    estimate = classify_follow_up("estimate", "2026-09-09 02:00:00", now)
    assert estimate["bucket"] == "estimate_followup"
    assert estimate["due"] is True
    sent = classify_follow_up("sent", "2026-09-09 02:00:00", now)
    assert sent["bucket"] == "no_reply"
    assert sent["due"] is True
    waiting = classify_follow_up("sent", "2026-09-12 02:00:00", now)
    assert waiting["bucket"] == "waiting"
    assert waiting["due"] is False
    assert classify_follow_up("won", "2026-09-09 02:00:00", now) is None
    assert classify_follow_up("lost", "2026-09-09 02:00:00", now) is None


def test_build_follow_up_rows_uses_latest_activity_only():
    rows = [
        {"candidate_id": 1, "activity_type": "replied", "created_at": "2026-09-13 02:00:00"},
        {"candidate_id": 1, "activity_type": "sent", "created_at": "2026-09-08 02:00:00"},
        {"candidate_id": 2, "activity_type": "won", "created_at": "2026-09-12 02:00:00"},
    ]
    now = datetime(2026, 9, 13, 3, 0, 0, tzinfo=timezone.utc)
    result = build_follow_up_rows(rows, now=now)
    assert len(result) == 1
    assert result[0]["row"]["candidate_id"] == 1
    assert result[0]["bucket"] == "reply_action"


def test_follow_up_route_renders_due_queue(tmp_path):
    db_path = tmp_path / "followup.db"
    app = create_app({"TESTING": True, "DATABASE": db_path, "APP_USERNAME": "", "APP_PASSWORD": ""})
    register_sales_activity(app)
    register_follow_up(app)

    with sqlite3.connect(db_path) as con:
        con.execute("""INSERT INTO lead_candidates
          (name,prefecture,city,address,source_url,source_type,normalized_key,status)
          VALUES (?,?,?,?,?,?,?,'pending')""",
          ("追客宿", "宮城県", "仙台市", "仙台市青葉区1", "src", "test", "follow|1"))
        candidate_id = con.execute("SELECT id FROM lead_candidates WHERE normalized_key='follow|1'").fetchone()[0]
        con.execute(
            "INSERT INTO sales_activities (candidate_id,activity_type,theme_key,channel,note,created_at) VALUES (?,?,?,?,?,?)",
            (candidate_id, "sent", "floor_repair", "email", "初回送信", _ts(4)),
        )
        con.commit()

    response = app.test_client().get("/follow-up")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "フォローアップ管理" in body
    assert "追客宿" in body
    assert "未返信" in body
    assert "短い追客文で再連絡" in body


def test_follow_up_route_hides_won_and_lost(tmp_path):
    db_path = tmp_path / "followup-terminal.db"
    app = create_app({"TESTING": True, "DATABASE": db_path, "APP_USERNAME": "", "APP_PASSWORD": ""})
    register_sales_activity(app)
    register_follow_up(app)

    with sqlite3.connect(db_path) as con:
        con.execute("""INSERT INTO lead_candidates
          (name,prefecture,city,address,source_url,source_type,normalized_key,status)
          VALUES (?,?,?,?,?,?,?,'pending')""",
          ("成約宿", "山形県", "山形市", "山形市1", "src", "test", "follow|2"))
        candidate_id = con.execute("SELECT id FROM lead_candidates WHERE normalized_key='follow|2'").fetchone()[0]
        con.execute(
            "INSERT INTO sales_activities (candidate_id,activity_type,created_at) VALUES (?,?,?)",
            (candidate_id, "won", _ts(1)),
        )
        con.commit()

    body = app.test_client().get("/follow-up?due=0").get_data(as_text=True)
    assert "成約宿" not in body
