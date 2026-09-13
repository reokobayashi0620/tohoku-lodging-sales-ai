import sqlite3

from flask import abort, render_template, request

from follow_up import classify_follow_up
from sales_action import THEMES

FOLLOW_UP_TONES = {
    "short": "短め",
    "standard": "標準",
    "soft": "やわらかめ",
}


def _theme_label(theme_key):
    return THEMES.get(theme_key, {}).get("label", "補修・コーティング")


def build_follow_up_draft(candidate, activity, tone="standard"):
    """Build a safe follow-up draft from the latest logged activity only."""
    follow = classify_follow_up(activity["activity_type"], activity["created_at"])
    if not follow:
        return None

    facility = candidate["name"] or "ご担当施設"
    company = candidate["company_name"] or "ご担当者"
    theme = _theme_label(activity["theme_key"])
    note = (activity["note"] or "").strip()

    greeting = f"{company}様\n\nお世話になっております。先日、{facility}についてご連絡した件で、確認のためご連絡いたしました。"

    if follow["bucket"] == "no_reply":
        body = (
            f"\n\n先日の{theme}のご案内につきまして、その後ご確認いただけましたでしょうか。"
            "\n交換や張り替えを決める前の比較材料として、写真から対応可否や概算の確認も可能です。"
            "\nお急ぎでなければ、ご都合のよいタイミングでご覧いただければ幸いです。"
        )
    elif follow["bucket"] == "reply_action":
        context = f"\n\n前回のご返信内容：{note}" if note else ""
        body = (
            f"{context}\n\nご返信ありがとうございます。{theme}について、必要な範囲や状態を確認できれば、対応方法を具体的に整理できます。"
            "\n差し支えなければ、気になる箇所の写真やおおよその範囲をお送りください。現地確認が必要かも含めてご案内します。"
        )
    elif follow["bucket"] == "estimate_followup":
        body = (
            f"\n\n先日お送りした{theme}のお見積について、その後ご不明点や調整したい点はございませんでしょうか。"
            "\n施工範囲・日程・ご予算に合わせた調整も可能ですので、検討中の点があれば遠慮なくお知らせください。"
        )
    else:
        body = (
            f"\n\n先日ご案内した{theme}について、必要になりましたらいつでもご相談ください。"
            "\n現時点ではご返信不要です。"
        )

    closing = "\n\nどうぞよろしくお願いいたします。"
    draft = greeting + body + closing

    if tone == "short":
        lines = [line for line in draft.splitlines() if line.strip()]
        return "\n\n".join(lines[:4])
    if tone == "soft":
        draft = draft.replace("確認のためご連絡いたしました。", "念のため、無理のないタイミングでご確認いただければと思いご連絡しました。")
        draft = draft.replace("お送りください。", "お送りいただけますと幸いです。")
    return draft


def register_follow_up_draft(app):
    @app.get("/follow-up-draft/<int:candidate_id>")
    def follow_up_draft(candidate_id):
        tone = request.args.get("tone", "standard").strip()
        if tone not in FOLLOW_UP_TONES:
            tone = "standard"

        con = sqlite3.connect(app.config["DATABASE"])
        con.row_factory = sqlite3.Row
        try:
            candidate = con.execute("SELECT * FROM lead_candidates WHERE id=?", (candidate_id,)).fetchone()
            activity = con.execute(
                """SELECT * FROM sales_activities
                   WHERE candidate_id=?
                   ORDER BY created_at DESC, id DESC LIMIT 1""",
                (candidate_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            activity = None
            candidate = con.execute("SELECT * FROM lead_candidates WHERE id=?", (candidate_id,)).fetchone()
        finally:
            con.close()

        if not candidate:
            abort(404)
        if not activity:
            abort(404)

        follow = classify_follow_up(activity["activity_type"], activity["created_at"])
        if not follow:
            abort(404)

        draft = build_follow_up_draft(candidate, activity, tone=tone)
        return render_template(
            "follow_up_draft.html",
            candidate=candidate,
            activity=activity,
            follow=follow,
            draft=draft,
            tone=tone,
            tones=FOLLOW_UP_TONES,
            themes=THEMES,
        )

    return app
