import csv
import hmac
import io
import os
import secrets
import sqlite3
from pathlib import Path

from flask import Flask, Response, flash, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "instance" / "sales.db"))

PREFECTURES = ["宮城県", "岩手県", "山形県", "福島県", "秋田県", "青森県"]
FACILITY_TYPES = ["民泊", "ホテル", "旅館", "ゲストハウス", "貸別荘", "運営会社", "その他"]
STATUSES = ["未連絡", "営業文作成済", "連絡済", "返信あり", "商談", "見積", "成約", "見送り"]
BOOL_FIELDS = ["pet_friendly", "whole_house", "multiple_facilities", "wood_floor"]


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", secrets.token_hex(32)),
        DATABASE=DATABASE,
        APP_USERNAME=os.environ.get("APP_USERNAME", ""),
        APP_PASSWORD=os.environ.get("APP_PASSWORD", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").lower() in {"1", "true", "yes"},
    )
    if test_config:
        app.config.update(test_config)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    username = app.config["APP_USERNAME"]
    password = app.config["APP_PASSWORD"]
    if bool(username) != bool(password):
        raise RuntimeError("APP_USERNAME and APP_PASSWORD must be set together")

    @app.before_request
    def require_basic_auth():
        if not username or request.endpoint == "healthz":
            return None
        auth = request.authorization
        valid = (
            auth is not None
            and hmac.compare_digest(auth.username or "", username)
            and hmac.compare_digest(auth.password or "", password)
        )
        if not valid:
            return Response(
                "Authentication required", 401,
                {"WWW-Authenticate": 'Basic realm="Tohoku Sales", charset="UTF-8"'},
            )
        return None

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    def db():
        connection = sqlite3.connect(app.config["DATABASE"])
        connection.row_factory = sqlite3.Row
        return connection

    def init_db():
        Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
        with db() as con:
            con.executescript((BASE_DIR / "schema.sql").read_text(encoding="utf-8"))
            count = con.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]
            if count == 0:
                con.executescript((BASE_DIR / "sample_data.sql").read_text(encoding="utf-8"))

    def calculate_priority(data):
        score = sum(bool(data.get(key)) for key in BOOL_FIELDS)
        lodging = data.get("facility_type") in {"民泊", "ホテル", "旅館", "ゲストハウス", "貸別荘"}
        reasons = []
        labels = {"pet_friendly": "ペット可", "whole_house": "一棟貸し", "multiple_facilities": "複数施設運営", "wood_floor": "木質床の可能性あり"}
        reasons.extend(label for key, label in labels.items() if data.get(key))
        if lodging:
            reasons.append("宿泊施設")
        if lodging and score >= 3:
            return "S", "、".join(reasons) + "のため、補修需要との適合度が特に高い"
        if (lodging and score >= 1) or data.get("multiple_facilities"):
            return "A", "、".join(reasons) + "のため、営業価値が高い"
        if lodging:
            return "B", "一般的な宿泊施設として補修提案の余地がある"
        return "C", "判断材料が少ないため、追加調査が必要"

    def form_data():
        data = {key: request.form.get(key, "").strip() for key in [
            "name", "company_name", "prefecture", "city", "facility_type", "official_url",
            "phone", "email", "contact_url", "source_url", "notes", "status"
        ]}
        data.update({key: int(request.form.get(key) == "on") for key in BOOL_FIELDS})
        return data

    @app.route("/")
    def index():
        filters = {key: request.args.get(key, "").strip() for key in ["q", "prefecture", "priority", "status"]}
        sql, params = "SELECT * FROM facilities WHERE 1=1", []
        if filters["q"]:
            sql += " AND (name LIKE ? OR company_name LIKE ? OR city LIKE ? OR notes LIKE ?)"
            params += [f"%{filters['q']}%"] * 4
        for key in ["prefecture", "priority", "status"]:
            if filters[key]:
                sql += f" AND {key} = ?"
                params.append(filters[key])
        sql += " ORDER BY CASE priority WHEN 'S' THEN 1 WHEN 'A' THEN 2 WHEN 'B' THEN 3 ELSE 4 END, updated_at DESC"
        with db() as con:
            facilities = con.execute(sql, params).fetchall()
            summary = dict(con.execute("SELECT priority, COUNT(*) count FROM facilities GROUP BY priority").fetchall())
        return render_template("index.html", facilities=facilities, filters=filters, summary=summary,
                               prefectures=PREFECTURES, statuses=STATUSES)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.route("/facilities/new", methods=["GET", "POST"])
    @app.route("/facilities/<int:facility_id>/edit", methods=["GET", "POST"])
    def facility_form(facility_id=None):
        facility = None
        if facility_id:
            with db() as con:
                facility = con.execute("SELECT * FROM facilities WHERE id=?", (facility_id,)).fetchone()
        if request.method == "POST":
            data = form_data()
            if not data["name"] or data["prefecture"] not in PREFECTURES:
                flash("施設名と東北6県の都道府県は必須です。", "error")
                return render_template("form.html", facility=data, prefectures=PREFECTURES,
                                       facility_types=FACILITY_TYPES, statuses=STATUSES)
            data["priority"], data["priority_reason"] = calculate_priority(data)
            columns = list(data)
            with db() as con:
                if facility_id:
                    assignments = ",".join(f"{column}=?" for column in columns)
                    con.execute(f"UPDATE facilities SET {assignments}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                                [data[c] for c in columns] + [facility_id])
                else:
                    placeholders = ",".join("?" for _ in columns)
                    con.execute(f"INSERT INTO facilities ({','.join(columns)}) VALUES ({placeholders})", [data[c] for c in columns])
            flash("施設情報を保存し、優先度を自動判定しました。", "success")
            return redirect(url_for("index"))
        return render_template("form.html", facility=facility, prefectures=PREFECTURES,
                               facility_types=FACILITY_TYPES, statuses=STATUSES)

    @app.post("/facilities/<int:facility_id>/status")
    def update_status(facility_id):
        status = request.form.get("status")
        if status in STATUSES:
            with db() as con:
                con.execute("UPDATE facilities SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, facility_id))
        return redirect(request.referrer or url_for("index"))

    @app.route("/facilities/<int:facility_id>/message", methods=["GET", "POST"])
    def message(facility_id):
        with db() as con:
            facility = con.execute("SELECT * FROM facilities WHERE id=?", (facility_id,)).fetchone()
        if not facility:
            return ("Not found", 404)
        template_key = request.form.get("template", "standard")
        return render_template("message.html", facility=facility, selected=template_key)

    @app.route("/export.csv")
    def export_csv():
        with db() as con:
            rows = con.execute("SELECT * FROM facilities ORDER BY id").fetchall()
        output = io.StringIO()
        output.write("\ufeff")
        fields = ["施設名", "運営会社", "都道府県", "市区町村", "施設種別", "優先度", "判定理由", "ステータス", "公式URL", "電話", "メール", "問い合わせURL", "メモ"]
        writer = csv.writer(output)
        writer.writerow(fields)
        for row in rows:
            writer.writerow([row[k] for k in ["name", "company_name", "prefecture", "city", "facility_type", "priority", "priority_reason", "status", "official_url", "phone", "email", "contact_url", "notes"]])
        return Response(output.getvalue(), mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=facilities.csv"})

    app.jinja_env.globals.update(statuses=STATUSES)
    app.init_db = init_db
    app.calculate_priority = calculate_priority
    with app.app_context():
        init_db()
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
