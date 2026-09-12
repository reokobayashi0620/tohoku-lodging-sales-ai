import sqlite3

from flask import flash, redirect, request, url_for


ALLOWED_BULK_ACTIONS = {
    "start_research": "調査中に変更",
    "reset_research": "未調査に戻す",
    "exclude": "除外",
}


def _candidate_ids(values):
    ids = []
    for value in values[:200]:
        try:
            candidate_id = int(value)
        except (TypeError, ValueError):
            continue
        if candidate_id > 0 and candidate_id not in ids:
            ids.append(candidate_id)
    return ids


def register_bulk_actions(app):
    if "bulk_candidates" in app.view_functions:
        return app

    @app.post("/candidates/bulk", endpoint="bulk_candidates")
    def bulk_candidates():
        action = request.form.get("action", "")
        ids = _candidate_ids(request.form.getlist("candidate_ids"))
        return_status = request.form.get("return_status", "pending")
        if return_status not in {"pending", "promoted", "excluded", "all"}:
            return_status = "pending"

        if action not in ALLOWED_BULK_ACTIONS:
            flash("一括操作を選択してください。", "error")
            return redirect(url_for("candidates", status=return_status))
        if not ids:
            flash("候補を1件以上選択してください。", "error")
            return redirect(url_for("candidates", status=return_status))

        placeholders = ",".join("?" for _ in ids)
        database = app.config["DATABASE"]
        with sqlite3.connect(database) as con:
            if action == "start_research":
                cursor = con.execute(
                    f"""UPDATE lead_candidates
                        SET research_status='researching', updated_at=CURRENT_TIMESTAMP
                        WHERE id IN ({placeholders})
                          AND status='pending'
                          AND research_status='unresearched'""",
                    ids,
                )
            elif action == "reset_research":
                cursor = con.execute(
                    f"""UPDATE lead_candidates
                        SET research_status='unresearched', updated_at=CURRENT_TIMESTAMP
                        WHERE id IN ({placeholders}) AND status='pending'""",
                    ids,
                )
            else:
                cursor = con.execute(
                    f"""UPDATE lead_candidates
                        SET status='excluded', updated_at=CURRENT_TIMESTAMP
                        WHERE id IN ({placeholders}) AND status='pending'""",
                    ids,
                )
            changed = cursor.rowcount

        flash(f"{ALLOWED_BULK_ACTIONS[action]}：{changed}件を更新しました。", "success")
        return redirect(url_for("candidates", status=return_status))

    return app
