import sqlite3

from flask import render_template, request

from sales_priority import score_candidate

PREFECTURES = ["宮城県", "山形県", "岩手県", "福島県", "秋田県", "青森県"]

TARGET_TERMS = (
    "民泊", "貸別荘", "一棟貸", "一棟", "ヴィラ", "villa", "コテージ", "cottage",
    "vacation rental", "vacation house", "ゲストハウス", "guesthouse", "古民家",
)
OFFICIAL_TERMS = ("届出", "許可", "自治体", "県", "市", "町", "村", "公式")
PET_TERMS = ("ペット", "犬", "dog", "pet")


def _value(row, key, default=""):
    try:
        value = row[key]
    except (KeyError, IndexError):
        return default
    return value if value is not None else default


def is_osm_candidate(row):
    return "openstreetmap" in str(_value(row, "source_type")).lower()


def is_official_registry_candidate(row):
    source_type = str(_value(row, "source_type"))
    source_url = str(_value(row, "source_url"))
    haystack = f"{source_type} {source_url}".lower()
    official_domain = any(token in haystack for token in (".go.jp", "pref.", "city.", "lg.jp"))
    official_label = any(term in source_type for term in OFFICIAL_TERMS)
    return (official_domain or official_label) and not is_osm_candidate(row)


def target_fit(row):
    base = score_candidate(row)
    text = " ".join(str(_value(row, key)) for key in (
        "name", "company_name", "research_notes", "source_type", "official_url"
    )).lower()

    fit = 0
    reasons = []
    if is_official_registry_candidate(row):
        fit += 25
        reasons.append("自治体・届出系ソース +25")
    elif not is_osm_candidate(row):
        fit += 10
        reasons.append("非OSMソース +10")
    else:
        fit -= 20
        reasons.append("OSM一般宿泊POI -20")

    if any(term.lower() in text for term in TARGET_TERMS):
        fit += 25
        reasons.append("民泊・貸別荘系キーワード +25")
    if _value(row, "whole_house"):
        fit += 20
        reasons.append("一棟貸し +20")
    if _value(row, "pet_friendly") or any(term in text for term in PET_TERMS):
        fit += 20
        reasons.append("ペット需要候補 +20")
    if _value(row, "wood_floor"):
        fit += 15
        reasons.append("木質床 +15")
    if _value(row, "multiple_facilities"):
        fit += 15
        reasons.append("複数施設運営 +15")
    if _value(row, "company_name"):
        fit += 10
        reasons.append("運営会社特定済み +10")
    if _value(row, "phone") or _value(row, "email") or _value(row, "contact_url"):
        fit += 10
        reasons.append("営業連絡先あり +10")

    identity_known = bool(_value(row, "name"))
    site_known = bool(_value(row, "official_url"))
    operator_known = bool(_value(row, "company_name"))
    contact_known = bool(_value(row, "phone") or _value(row, "email") or _value(row, "contact_url"))
    sales_ready = identity_known and (site_known or operator_known) and contact_known

    if not identity_known:
        fit = min(fit, 35)
        reasons.append("施設名未特定: 営業対象確定前 -")
    if not (site_known or operator_known):
        fit = min(fit, 45)
        reasons.append("公式サイト・運営者未特定: 要調査 -")
    if not contact_known:
        fit = min(fit, 55)
        reasons.append("連絡先未特定: 営業準備未完了 -")

    fit = max(0, min(100, fit))
    if sales_ready and fit >= 70:
        target_band = "S"
    elif sales_ready and fit >= 50:
        target_band = "A"
    elif fit >= 30:
        target_band = "B"
    else:
        target_band = "C"

    return {
        **base,
        "target_score": fit,
        "target_band": target_band,
        "target_reasons": reasons,
        "sales_ready": sales_ready,
        "identity_known": identity_known,
        "operator_known": operator_known,
        "contact_known": contact_known,
    }


def find_targets(database, prefecture="", include_osm=False, limit=100):
    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT * FROM lead_candidates WHERE status='pending' ORDER BY updated_at DESC, id DESC"
        ).fetchall()
    finally:
        con.close()

    items = []
    for row in rows:
        if prefecture and _value(row, "prefecture") != prefecture:
            continue
        if not include_osm and is_osm_candidate(row):
            continue
        result = target_fit(row)
        items.append({"candidate": row, **result})

    items.sort(key=lambda item: (
        0 if item["sales_ready"] else 1,
        {"S": 0, "A": 1, "B": 2, "C": 3}[item["target_band"]],
        -item["target_score"],
        -item["score"],
        item["candidate"]["id"],
    ))
    return items[:limit]


def register_target_finder(app):
    @app.get("/targets")
    def target_finder():
        prefecture = request.args.get("prefecture", "").strip()
        if prefecture not in PREFECTURES:
            prefecture = ""
        include_osm = request.args.get("include_osm") == "1"
        targets = find_targets(app.config["DATABASE"], prefecture, include_osm=include_osm)
        summary = {band: sum(1 for item in targets if item["target_band"] == band) for band in "SABC"}
        ready_count = sum(1 for item in targets if item["sales_ready"])
        research_count = len(targets) - ready_count
        return render_template(
            "target_finder.html",
            targets=targets,
            summary=summary,
            ready_count=ready_count,
            research_count=research_count,
            prefectures=PREFECTURES,
            selected_prefecture=prefecture,
            include_osm=include_osm,
        )

    return app
