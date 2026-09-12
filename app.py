import csv
import hmac
import io
import os
import re
import secrets
import sqlite3
import unicodedata
from io import BytesIO
from pathlib import Path

import requests
from flask import Flask, Response, flash, redirect, render_template, request, session, url_for
from pypdf import PdfReader
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "instance" / "sales.db"))

PREFECTURES = ["宮城県", "岩手県", "山形県", "福島県", "秋田県", "青森県"]
FACILITY_TYPES = ["民泊", "ホテル", "旅館", "ゲストハウス", "貸別荘", "運営会社", "その他"]
STATUSES = ["未連絡", "営業文作成済", "連絡済", "返信あり", "商談", "見積", "成約", "見送り"]
BOOL_FIELDS = ["pet_friendly", "whole_house", "multiple_facilities", "wood_floor"]
MIYAGI_OFFICIAL_URL = "https://www.pref.miyagi.jp/documents/30180/kunigaidorain.pdf"
MIYAGI_LEGACY_URL = "https://www.pref.miyagi.jp/documents/30180/20260319.pdf"
MIYAGI_SOURCE_URL = os.environ.get("MIYAGI_SOURCE_URL", MIYAGI_OFFICIAL_URL)
MIYAGI_SOURCE_TYPE = "宮城県 住宅宿泊事業届出施設一覧"
MAX_PDF_BYTES = 20 * 1024 * 1024


def credentials_match(value, expected):
    return hmac.compare_digest(value.encode("utf-8"), expected.encode("utf-8"))


def normalize_address(value):
    """Normalize Japanese address text enough for practical duplicate checks."""
    text = unicodedata.normalize("NFKC", value or "").strip().lower()
    text = re.sub(r"[\s\u3000]+", "", text)
    text = re.sub(r"[‐‑‒–—―ー−﹣－]+", "-", text)
    return text


def candidate_key(prefecture, city, address):
    return "|".join(normalize_address(part) for part in (prefecture, city, address))


def extract_city(address):
    text = (address or "").strip()
    match = re.match(r"^(.+?郡.+?[町村]|.+?[市区町村])", text)
    return match.group(1) if match else ""


def parse_miyagi_pdf(pdf_bytes):
    """Extract only published lodging addresses from the Miyagi PDF."""
    reader = PdfReader(BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    addresses = []
    seen = set()
    for raw_line in text.splitlines():
        line = unicodedata.normalize("NFKC", raw_line).strip()
        line = re.sub(r"^\s*\d+[.)]?\s*", "", line)
        if not line or "届出住宅所在地" in line or line.startswith("※"):
            continue
        if not re.match(r"^(.+?郡.+?[町村]|.+?[市区町村])", line):
            continue
        normalized = normalize_address(line)
        if normalized in seen:
            continue
        seen.add(normalized)
        addresses.append(line)
    return addresses


def miyagi_source_urls(configured_url=None):
    """Return source candidates with the stable official URL always first."""
    urls = [MIYAGI_OFFICIAL_URL]
    for value in (configured_url, MIYAGI_SOURCE_URL, MIYAGI_LEGACY_URL):
        if value and value not in urls:
            urls.append(value)
    return urls


def download_pdf(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0 Safari/537.36"
        ),
        "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
    }
    response = requests.get(url, timeout=20, stream=True, headers=headers, allow_redirects=True)
    response.raise_for_status()
    data = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        data.extend(chunk)
        if len(data) > MAX_PDF_BYTES:
            raise ValueError("PDFのサイズが20MBを超えています。")
    pdf_bytes = bytes(data)
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("取得したファイルがPDF形式ではありません。")
    return pdf_bytes


def fetch_miyagi_candidates(source_url=None):
    """Fetch candidates with safe fallbacks and return (addresses, actual_source_url)."""
    errors = []
    for url in miyagi_source_urls(source_url):
        try:
            addresses = parse_miyagi_pdf(download_pdf(url))
            if not addresses:
                raise ValueError("所在地を抽出できませんでした。")
            return addresses, url
        except (requests.RequestException, ValueError, OSError) as exc:
            errors.append(f"{type(exc).__name__}:{url}")
    raise ValueError(
        "宮城県の公開資料を取得できませんでした。現在、複数の公式URLを自動確認しました。"
        "時間を置いて再度お試しください。"
    )


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
        MIYAGI_SOURCE_URL=MIYAGI_SOURCE_URL,
    )
    if test_config:
        app.config.update(test_config)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    username = app.config["APP_USERNAME"]
    password = app.config["APP_PASSWORD"]
    if bool(username) != bool(password):
        raise RuntimeError("APP_USERNAME and APP_PASSWORD must be set together")

    @app.before_request
    def require_login():
        if not username or request.endpoint in {"healthz", "login", "static"}:
            return None
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return None

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("logged_in") or not username:
            return redirect(url_for("index"))
        error = None
        if request.method == "POST":
            supplied_username = request.form.get("username", "")
            supplied_password = request.form.get("password", "")
            credentials_valid = all((
                credentials_match(supplied_username, username),
                credentials_match(supplied_password, password),
            ))
            if credentials_valid:
                session.clear()
                session["logged_in"] = True
                return redirect(url_for("index"))
            error = "ユーザー名またはパスワードが違います"
        return render_template("login.html", error=error)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

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
            facility_columns = {row[1] for row in con.execute("PRAGMA table_info(facilities)").fetchall()}
            if "address" not in facility_columns:
                con.execute("ALTER TABLE facilities ADD COLUMN address TEXT DEFAULT ''")
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
            "name", "company_name", "prefecture", "city", "address", "facility_type", "official_url",
            "phone", "email", "contact_url", "source_url", "notes", "status"
        ]}
        data.update({key: int(request.form.get(key) == "on") for key in BOOL_FIELDS})
        return data

    @app.route("/")
    def index():
        filters = {key: request.args.get(key, "").strip() for key in ["q", "prefecture", "priority", "status"]}
        sql, params = "SELECT * FROM facilities WHERE 1=1", []
        if filters["q"]:
            sql += " AND (name LIKE ? OR company_name LIKE ? OR city LIKE ? OR address LIKE ? OR notes LIKE ?)"
            params += [f"%{filters['q']}%"] * 5
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

    @app.route("/collect", methods=["GET", "POST"])
    def collect_candidates():
        stats = None
        source_url = MIYAGI_OFFICIAL_URL
        if request.method == "POST":
            try:
                addresses, actual_source_url = fetch_miyagi_candidates(app.config["MIYAGI_SOURCE_URL"])
                new_count = 0
                duplicate_count = 0
                with db() as con:
                    for address in addresses:
                        city = extract_city(address)
                        key = candidate_key("宮城県", city, address)
                        existing = con.execute("SELECT id FROM lead_candidates WHERE normalized_key=?", (key,)).fetchone()
                        if existing:
                            duplicate_count += 1
                            continue
                        con.execute(
                            """INSERT INTO lead_candidates
                               (name,prefecture,city,address,official_url,source_url,source_type,normalized_key,status)
                               VALUES ('','宮城県',?,?,?,?,?,?, 'pending')""",
                            (city, address, "", actual_source_url, MIYAGI_SOURCE_TYPE, key),
                        )
                        new_count += 1
                stats = {"total": len(addresses), "new": new_count, "duplicate": duplicate_count}
                flash(f"{len(addresses)}件を確認し、新規{new_count}件を候補へ追加しました。", "success")
            except ValueError as exc:
                app.logger.warning("Miyagi source fetch failed: %s", exc)
                flash(str(exc), "error")
        with db() as con:
            pending_count = con.execute("SELECT COUNT(*) FROM lead_candidates WHERE status='pending'").fetchone()[0]
        return render_template("collect.html", source_url=source_url, source_type=MIYAGI_SOURCE_TYPE,
                               stats=stats, pending_count=pending_count)

    @app.get("/candidates")
    def candidates():
        status = request.args.get("status", "pending")
        if status not in {"pending", "promoted", "excluded", "all"}:
            status = "pending"
        sql = "SELECT * FROM lead_candidates"
        params = []
        if status != "all":
            sql += " WHERE status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC, id DESC"
        with db() as con:
            rows = con.execute(sql, params).fetchall()
        return render_template("candidates.html", candidates=rows, selected_status=status)

    @app.post("/candidates/<int:candidate_id>/promote")
    def promote_candidate(candidate_id):
        with db() as con:
            candidate = con.execute("SELECT * FROM lead_candidates WHERE id=?", (candidate_id,)).fetchone()
            if not candidate:
                return ("Not found", 404)
            if candidate["status"] == "excluded":
                flash("除外済み候補は営業リストへ登録できません。", "error")
                return redirect(url_for("candidates"))
            target_key = candidate_key(candidate["prefecture"], candidate["city"], candidate["address"])
            existing_facility = None
            for facility in con.execute(
                "SELECT id,prefecture,city,address FROM facilities WHERE prefecture=?",
                (candidate["prefecture"],),
            ).fetchall():
                if candidate_key(facility["prefecture"], facility["city"], facility["address"]) == target_key:
                    existing_facility = facility
                    break
            if existing_facility:
                facility_id = existing_facility["id"]
            else:
                data = {
                    "facility_type": "民泊", "pet_friendly": 0, "whole_house": 0,
                    "multiple_facilities": 0, "wood_floor": 0,
                }
                priority, reason = calculate_priority(data)
                display_name = candidate["name"] or candidate["address"]
                cursor = con.execute(
                    """INSERT INTO facilities
                       (name,company_name,prefecture,city,address,facility_type,official_url,phone,email,contact_url,
                        pet_friendly,whole_house,multiple_facilities,wood_floor,source_url,notes,priority,priority_reason,status)
                       VALUES (?,?,?,?,?,'民泊',?,'','','',0,0,0,0,?,'',?,?,'未連絡')""",
                    (display_name, "", candidate["prefecture"], candidate["city"], candidate["address"],
                     candidate["official_url"], candidate["source_url"], priority, reason),
                )
                facility_id = cursor.lastrowid
            con.execute(
                "UPDATE lead_candidates SET status='promoted', matched_facility_id=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (facility_id, candidate_id),
            )
        flash("候補を営業リストへ登録しました。", "success")
        return redirect(url_for("candidates"))

    @app.post("/candidates/<int:candidate_id>/exclude")
    def exclude_candidate(candidate_id):
        with db() as con:
            candidate = con.execute("SELECT id,status FROM lead_candidates WHERE id=?", (candidate_id,)).fetchone()
            if not candidate:
                return ("Not found", 404)
            if candidate["status"] != "promoted":
                con.execute(
                    "UPDATE lead_candidates SET status='excluded', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (candidate_id,),
                )
        flash("候補を除外しました。", "success")
        return redirect(url_for("candidates"))

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
        fields = ["施設名", "運営会社", "都道府県", "市区町村", "住所", "施設種別", "優先度", "判定理由", "ステータス", "公式URL", "電話", "メール", "問い合わせURL", "メモ"]
        writer = csv.writer(output)
        writer.writerow(fields)
        for row in rows:
            writer.writerow([row[k] for k in ["name", "company_name", "prefecture", "city", "address", "facility_type", "priority", "priority_reason", "status", "official_url", "phone", "email", "contact_url", "notes"]])
        return Response(output.getvalue(), mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=facilities.csv"})

    app.jinja_env.globals.update(statuses=STATUSES)
    app.init_db = init_db
    app.calculate_priority = calculate_priority
    app.normalize_address = normalize_address
    app.candidate_key = candidate_key
    app.extract_city = extract_city
    app.parse_miyagi_pdf = parse_miyagi_pdf
    app.fetch_miyagi_candidates = fetch_miyagi_candidates
    with app.app_context():
        init_db()
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
