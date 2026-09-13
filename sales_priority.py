import sqlite3
from flask import render_template, request

PREFECTURE_RANK = {"宮城県": 0, "山形県": 1, "岩手県": 2, "福島県": 3, "秋田県": 4, "青森県": 5}


def score_candidate(row):
    """Explainable sales-readiness score. Unknown data stays neutral, never positive."""
    score = 0
    reasons = []
    missing = []

    signals = [
        ("pet_friendly", 25, "ペット可"),
        ("whole_house", 20, "一棟貸し"),
        ("wood_floor", 20, "木質床"),
        ("multiple_facilities", 15, "複数施設運営"),
    ]
    for key, points, label in signals:
        if row[key]:
            score += points
            reasons.append(f"{label} +{points}")

    if row["company_name"]:
        score += 8
        reasons.append("運営会社確認 +8")
    else:
        missing.append("運営会社")

    if row["phone"] or row["email"] or row["contact_url"]:
        score += 7
        reasons.append("連絡先あり +7")
    else:
        missing.append("連絡先")

    if row["official_url"]:
        score += 5
        reasons.append("根拠URLあり +5")
    else:
        missing.append("根拠URL")

    if row["research_status"] == "verified":
        score += 10
        reasons.append("確認済 +10")
    elif row["research_status"] == "unresearched":
        missing.append("調査")

    # Regional rollout preference is deliberately small: business fit dominates geography.
    region_bonus = {"宮城県": 5, "山形県": 3, "岩手県": 3}.get(row["prefecture"], 0)
    if region_bonus:
        score += region_bonus
        reasons.append(f"地域優先 +{region_bonus}")

    score = min(score, 100)
    reachable = bool(row["phone"] or row["email"] or row["contact_url"])
    verified = row["research_status"] == "verified"

    if score >= 70 and reachable and verified:
        band, action = "S", "今すぐ営業文を作成"
    elif score >= 50 and reachable:
        band, action = "A", "根拠を最終確認して営業"
    elif score >= 30:
        band, action = "B", "不足情報を調査"
    else:
        band, action = "C", "後回し・追加調査"

    return {
        "score": score,
        "band": band,
        "reasons": reasons,
        "missing": missing,
        "action": action,
        "reachable": reachable,
    }


def register_sales_priority(app):
    @app.get("/sales-priority")
    def sales_priority():
        prefecture = request.args.get("prefecture", "").strip()
        band_filter = request.args.get("band", "").strip().upper()
        ready_only = request.args.get("ready", "") == "1"

        con = sqlite3.connect(app.config["DATABASE"])
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT * FROM lead_candidates WHERE status='pending' ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        finally:
            con.close()

        ranked = []
        for row in rows:
            result = score_candidate(row)
            item = {"candidate": row, **result}
            if prefecture and row["prefecture"] != prefecture:
                continue
            if band_filter in {"S", "A", "B", "C"} and result["band"] != band_filter:
                continue
            if ready_only and result["band"] not in {"S", "A"}:
                continue
            ranked.append(item)

        ranked.sort(key=lambda item: (
            {"S": 0, "A": 1, "B": 2, "C": 3}[item["band"]],
            -item["score"],
            PREFECTURE_RANK.get(item["candidate"]["prefecture"], 9),
            item["candidate"]["id"],
        ))

        summary = {band: sum(1 for item in ranked if item["band"] == band) for band in "SABC"}
        return render_template(
            "sales_priority.html",
            ranked=ranked,
            summary=summary,
            selected_prefecture=prefecture,
            selected_band=band_filter,
            ready_only=ready_only,
            prefectures=["宮城県", "山形県", "岩手県", "福島県", "秋田県", "青森県"],
        )
