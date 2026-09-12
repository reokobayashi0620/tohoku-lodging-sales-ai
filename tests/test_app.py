import csv
import io

import pytest

from app import create_app


@pytest.fixture()
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": tmp_path / "test.db", "SECRET_KEY": "test"})


@pytest.fixture()
def client(app):
    return app.test_client()


def test_index_contains_sample_data(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "森のわんこコテージ" in response.get_data(as_text=True)


@pytest.mark.parametrize(
    "data,expected",
    [
        ({"facility_type": "民泊", "pet_friendly": 1, "whole_house": 1, "wood_floor": 1}, "S"),
        ({"facility_type": "運営会社", "multiple_facilities": 1}, "A"),
        ({"facility_type": "ホテル"}, "B"),
        ({"facility_type": "その他"}, "C"),
    ],
)
def test_priority_rules(app, data, expected):
    priority, reason = app.calculate_priority(data)
    assert priority == expected
    assert reason


def test_create_search_and_status_update(client):
    response = client.post("/facilities/new", data={
        "name": "テスト山荘", "prefecture": "福島県", "city": "会津若松市",
        "facility_type": "民泊", "pet_friendly": "on", "whole_house": "on",
        "wood_floor": "on", "status": "未連絡",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert "テスト山荘" in response.get_data(as_text=True)
    filtered = client.get("/?q=テスト山荘")
    assert "テスト山荘" in filtered.get_data(as_text=True)
    response = client.post("/facilities/6/status", data={"status": "商談"}, follow_redirects=True)
    assert 'selected>商談' in response.get_data(as_text=True)


def test_csv_has_bom_and_rows(client):
    response = client.get("/export.csv")
    assert response.status_code == 200
    text = response.data.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0][0] == "施設名"
    assert len(rows) == 6


def test_rejects_invalid_prefecture(client):
    response = client.post("/facilities/new", data={"name": "対象外", "prefecture": "東京都"})
    assert response.status_code == 200
    assert "東北6県" in response.get_data(as_text=True)


def test_healthcheck(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_basic_auth_protects_sales_data(tmp_path):
    protected_app = create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "protected.db",
        "SECRET_KEY": "test",
        "APP_USERNAME": "owner",
        "APP_PASSWORD": "strong-password",
    })
    protected_client = protected_app.test_client()

    denied = protected_client.get("/")
    assert denied.status_code == 401
    assert denied.headers["WWW-Authenticate"].startswith("Basic")

    allowed = protected_client.get("/", auth=("owner", "strong-password"))
    assert allowed.status_code == 200
    assert allowed.headers["X-Frame-Options"] == "DENY"

    # Render must be able to monitor the service without learning the password.
    assert protected_client.get("/healthz").status_code == 200
