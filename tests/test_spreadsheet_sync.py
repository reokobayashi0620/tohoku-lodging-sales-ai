import csv
import io

import app as app_module
from simple_sales_flow import seed_businesses
from spreadsheet_sync import CSV_HEADERS, register_spreadsheet_sync


def make_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SHEETS_SYNC_TOKEN", "test-token")
    app = app_module.create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "sales.db",
        "APP_USERNAME": "",
        "APP_PASSWORD": "",
    })
    register_spreadsheet_sync(app)
    seed_businesses(app.config["DATABASE"])
    return app


def test_sales_csv_requires_token(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch)
    client = app.test_client()
    assert client.get("/exports/sales.csv").status_code == 403
    assert client.get("/exports/sales.csv?token=wrong").status_code == 403


def test_sales_csv_exports_seeded_businesses(tmp_path, monkeypatch):
    app = make_app(tmp_path, monkeypatch)
    response = app.test_client().get("/exports/sales.csv?token=test-token")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"

    text = response.get_data(as_text=True).lstrip("\ufeff")
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == CSV_HEADERS
    assert len(rows) == 9
    htp = next(row for row in rows[1:] if row[4] == "株式会社エイチ・ティー・プランニング")
    assert htp[1] == "宮城県"
    assert htp[7] == "info@h-t-p.co.jp"
    assert htp[13] == "新規"
