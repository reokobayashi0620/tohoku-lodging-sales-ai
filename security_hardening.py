import hmac
import re
import secrets
from html import escape

from flask import abort, request, session

TOKEN_FIELD = "_csrf_token"
FORM_RE = re.compile(r"<form\b(?P<attrs>[^>]*)>", re.IGNORECASE)
POST_METHOD_RE = re.compile(r"\bmethod\s*=\s*['\"]?post(?:['\"\s>]|$)", re.IGNORECASE)


def register_security_hardening(app):
    app.config.setdefault("CSRF_ENABLED", True)

    def csrf_token():
        token = session.get(TOKEN_FIELD)
        if not token:
            token = secrets.token_urlsafe(32)
            session[TOKEN_FIELD] = token
        return token

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def verify_csrf():
        if not app.config.get("CSRF_ENABLED", True):
            return None
        if app.config.get("TESTING") and not app.config.get("CSRF_TESTING"):
            return None
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        expected = session.get(TOKEN_FIELD, "")
        supplied = request.form.get(TOKEN_FIELD, "") or request.headers.get("X-CSRF-Token", "")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            abort(400, description="フォームの有効期限が切れました。画面を再読み込みしてから再度お試しください。")
        return None

    @app.after_request
    def inject_csrf(response):
        if not app.config.get("CSRF_ENABLED", True):
            return response
        if app.config.get("TESTING") and not app.config.get("CSRF_TESTING"):
            return response
        content_type = response.headers.get("Content-Type", "")
        if response.status_code != 200 or "text/html" not in content_type.lower():
            return response
        try:
            html = response.get_data(as_text=True)
        except (RuntimeError, UnicodeDecodeError):
            return response
        if "<form" not in html.lower():
            return response
        token = escape(csrf_token(), quote=True)
        hidden = f'<input type="hidden" name="{TOKEN_FIELD}" value="{token}">'

        def repl(match):
            attrs = match.group("attrs")
            if POST_METHOD_RE.search(attrs):
                return match.group(0) + hidden
            return match.group(0)

        updated = FORM_RE.sub(repl, html)
        if updated != html:
            response.set_data(updated)
        return response

    return app
