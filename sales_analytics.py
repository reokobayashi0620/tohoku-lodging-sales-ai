import sqlite3
from flask import render_template

from sales_action import THEMES

PREFECTURES = ["宮城県", "山形県", "岩手県", "福島県", "秋田県", "青森県"]


def safe_rate(numerator, denominator):
    if not denominator:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def build_metrics(rows):
    base = {"sent": 0, "replied": 0, "estimate": 0, "won": 0, "lost": 0}
    overall = base.copy()
    by_theme = {key: {"label": theme["label"], **base.copy()} for key, theme in THEMES.items()}
    by_prefecture = {p: base.copy() for p in PREFECTURES}

    for row in rows:
        activity_type = row["activity_type"]
        if activity_type in overall:
            overall[activity_type] += 1
        theme_key = row["theme_key"]
        if theme_key in by_theme and activity_type in overall:
            by_theme[theme_key][activity_type] += 1
        prefecture = row["prefecture"]
        if prefecture in by_prefecture and activity_type in overall:
            by_prefecture[prefecture][activity_type] += 1

    def enrich(data):
        enriched = dict(data)
        enriched["reply_rate"] = safe_rate(enriched["replied"], enriched["sent"])
        enriched["estimate_rate"] = safe_rate(enriched["estimate"], enriched["sent"])
        enriched["win_rate"] = safe_rate(enriched["won"], enriched["sent"])
        return enriched

    overall = enrich(overall)

    theme_rows = []
    for key, data in by_theme.items():
        item = enrich(data)
        item["key"] = key
        theme_rows.append(item)
    theme_rows.sort(key=lambda r: (-r["win_rate"], -r["estimate_rate"], -r["reply_rate"], -r["sent"]))

    prefecture_rows = []
    for prefecture, data in by_prefecture.items():
        item = enrich(data)
        item["prefecture"] = prefecture
        prefecture_rows.append(item)
    prefecture_rows.sort(key=lambda r: (-r["win_rate"], -r["estimate_rate"], -r["reply_rate"], -r["sent"]))

    best_theme = next((r for r in theme_rows if r["sent"] > 0), None)
    best_prefecture = next((r for r in prefecture_rows if r["sent"] > 0), None)
    return overall, theme_rows, prefecture_rows, best_theme, best_prefecture


def register_sales_analytics(app):
    @app.get("/sales-analytics")
    def sales_analytics():
        con = sqlite3.connect(app.config["DATABASE"])
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                """SELECT a.activity_type, a.theme_key, c.prefecture
                   FROM sales_activities a
                   JOIN lead_candidates c ON c.id=a.candidate_id"""
            ).fetchall()
        finally:
            con.close()

        overall, theme_rows, prefecture_rows, best_theme, best_prefecture = build_metrics(rows)
        return render_template(
            "sales_analytics.html",
            overall=overall,
            theme_rows=theme_rows,
            prefecture_rows=prefecture_rows,
            best_theme=best_theme,
            best_prefecture=best_prefecture,
        )

    return app
