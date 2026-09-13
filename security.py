import hmac
import secrets

from flask import abort, request, session


def _token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def register_security(app):
    @app.context_processor
    def csrf_context():
        return {"csrf_token": _token}

    @app.before_request
    def csrf_protect():
        # Login POST is intentionally exempt: protection starts once an authenticated
        # session exists. Tests/dev without configured authentication are unaffected.
        if request.method != "POST" or not session.get("logged_in"):
            return None
        expected = session.get("csrf_token", "")
        supplied = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            abort(400, description="CSRF token validation failed")
        return None

    @app.after_request
    def production_security_headers(response):
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response

    return app
