import sqlite3
from datetime import datetime, timedelta, timezone

from app import create_app
from follow_up_draft import build_follow_up_draft, register_follow_up_draft
from sales_activity import register_sales_activity


def _ts(days_ago):
    value = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _row(**kwargs):
    base = {
        "name": "テスト宿",
        "company_name": "運営会社",
    }
    base.update(kwargs)
    return base


def test_build_follow_up_draft_changes_by_latest_activity():
    candidate = _row()
    sent = {"activity_type": "sent", "created_at": _ts(4), "theme_key": "floor_repair", "note": ""}
    replied = {"activity_type": "replied", "created_at": _ts(0), "theme_key": "pet_damage", "note": "写真を送れます"}
    estimate = {"activity_type": "estimate", "created_at": _ts(4), "theme_key": "coating", "note": ""}

    assert "その後ご確認いただけましたでしょうか" in build_follow_up_draft(candidate, sent)
    reply_text = build_follow_up_draft(candidate, replied)
    assert "ご返信ありがとうございます" in reply_text
    assert "写真を送れます" in reply_text
    assert "お見積" in build_follow_up_draft(candidate, estimate)


def test_short_and_soft_tones_are_available():
    candidate = _row()
    activity = {"activity_type": "sent", "created_at": _ts(4), "theme_key": "floor_repair", "note": ""}
    standard = build_follow_up_draft(candidate, activity, "standard")
    short = build_follow_up_draft(candidate, activity, "short")
    soft = build_follow_up_draft(candidate, activity, "soft")
    assert len(short) < len(standard)
    assert "無理のないタイミング" in soft


def test_follow_up_draft_route_renders_latest_activity(tmp_path):
    db_path = tmp_path / "draft.db"
    app = create_app({"TESTING": True, "DATABASE": db_path, "APP_USERNAME": "", "APP_PASSWORD": ""})
    register_sales_activity(app)
    register_follow_up_draft(app)

    with sqlite3.connect(db_path) as con:
        con.execute("""INSERT INTO lead_candidates
          (name,company_name,prefecture,city,address,source_url,source_type,normalized_key,status)
          VALUES (?,?,?,?,?,?,?,?, 'pending')""",
          ("追客宿", "運営社", "宮城県", "仙台市", "仙台市青葉区1", "src", "test", "draft|1"))
        candidate_id = con.execute("SELECT id FROM lead_candidates WHERE normalized_key='draft|1'").fetchone()[0]
        con.execute(
            "INSERT INTO sales_activities (candidate_id,activity_type,theme_key,channel,note,created_at) VALUES (?,?,?,?,?,?)",
            (candidate_id, "sent", "floor_repair", "email", "初回送信", _ts(4)),
        )
        con.commit()

    response = app.test_client().get(f"/follow-up-draft/{candidate_id}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "フォローアップ文作成" in body
    assert "追客宿" in body
    assert "床の傷・劣化補修" in body
    assert "その後ご確認いただけましたでしょうか" in body
    assert "自動送信は行いません" in body
