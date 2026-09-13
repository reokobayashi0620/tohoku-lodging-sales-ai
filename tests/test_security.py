from app import create_app
from security import register_security


def test_authenticated_post_requires_csrf(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "security.db",
        "APP_USERNAME": "owner",
        "APP_PASSWORD": "strong-password",
        "SECRET_KEY": "test-secret",
    })
    register_security(app)
    client = app.test_client()

    login = client.post("/login", data={"username": "owner", "password": "strong-password"})
    assert login.status_code == 302

    page = client.get("/")
    assert page.status_code == 200
    with client.session_transaction() as session:
        token = session["csrf_token"]

    rejected = client.post("/logout")
    assert rejected.status_code == 400

    accepted = client.post("/logout", data={"csrf_token": token})
    assert accepted.status_code == 302


def test_csrf_not_forced_when_auth_disabled(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "security-dev.db",
        "APP_USERNAME": "",
        "APP_PASSWORD": "",
        "SECRET_KEY": "test-secret",
    })
    register_security(app)
    response = app.test_client().post("/logout")
    # No CSRF rejection in local/test mode without authentication.
    assert response.status_code == 302
