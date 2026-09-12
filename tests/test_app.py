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


def protected_app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "protected.db",
        "SECRET_KEY": "test",
        "APP_USERNAME": "東北担当",
        "APP_PASSWORD": "安全なパスワード🔑",
    })


def test_logged_out_user_is_redirected_to_login(tmp_path):
    client = protected_app(tmp_path).test_client()
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert "WWW-Authenticate" not in response.headers


def test_login_success_stores_session_and_opens_sales_screen(tmp_path):
    client = protected_app(tmp_path).test_client()
    response = client.post("/login", data={
        "username": "東北担当", "password": "安全なパスワード🔑",
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    assert client.get("/").status_code == 200
    with client.session_transaction() as login_session:
        assert login_session["logged_in"] is True


def test_login_failure_displays_generic_error_and_does_not_log_in(tmp_path):
    client = protected_app(tmp_path).test_client()
    response = client.post("/login", data={
        "username": "東北担当", "password": "間違ったパスワード",
    })
    assert response.status_code == 200
    assert "ユーザー名またはパスワードが違います" in response.get_data(as_text=True)
    assert client.get("/").status_code == 302


def test_logout_clears_session(tmp_path):
    client = protected_app(tmp_path).test_client()
    client.post("/login", data={
        "username": "東北担当", "password": "安全なパスワード🔑",
    })
    response = client.post("/logout")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert client.get("/").status_code == 302


def test_healthcheck_stays_public_when_login_is_enabled(tmp_path):
    client = protected_app(tmp_path).test_client()
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_auth_diagnostics_stay_public_without_exposing_credentials(tmp_path):
    client = protected_app(tmp_path).test_client()
    response = client.get("/debug-auth")

    assert response.status_code == 200
    assert response.json == {
        "authentication_enabled": True,
        "username_configured": True,
        "password_configured": True,
        "logged_in": False,
        "request_is_secure": False,
        "session_cookie_secure": False,
    }
    assert "東北担当" not in response.get_data(as_text=True)
    assert "安全なパスワード🔑" not in response.get_data(as_text=True)


def test_session_cookie_security_settings(tmp_path):
    app = protected_app(tmp_path)
    app.config["SESSION_COOKIE_SECURE"] = True
    client = app.test_client()
    response = client.post("/login", data={
        "username": "東北担当", "password": "安全なパスワード🔑",
    })
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Secure" in cookie
