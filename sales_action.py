import sqlite3
from flask import abort, render_template, request

from sales_priority import score_candidate

THEMES = {
    "pet_damage": {
        "label": "ペット傷・汚れ対策",
        "hook": "ペット同伴施設では、床や建具の引っかき傷・汚れが美観や清掃負担につながりやすいため",
        "offer": "既存の傷補修と、再発を抑える保護コーティングを組み合わせた現地対応",
    },
    "floor_repair": {
        "label": "床の傷・劣化補修",
        "hook": "宿泊施設の床は、張り替えるほどではない傷や摩耗でも宿泊者の印象に影響しやすいため",
        "offer": "交換・張り替え前に、部分補修や再生で美観を戻す現地対応",
    },
    "coating": {
        "label": "床・水回りコーティング",
        "hook": "日々の清掃負担と経年劣化を抑え、稼働を止める大規模改修を減らすため",
        "offer": "床や水回りの状態に合わせた保護コーティングとメンテナンス提案",
    },
    "furniture": {
        "label": "家具・建具の補修",
        "hook": "家具や建具の小傷は交換コストに対して補修効果が出やすいため",
        "offer": "家具・建具・枠まわりの傷や欠けを交換せず現地で補修する対応",
    },
}


def recommend_theme(row):
    if row["pet_friendly"]:
        return "pet_damage"
    if row["wood_floor"]:
        return "floor_repair"
    if row["whole_house"]:
        return "coating"
    return "furniture"


def build_sales_draft(row, theme_key):
    theme = THEMES.get(theme_key, THEMES[recommend_theme(row)])
    facility = row["name"] or "ご担当施設"
    company = row["company_name"] or "ご担当者"
    first_line = f"{company}様\n\n突然のご連絡失礼いたします。東北エリアで床・建具・家具・水回りの補修・コーティングを行っております。"
    body = (
        f"\n\n{facility}について拝見し、{theme['hook']}、ご連絡いたしました。"
        f"\n\n弊社では、{theme['offer']}が可能です。"
        "\n『交換するほどではない。でも、このままでは宿泊客に見せにくい』という傷や劣化を、できるだけ稼働を止めずに整えることを得意としています。"
        "\n\n張り替え・交換を決める前の比較材料として、写真からの概算確認や現地確認も可能です。"
        "\nもし床・家具・建具などで気になる箇所がございましたら、写真を数枚お送りいただければ対応可否を確認いたします。"
        "\n\nどうぞよろしくお願いいたします。"
    )
    return first_line + body


def register_sales_action(app):
    @app.get("/sales-action/<int:candidate_id>")
    def sales_action(candidate_id):
        con = sqlite3.connect(app.config["DATABASE"])
        con.row_factory = sqlite3.Row
        try:
            candidate = con.execute("SELECT * FROM lead_candidates WHERE id=?", (candidate_id,)).fetchone()
        finally:
            con.close()
        if not candidate:
            abort(404)

        score = score_candidate(candidate)
        selected_theme = request.args.get("theme", "").strip()
        if selected_theme not in THEMES:
            selected_theme = recommend_theme(candidate)
        draft = build_sales_draft(candidate, selected_theme)
        contact_options = [
            ("メール", candidate["email"]),
            ("電話", candidate["phone"]),
            ("問い合わせフォーム", candidate["contact_url"]),
        ]
        contact_options = [(label, value) for label, value in contact_options if value]
        return render_template(
            "sales_action.html",
            candidate=candidate,
            score=score,
            themes=THEMES,
            selected_theme=selected_theme,
            draft=draft,
            contact_options=contact_options,
        )
    return app
