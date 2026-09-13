import re

from flask import Flask

from security_hardening import register_security_hardening


def test_csrf_token_is_injected_and_required():
    app = Flask(__name__)
    app.config.update(SECRET_KEY="test", TESTING=True, CSRF_TESTING=True, CSRF_ENABLED=True)

    @app.get("/form")
    def form():
        return '<form method="post" action="/submit"><button>送信</button></form>'

    @app.post("/submit")
    def submit():
        return "ok"

    register_security_hardening(app)
    client = app.test_client()

    page = client.get("/form")
    body = page.get_data(as_text=True)
    match = re.search(r'name="_csrf_token" value="([^"]+)"', body)
    assert match

    assert client.post("/submit").status_code == 400
    assert client.post("/submit", data={"_csrf_token": match.group(1)}).status_code == 200
