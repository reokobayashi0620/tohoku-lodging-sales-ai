import sqlite3
from datetime import datetime, timedelta, timezone

from app import create_app
from follow_up import register_follow_up
from follow_up_draft import register_follow_up_draft
from ops_dashboard import build_ops_snapshot, register_ops_dashboard
from sales_activity import register_sales_activity


def _ts(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def _insert_candidate(con, key, name, verified=True, email="info@example.com"):
    con.execute(
        """INSERT INTO lead_candidates
        (name,company_name,prefecture,city,address,official_url,email,pet_friendly,whole_house,wood_floor,multiple_facilities,research_status,source_url,source_type,normalized_key,status)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')""",
        (name,"運営会社","宮城県","仙台市","仙台市青葉区1","https://example.com",email,1,1,1,1,"verified" if verified else "researching","src","test",key),
    )
    return con.execute("SELECT id FROM lead_candidates WHERE normalized_key=?", (key,)).fetchone()[0]


def test_ops_snapshot_combines_new_sales_and_follow_up(tmp_path):
    db_path = tmp_path / "ops.db"
    app = create_app({"TESTING": True, "DATABASE": db_path, "APP_USERNAME": "", "APP_PASSWORD": ""})
    register_sales_activity(app)
    with sqlite3.connect(db_path) as con:
        cid = _insert_candidate(con, "ops|1", "統合宿")
        con.execute(
            "INSERT INTO sales_activities (candidate_id,activity_type,theme_key,channel,created_at) VALUES (?,?,?,?,?)",
            (cid, "sent", "floor_repair", "email", _ts(4)),
        )
        con.commit()
    snapshot = build_ops_snapshot(app)
    assert snapshot["stats"]["ready_sales"] == 1
    assert snapshot["stats"]["due_follow_up"] == 1
    assert snapshot["stats"]["sent"] == 1
    assert snapshot["ready_sales"][0]["band"] == "S"
    assert snapshot["due_follow_up"][0]["bucket"] == "no_reply"


def test_ops_dashboard_and_backup_csv(tmp_path):
    db_path = tmp_path / "ops-route.db"
    app = create_app({"TESTING": True, "DATABASE": db_path, "APP_USERNAME": "", "APP_PASSWORD": ""})
    register_sales_activity(app)
    register_follow_up(app)
    register_follow_up_draft(app)
    register_ops_dashboard(app)
    with sqlite3.connect(db_path) as con:
        cid = _insert_candidate(con, "ops|2", "今日やる宿")
        con.execute(
            "INSERT INTO sales_activities (candidate_id,activity_type,theme_key,channel,note,created_at) VALUES (?,?,?,?,?,?)",
            (cid, "replied", "pet_damage", "email", "写真送付可能との返信", _ts(0)),
        )
        con.commit()

    client = app.test_client()
    response = client.get("/ops")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "今日の営業" in body
    assert "今日やる宿" in body
    assert "要フォロー" in body

    export = client.get("/ops/export.csv")
    assert export.status_code == 200
    assert "text/csv" in export.content_type
    text = export.get_data(as_text=True)
    assert "[候補]" in text
    assert "今日やる宿" in text
    assert "[営業活動]" in text
    assert "replied" in text
