import sqlite3
from datetime import datetime, timezone
from urllib.parse import quote

from flask import abort, flash, redirect, render_template, request

from sales_action import build_sales_draft, recommend_theme

FOLLOW_UP_DAYS = 5

BUSINESS_SEEDS = (
    {
        "name": "宮城民泊運営代行株式会社",
        "company_name": "宮城民泊運営代行株式会社",
        "prefecture": "宮城県",
        "city": "仙台市",
        "address": "宮城県仙台市太白区山田本町21-7",
        "official_url": "https://minpaku-agency.com/management/miyagi/",
        "phone": "0120-233-230",
        "email": "",
        "contact_url": "https://minpaku-agency.com/management/miyagi/",
        "source_url": "https://minpaku-agency.com/management/miyagi/",
        "notes": "民泊運営・清掃・物件管理。複数物件を所有する管理会社の運営代行にも対応。",
    },
    {
        "name": "民泊パートナー宮城",
        "company_name": "合同会社SOL COMODA",
        "prefecture": "宮城県",
        "city": "仙台市",
        "address": "宮城県仙台市",
        "official_url": "https://minpaku-miyagi.com/",
        "phone": "090-8196-7107",
        "email": "norik@kdn.biglobe.ne.jp",
        "contact_url": "https://minpaku-miyagi.com/",
        "source_url": "https://minpaku-partner.com/intro/",
        "notes": "民泊パートナー運営会社。全国47エリア展開を掲げ、清掃・メンテナンス手配にも対応。",
    },
    {
        "name": "Minpaku Resort 仙台",
        "company_name": "Minpaku Resort",
        "prefecture": "宮城県",
        "city": "仙台市",
        "address": "宮城県仙台市",
        "official_url": "https://www.minpaku-resort.com/sendai/",
        "phone": "",
        "email": "",
        "contact_url": "https://www.minpaku-resort.com/sendai/",
        "source_url": "https://www.minpaku-resort.com/",
        "notes": "全国対応の民泊運営・清掃代行。物件管理、清掃、ゲスト対応、設備不具合・緊急トラブル対応を案内。",
    },
    {
        "name": "HTP 民泊ホテル運営",
        "company_name": "株式会社エイチ・ティー・プランニング",
        "prefecture": "宮城県",
        "city": "仙台市",
        "address": "宮城県仙台市宮城野区宮城野1丁目12-15 松栄宮城野ビル5F",
        "official_url": "https://www.h-t-p.co.jp/minpaku/",
        "phone": "022-292-5181",
        "email": "info@h-t-p.co.jp",
        "contact_url": "https://www.h-t-p.co.jp/contact/",
        "source_url": "https://www.h-t-p.co.jp/minpaku/",
        "notes": "住宅宿泊管理業登録。仙台・宮城・岩手で複数の民泊ホテル管理実績を公開。",
    },
    {
        "name": "BnBアソシエイト",
        "company_name": "合同会社Bebop",
        "prefecture": "宮城県",
        "city": "利府町",
        "address": "宮城県宮城郡利府町赤沼字中倉51-5 OHLM2管理棟",
        "official_url": "https://bnb-associate.bebop-llc.jp/",
        "phone": "",
        "email": "",
        "contact_url": "https://bnb-associate.bebop-llc.jp/",
        "source_url": "https://bnb-associate.bebop-llc.jp/",
        "notes": "仙台・東北対応の民泊運用代行。清掃スケジュール調整、24時間駆けつけ、インテリア提案に対応。住宅宿泊管理業登録。",
    },
    {
        "name": "Blue First 貸別荘運営",
        "company_name": "株式会社Blue First",
        "prefecture": "宮城県",
        "city": "川崎町",
        "address": "宮城県柴田郡川崎町大字前川字六方山3-170",
        "official_url": "https://www.blue-first.net/",
        "phone": "090-9034-1710",
        "email": "",
        "contact_url": "https://www.blue-first.net/",
        "source_url": "https://www.blue-first.net/about/",
        "notes": "別荘・空き家管理、貸別荘運営、リノベーションを実施。青根エリアで複数の貸別荘を案内。",
    },
    {
        "name": "ガイアリゾート",
        "company_name": "株式会社ガイア",
        "prefecture": "宮城県",
        "city": "白石市",
        "address": "宮城県白石市旭町1丁目5番7号2F",
        "official_url": "https://gaia-resort.net/",
        "phone": "0224-26-8892",
        "email": "",
        "contact_url": "https://gaia-resort.net/",
        "source_url": "https://gaia-resort.net/privacy-policy/",
        "notes": "宮城蔵王を中心に多数の一棟貸し・貸別荘を運営。ペット可、温泉付きなど複数タイプを展開。",
    },
    {
        "name": "たびの邸宅",
        "company_name": "株式会社たびのレシピ",
        "prefecture": "宮城県",
        "city": "仙台市",
        "address": "宮城県",
        "official_url": "https://www.tabinoteitaku.jp/",
        "phone": "",
        "email": "",
        "contact_url": "https://www.tabinoteitaku.jp/",
        "source_url": "https://www.tabinoteitaku.jp/",
        "notes": "宮城県内多数と山形県でも一棟貸し・コテージ・貸別荘・コンドミニアムをプロデュース・運営。",
    },
)


def _connect(database):
    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    return con


def _ensure_activity_table(database):
    with _connect(database) as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS sales_activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id INTEGER NOT NULL,
                activity_type TEXT NOT NULL,
                theme_key TEXT DEFAULT '',
                channel TEXT DEFAULT '',
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (candidate_id) REFERENCES lead_candidates(id)
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_sales_activities_candidate ON sales_activities(candidate_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sales_activities_type ON sales_activities(activity_type)")


def _seed_key(url):
    return "business|" + url.rstrip("/").lower()


def seed_businesses(database):
    inserted = 0
    with _connect(database) as con:
        for item in BUSINESS_SEEDS:
            key = _seed_key(item["official_url"])
            exists = con.execute("SELECT id FROM lead_candidates WHERE normalized_key=?", (key,)).fetchone()
            if exists:
                continue
            con.execute(
                """INSERT INTO lead_candidates
                   (name,company_name,prefecture,city,address,official_url,phone,email,contact_url,
                    research_status,research_notes,source_url,source_type,normalized_key,status)
                   VALUES (?,?,?,?,?,?,?,?,?,'verified',?,?,?,?,'pending')""",
                (
                    item["name"], item["company_name"], item["prefecture"], item["city"], item["address"],
                    item["official_url"], item["phone"], item["email"], item["contact_url"], item["notes"],
                    item["source_url"], "事業者発掘", key,
                ),
            )
            inserted += 1
    return inserted


def _latest_activity(rows):
    by_candidate = {}
    for row in rows:
        by_candidate.setdefault(row["candidate_id"], []).append(row)
    return by_candidate


def _stage(candidate, activities, now):
    types = {row["activity_type"] for row in activities}
    if "won" in types or "lost" in types:
        return "done"
    if "replied" in types:
        return "replied"
    sent = [row for row in activities if row["activity_type"] == "sent"]
    if sent:
        sent_at = datetime.fromisoformat(sent[0]["created_at"].replace(" ", "T") + "+00:00")
        if (now - sent_at).days >= FOLLOW_UP_DAYS:
            return "followup"
        return "sent"
    if candidate["email"] or candidate["contact_url"] or candidate["phone"]:
        return "new"
    return "research"


def _mailto(candidate, draft):
    if not candidate["email"]:
        return ""
    subject = "宿泊施設の傷補修・コーティングのご提案"
    return f"mailto:{candidate['email']}?subject={quote(subject)}&body={quote(draft)}"


def build_flow(database):
    with _connect(database) as con:
        candidates = con.execute(
            """SELECT * FROM lead_candidates
               WHERE source_type='事業者発掘' OR company_name<>''
               ORDER BY updated_at DESC, id DESC"""
        ).fetchall()
        activities = con.execute(
            "SELECT * FROM sales_activities ORDER BY created_at DESC, id DESC"
        ).fetchall()
    activity_map = _latest_activity(activities)
    now = datetime.now(timezone.utc)
    groups = {key: [] for key in ("new", "sent", "replied", "followup", "done", "research")}
    for candidate in candidates:
        history = activity_map.get(candidate["id"], [])
        stage = _stage(candidate, history, now)
        theme = recommend_theme(candidate)
        draft = build_sales_draft(candidate, theme)
        groups[stage].append({
            "candidate": candidate,
            "draft": draft,
            "theme": theme,
            "mailto": _mailto(candidate, draft),
            "last_activity": history[0] if history else None,
        })
    return groups


def register_simple_sales_flow(app):
    _ensure_activity_table(app.config["DATABASE"])

    @app.get("/sales-flow")
    def simple_sales_flow():
        return render_template(
            "simple_sales_flow.html",
            groups=build_flow(app.config["DATABASE"]),
            follow_up_days=FOLLOW_UP_DAYS,
        )

    @app.post("/sales-flow/discover")
    def simple_sales_discover():
        inserted = seed_businesses(app.config["DATABASE"])
        flash(f"営業先候補を{inserted}社追加しました。" if inserted else "初期営業先はすでにリストに入っています。", "success")
        return redirect("/sales-flow")

    @app.post("/sales-flow/<int:candidate_id>/activity")
    def simple_sales_activity(candidate_id):
        activity_type = request.form.get("activity_type", "").strip()
        if activity_type not in {"sent", "replied", "won", "lost"}:
            abort(400)
        channel = request.form.get("channel", "").strip()
        if channel not in {"email", "form", "phone", "other"}:
            channel = "other"
        note = request.form.get("note", "").strip()[:1000]
        with _connect(app.config["DATABASE"]) as con:
            candidate = con.execute("SELECT id FROM lead_candidates WHERE id=?", (candidate_id,)).fetchone()
            if not candidate:
                abort(404)
            con.execute(
                "INSERT INTO sales_activities (candidate_id,activity_type,channel,note) VALUES (?,?,?,?)",
                (candidate_id, activity_type, channel, note),
            )
        labels = {"sent": "送信済み", "replied": "返信あり", "won": "成約", "lost": "見送り"}
        flash(f"{labels[activity_type]}として記録しました。", "success")
        return redirect("/sales-flow")

    return app
