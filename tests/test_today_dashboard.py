import sqlite3

from app import create_app
from sales_activity import register_sales_activity
from today_dashboard import register_today_dashboard


def test_today_dashboard_shows_ready_candidate(tmp_path):
    db_path = tmp_path / "today.db"
    app = create_app({"TESTING": True, "DATABASE": db_path, "APP_USERNAME": "", "APP_PASSWORD": ""})
    register_sales_activity(app)
    register_today_dashboard(app)

    with sqlite3.connect(db_path) as con:
        con.execute(
            """INSERT INTO lead_candidates
            (name, company_name, prefecture, city, address, official_url, email,
             pet_friendly, whole_house, wood_floor, multiple_facilities,
             research_status, source_url, source_type, normalized_key, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')""",
            (
                "営業候補宿", "運営株式会社", "宮城県", "仙台市", "仙台市青葉区1",
                "https://example.com", "info@example.com", 1, 1, 1, 1,
                "verified", "src", "test", "today|1",
            ),
        )
        con.commit()

    response = app.test_client().get("/today")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "今日やること" in body
    assert "営業候補宿" in body
    assert "営業文を作成" in body
