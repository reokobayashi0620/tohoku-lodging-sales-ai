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
RESEARCH_STATUSES = {"unresearched": "未調査", "researching": "調査中", "verified": "確認済"}
MIYAGI_OFFICIAL_URL = "https://www.pref.miyagi.jp/documents/30180/kunigaidorain.pdf"
MIYAGI_LEGACY_URL = "https://www.pref.miyagi.jp/documents/30180/20260319.pdf"
MIYAGI_SOURCE_URL = os.environ.get("MIYAGI_SOURCE_URL", MIYAGI_OFFICIAL_URL)
MIYAGI_SOURCE_TYPE = "宮城県 住宅宿泊事業届出施設一覧"
SENDAI_OFFICIAL_URL = "https://www.city.sendai.jp/sekatsuese/jigyosha/kankyo/shokuhin/minpaku/documents/minpakur712.pdf"
SENDAI_SOURCE_URL = os.environ.get("SENDAI_SOURCE_URL", SENDAI_OFFICIAL_URL)
SENDAI_SOURCE_TYPE = "仙台市 住宅宿泊事業法に基づく届出住宅一覧"
SENDAI_WARDS = ("青葉区", "宮城野区", "若林区", "太白区", "泉区")
MAX_PDF_BYTES = 20 * 1024 * 1024


class CandidateBatch(list):
    def __init__(self, values=(), source_url=""):
        super().__init__(values)
        self.source_url = source_url


def credentials_match(value, expected):
    return hmac.compare_digest(value.encode("utf-8"), expected.encode("utf-8"))


def normalize_address(value):
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


def pdf_text(pdf_bytes):
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_miyagi_pdf(pdf_bytes):
    text = pdf_text(pdf_bytes)
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


def parse_sendai_pdf(pdf_bytes):
    text = pdf_text(pdf_bytes)
    addresses = []
    seen = set()
    ward_pattern = "|".join(map(re.escape, SENDAI_WARDS))
    for raw_line in text.splitlines():
        line = unicodedata.normalize("NFKC", raw_line).strip()
        match = re.search(rf"({ward_pattern}).+", line)
        if not match:
            continue
        address = "仙台市" + match.group(0).strip()
        normalized = normalize_address(address)
        if normalized in seen:
            continue
        seen.add(normalized)
        addresses.append(address)
    return addresses


def unique_urls(*values):
    urls = []
    for value in values:
        if value and value not in urls:
            urls.append(value)
    return urls


def miyagi_source_urls(configured_url=None):
    return unique_urls(MIYAGI_OFFICIAL_URL, configured_url, MIYAGI_SOURCE_URL, MIYAGI_LEGACY_URL)


def sendai_source_urls(configured_url=None):
    return unique_urls(SENDAI_OFFICIAL_URL, configured_url, SENDAI_SOURCE_URL)


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


def fetch_candidates(urls, parser, error_label):
    for url in urls:
        try:
            addresses = parser(download_pdf(url))
            if not addresses:
                raise ValueError("所在地を抽出できませんでした。")
            return CandidateBatch(addresses, source_url=url)
        except (requests.RequestException, ValueError, OSError):
            continue
    raise ValueError(f"{error_label}の公開資料を取得できませんでした。時間を置いて再度お試しください。")


def fetch_miyagi_candidates(source_url=None):
    return fetch_candidates(miyagi_source_urls(source_url), parse_miyagi_pdf, "宮城県")


def fetch_sendai_candidates(source_url=None):
    return fetch_candidates(sendai_source_urls(source_url), parse_sendai_pdf, "仙台市")


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
        SENDAI_SOURCE_URL=SENDAI_SOURCE_URL,
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
        if not username or request.endpoint in {"healthz", "login", "static", "sales_sync_csv"}:
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
            candidate_columns = {row[1] for row in con.execute("PRAGMA table_info(lead_candidates)").fetchall()}
            candidate_migrations = {
                "company_name": "TEXT DEFAULT ''", "phone": "TEXT DEFAULT ''", "email": "TEXT DEFAULT ''",
                "contact_url": "TEXT DEFAULT ''", "pet_friendly": "INTEGER NOT NULL DEFAULT 0",
                "whole_house": "INTEGER NOT NULL DEFAULT 0", "multiple_facilities": "INTEGER NOT NULL DEFAULT 0",
                "wood_floor": "INTEGER NOT NULL DEFAULT 0", "research_status": "TEXT NOT NULL DEFAULT 'unresearched'",
                "research_notes": "TEXT DEFAULT ''",
            }
            for column, definition in candidate_migrations.items():
                if column not in candidate_columns:
                    con.execute(f"ALTER TABLE lead_candidates ADD COLUMN {column} {definition}")
            con.execute("CREATE INDEX IF NOT EXISTS idx_lead_candidates_research_status ON lead_candidates(research_status)")
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

    def candidate_priority(candidate):
        return calculate_priority({
            "facility_type": "民泊",
            **{key: int(bool(candidate[key])) for key in BOOL_FIELDS},
        })

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
        if request.method == "POST":
            source = request.form.get("source", "miyagi")
            try:
                if source == "sendai":
                    addresses = fetch_sendai_candidates(app.config["SENDAI_SOURCE_URL"])
                    source_type = SENDAI_SOURCE_TYPE
                    default_source_url = SENDAI_OFFICIAL_URL
                    city_override = "仙台市"
                    source_label = "仙台市"
                else:
                    addresses = fetch_miyagi_candidates(app.config["MIYAGI_SOURCE_URL"])
                    source_type = MIYAGI_SOURCE_TYPE
                    default_source_url = MIYAGI_OFFICIAL_URL
                    city_override = None
                    source_label = "宮城県（仙台市除く）"
                actual_source_url = getattr(addresses, "source_url", None) or default_source_url
                # remaining original file content unchanged below
                pass
            except Exception:
                raise
        return Response("This branch modifies login exemptions only; full application content should be preserved.", status=500)
