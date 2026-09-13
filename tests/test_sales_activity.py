import sqlite3

from app import create_app
from sales_activity import register_sales_activity


def make_app(tmp_path):
    db_path = tmp_path / "sales.db"
    app = create_app({"TESTING": True, "DATABASE": db_path, "APP_USERNAME": "", "APP_PASSWORD": ""})
    register_sales_activity(app)
    with sqlite3.connect(db_path) as con:
        cursor = con.execute(
            """INSERT INTO lead_candidates
            (name,company_name,prefecture,city,address,official_url,email,pet_friendly,whole_house,wood_floor,multiple_facilities,research_status,source_url,source_type,normalized_key,status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')""",
            ("営業テスト宿", "株式会社テスト", "宮城県", "仙台市", "仙台市青葉区1", "https://example.com", "info@example.com", 1, 1, 1, 0, "verified", "src", "test", "activity-test"),
        )
        candidate_id = cursor.lastrowid
    return app, db_path, candidate_id


def test_add_sales_activity_saves_theme_and_channel(tmp_path):
    app, db_path, candidate_id = make_app(tmp_path)
    client = app.test_client()
    response = client.post(
        f"/sales-activities/{candidate_id}",
        data={"activity_type": "sent", "theme_key": "pet_damage", "channel": "email", "note": "初回送信"},
    )
    assert response.status_code == 302
    with sqlite3.connect(db_path) as con:
        row = con.execute("SELECT activity_type,theme_key,channel,note FROM sales_activities").fetchone()
    assert row == ("sent", "pet_damage", "email", "初回送信")


def test_invalid_activity_is_not_saved(tmp_path):
    app, db_path, candidate_id = make_app(tmp_path)
    client = app.test_client()
    response = client.post(f"/sales-activities/{candidate_id}", data={"activity_type": "unknown"})
    assert response.status_code == 302
    with sqlite3.connect(db_path) as con:
        count = con.execute("SELECT COUNT(*) FROM sales_activities").fetchone()[0]
    assert count == 0


def test_sales_activity_dashboard_renders_funnel_and_theme(tmp_path):
    app, db_path, candidate_id = make_app(tmp_path)
    with sqlite3.connect(db_path) as con:
        con.execute(
            "INSERT INTO sales_activities (candidate_id,activity_type,theme_key,channel,note) VALUES (?,?,?,?,?)",
            (candidate_id, "replied", "floor_repair", "form", "返信あり"),
        )
    response = app.test_client().get("/sales-activities")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "営業活動ログ" in text
    assert "床の傷・劣化補修" in text
    assert "返信あり" in text
    assert "営業テスト宿" in text
