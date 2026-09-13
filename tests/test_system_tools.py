from app import create_app
from system_tools import register_system_tools


def test_system_page_and_database_backup(tmp_path):
    db_path = tmp_path / "system.db"
    app = create_app({"TESTING": True, "DATABASE": db_path, "APP_USERNAME": "", "APP_PASSWORD": ""})
    register_system_tools(app)
    client = app.test_client()

    page = client.get("/system")
    assert page.status_code == 200
    assert "システム状態" in page.get_data(as_text=True)

    backup = client.get("/backup/database")
    assert backup.status_code == 200
    assert len(backup.data) > 100
    assert backup.data.startswith(b"SQLite format 3")
