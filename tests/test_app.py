import csv
import io
import sqlite3

import pytest

import app as app_module
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
    assert "住所" in rows[0]
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


def test_auth_diagnostics_route_is_removed(tmp_path):
    client = protected_app(tmp_path).test_client()
    client.post("/login", data={
        "username": "東北担当", "password": "安全なパスワード🔑",
    })
    assert client.get("/debug-auth").status_code == 404


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


def test_address_normalization_handles_width_spaces_and_hyphens(app):
    left = app.normalize_address(" 宮城郡 松島町 26－2 ")
    right = app.normalize_address("宮城郡松島町26-2")
    assert left == right


def test_candidate_key_is_stable_for_equivalent_addresses(app):
    key1 = app.candidate_key("宮城県", "石巻市", "泉町２－９－１０")
    key2 = app.candidate_key("宮城県", "石巻市", "泉町2-9-10")
    assert key1 == key2


def test_collect_adds_candidates_and_second_run_is_duplicate(monkeypatch, app, client):
    addresses = ["石巻市泉町２－９－１０", "宮城郡松島町松島字垣ノ内２６－２"]
    monkeypatch.setattr(app_module, "fetch_miyagi_candidates", lambda _url: addresses)

    first = client.post("/collect", follow_redirects=True)
    assert first.status_code == 200
    assert "新規2件" in first.get_data(as_text=True)

    second = client.post("/collect", follow_redirects=True)
    assert second.status_code == 200
    assert "新規0件" in second.get_data(as_text=True)

    with sqlite3.connect(app.config["DATABASE"]) as con:
        assert con.execute("SELECT COUNT(*) FROM lead_candidates").fetchone()[0] == 2


def test_promote_candidate_creates_one_facility_only(monkeypatch, app, client):
    monkeypatch.setattr(app_module, "fetch_miyagi_candidates", lambda _url: ["石巻市泉町２－９－１０"])
    client.post("/collect")

    with sqlite3.connect(app.config["DATABASE"]) as con:
        candidate_id = con.execute("SELECT id FROM lead_candidates").fetchone()[0]
        before = con.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]

    response = client.post(f"/candidates/{candidate_id}/promote", follow_redirects=True)
    assert response.status_code == 200
    assert "営業リストへ登録しました" in response.get_data(as_text=True)

    with sqlite3.connect(app.config["DATABASE"]) as con:
        after_first = con.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]
        status, facility_id = con.execute(
            "SELECT status, matched_facility_id FROM lead_candidates WHERE id=?", (candidate_id,)
        ).fetchone()
    assert after_first == before + 1
    assert status == "promoted"
    assert facility_id

    client.post(f"/candidates/{candidate_id}/promote")
    with sqlite3.connect(app.config["DATABASE"]) as con:
        after_second = con.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]
    assert after_second == after_first


def test_exclude_candidate_changes_state(monkeypatch, app, client):
    monkeypatch.setattr(app_module, "fetch_miyagi_candidates", lambda _url: ["名取市高舘熊野堂大沢５７"])
    client.post("/collect")
    with sqlite3.connect(app.config["DATABASE"]) as con:
        candidate_id = con.execute("SELECT id FROM lead_candidates").fetchone()[0]

    response = client.post(f"/candidates/{candidate_id}/exclude", follow_redirects=True)
    assert response.status_code == 200
    with sqlite3.connect(app.config["DATABASE"]) as con:
        assert con.execute("SELECT status FROM lead_candidates WHERE id=?", (candidate_id,)).fetchone()[0] == "excluded"


def test_collect_failure_is_shown_without_crashing(monkeypatch, client):
    def fail(_url):
        raise ValueError("宮城県の公開資料を取得できませんでした。")

    monkeypatch.setattr(app_module, "fetch_miyagi_candidates", fail)
    response = client.post("/collect", follow_redirects=True)
    assert response.status_code == 200
    assert "公開資料を取得できませんでした" in response.get_data(as_text=True)
