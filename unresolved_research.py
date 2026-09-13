import sqlite3
from urllib.parse import quote_plus

from flask import render_template, request

from target_finder import PREFECTURES, is_official_registry_candidate, target_fit


def build_search_queries(row):
    address = (row["address"] or "").strip()
    prefecture = (row["prefecture"] or "").strip()
    city = (row["city"] or "").strip()
    base = address or f"{prefecture} {city}".strip()
    queries = [
        f'"{base}" 民泊',
        f'"{base}" 貸別荘 OR 一棟貸し OR ゲストハウス',
        f'"{base}" 宿泊 公式',
        f'"{base}" 運営会社 OR 会社概要 OR 特定商取引法',
    ]
    return [{"label": label, "query": query, "url": f"https://www.google.com/search?q={quote_plus(query)}"} for label, query in zip(
        ("民泊名を検索", "貸別荘・一棟貸しを検索", "公式サイトを検索", "運営会社を検索"), queries
    )]


def research_priority(row, missing_identity, missing_operator, missing_contact):
    fit = target_fit(row)
    score = fit["target_score"]
    reasons = []
    if row["name"]:
        score += 15
        reasons.append("施設名あり")
    if row["official_url"]:
        score += 20
        reasons.append("公式URLあり")
    if row["company_name"]:
        score += 20
        reasons.append("運営者あり")
    if row["phone"] or row["email"] or row["contact_url"]:
        score += 20
        reasons.append("連絡先あり")
    if row["pet_friendly"]:
        score += 15
        reasons.append("ペット可")
    if row["whole_house"]:
        score += 15
        reasons.append("一棟貸し")
    if row["wood_floor"]:
        score += 10
        reasons.append("木質床")
    if row["multiple_facilities"]:
        score += 10
        reasons.append("複数施設")

    missing_count = sum((missing_identity, missing_operator, missing_contact))
    score -= missing_count * 10
    return max(0, score), reasons


def unresolved_candidates(database, prefecture="", limit=100):
    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT * FROM lead_candidates WHERE status='pending' ORDER BY updated_at DESC, id DESC").fetchall()
    finally:
        con.close()

    items = []
    for row in rows:
        if prefecture and row["prefecture"] != prefecture:
            continue
        if not is_official_registry_candidate(row):
            continue
        missing_identity = not row["name"] or not row["official_url"]
        missing_operator = not row["company_name"]
        missing_contact = not (row["phone"] or row["email"] or row["contact_url"])
        if not (missing_identity or missing_operator or missing_contact):
            continue
        priority, reasons = research_priority(row, missing_identity, missing_operator, missing_contact)
        items.append({
            "candidate": row,
            "missing_identity": missing_identity,
            "missing_operator": missing_operator,
            "missing_contact": missing_contact,
            "research_priority": priority,
            "research_reasons": reasons,
            "searches": build_search_queries(row),
        })
    items.sort(key=lambda item: (-item["research_priority"], item["candidate"]["id"]))
    return items[:limit]


def register_unresolved_research(app):
    @app.get("/targets/unresolved")
    def unresolved_research():
        prefecture = request.args.get("prefecture", "").strip()
        if prefecture not in PREFECTURES:
            prefecture = ""
        items = unresolved_candidates(app.config["DATABASE"], prefecture)
        return render_template(
            "unresolved_research.html",
            items=items,
            prefectures=PREFECTURES,
            selected_prefecture=prefecture,
        )

    return app
