import csv
import hmac
import io
import os

from flask import Response, abort, request

from simple_sales_flow import build_flow

SYNC_TOKEN_ENV = "SHEETS_SYNC_TOKEN"
CSV_HEADERS = [
    "ID", "県", "市町村", "施設・サービス名", "運営会社名", "公式サイト", "問い合わせページ",
    "メール", "電話", "ペット可", "一棟貸し", "複数施設", "木質床", "営業ステータス",
    "営業テーマ", "最終活動日時", "情報元URL", "備考",
]


def _authorized():
    expected = os.environ.get(SYNC_TOKEN_ENV, "")
    supplied = request.args.get("token", "")
    return bool(expected and supplied and hmac.compare_digest(supplied, expected))


def _mark(value):
    return "○" if value else ""


def export_rows(database):
    groups = build_flow(database)
    stage_labels = {
        "new": "新規",
        "sent": "返信待ち",
        "replied": "返信あり",
        "followup": "追客",
        "done": "完了",
        "research": "要調査",
    }
    rows = []
    for stage, items in groups.items():
        for item in items:
            candidate = item["candidate"]
            last = item.get("last_activity")
            rows.append([
                candidate["id"],
                candidate["prefecture"],
                candidate["city"],
                candidate["name"],
                candidate["company_name"],
                candidate["official_url"],
                candidate["contact_url"],
                candidate["email"],
                candidate["phone"],
                _mark(candidate["pet_friendly"]),
                _mark(candidate["whole_house"]),
                _mark(candidate["multiple_facilities"]),
                _mark(candidate["wood_floor"]),
                stage_labels[stage],
                item["theme"],
                last["created_at"] if last else "",
                candidate["source_url"],
                candidate["research_notes"],
            ])
    rows.sort(key=lambda row: (row[1], row[2], str(row[4] or row[3])))
    return rows


def register_spreadsheet_sync(app):
    @app.get("/exports/sales.csv", endpoint="sales_sync_csv")
    def sales_sync_csv():
        if not _authorized():
            abort(403)
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(CSV_HEADERS)
        writer.writerows(export_rows(app.config["DATABASE"]))
        body = "\ufeff" + output.getvalue()
        return Response(
            body,
            mimetype="text/csv; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    return app
