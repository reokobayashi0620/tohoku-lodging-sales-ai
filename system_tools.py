import os
import sqlite3
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

from flask import render_template, send_file


def _readiness(app):
    db_path = Path(app.config["DATABASE"])
    persistent = not str(db_path).startswith("/tmp/")
    return [
        {
            "label": "ログイン保護",
            "ok": bool(app.config.get("APP_USERNAME") and app.config.get("APP_PASSWORD")),
            "detail": "APP_USERNAME / APP_PASSWORD を設定" if not (app.config.get("APP_USERNAME") and app.config.get("APP_PASSWORD")) else "有効",
        },
        {
            "label": "固定SECRET_KEY",
            "ok": bool(os.environ.get("SECRET_KEY")),
            "detail": "環境変数 SECRET_KEY を設定" if not os.environ.get("SECRET_KEY") else "有効",
        },
        {
            "label": "HTTPS Cookie",
            "ok": bool(app.config.get("SESSION_COOKIE_SECURE")),
            "detail": "SESSION_COOKIE_SECURE=true を設定" if not app.config.get("SESSION_COOKIE_SECURE") else "有効",
        },
        {
            "label": "CSRF対策",
            "ok": bool(app.config.get("CSRF_ENABLED", True)),
            "detail": "有効" if app.config.get("CSRF_ENABLED", True) else "無効",
        },
        {
            "label": "DB永続化",
            "ok": persistent,
            "detail": str(db_path) if persistent else "現在は一時領域。実運用前に永続ディスクへ移行してください。",
        },
    ]


def register_system_tools(app):
    @app.get("/system")
    def system_status():
        checks = _readiness(app)
        return render_template(
            "system_status.html",
            checks=checks,
            ready=sum(1 for item in checks if item["ok"]),
            total=len(checks),
            database=str(app.config["DATABASE"]),
        )

    @app.get("/backup/database")
    def backup_database():
        source_path = Path(app.config["DATABASE"])
        source_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix="sales-backup-", suffix=".sqlite3")
        os.close(fd)
        try:
            source = sqlite3.connect(source_path)
            target = sqlite3.connect(temp_path)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
            data = Path(temp_path).read_bytes()
        finally:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return send_file(
            BytesIO(data),
            mimetype="application/vnd.sqlite3",
            as_attachment=True,
            download_name=f"tohoku-repair-sales-{stamp}.sqlite3",
        )

    return app
