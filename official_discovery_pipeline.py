import requests
from flask import flash, redirect

from app import fetch_sendai_candidates
from candidate_reconciliation import reconcile_candidates
from miyagi_enrichment import MIYAGI_DETAIL_URL, fetch_miyagi_detail_records, import_miyagi_official_records
from operator_enrichment import operator_batch
from regional_official_import import (
    FUKUSHIMA_LIST_URL,
    FUKUSHIMA_SOURCE_TYPE,
    YAMAGATA_PDF_URL,
    YAMAGATA_SOURCE_TYPE,
    fetch_fukushima_records,
    fetch_yamagata_records,
    import_official_records,
)
from remaining_prefectures_official import (
    AOMORI_SOURCE_TYPE,
    AKITA_SOURCE_TYPE,
    IWATE_SOURCE_TYPE,
    fetch_aomori_records,
    fetch_akita_records,
    fetch_iwate_records,
)
from sendai_official import import_sendai_official_records


def run_official_discovery_pipeline(database, sendai_source_url):
    """Refresh official Tohoku minpaku sources, reconcile known public POIs, then enrich operators."""
    stats = {"sources_ok": 0, "sources_failed": 0, "source_records": 0, "inserted": 0, "updated": 0, "matched": 0}
    errors = []

    def collect(label, work):
        try:
            result = work()
            stats["sources_ok"] += 1
            stats["source_records"] += result.get("source_records", 0)
            stats["inserted"] += result.get("inserted", 0)
            stats["updated"] += result.get("updated", 0)
        except (requests.RequestException, ValueError, OSError) as exc:
            stats["sources_failed"] += 1
            errors.append(f"{label}: {exc}")

    collect("宮城県", lambda: import_miyagi_official_records(database, fetch_miyagi_detail_records(), MIYAGI_DETAIL_URL))

    def sendai():
        addresses = fetch_sendai_candidates(sendai_source_url)
        source_url = getattr(addresses, "source_url", None) or sendai_source_url
        return import_sendai_official_records(database, addresses, source_url)
    collect("仙台市", sendai)

    collect("山形県", lambda: import_official_records(database, "山形県", fetch_yamagata_records(), YAMAGATA_PDF_URL, YAMAGATA_SOURCE_TYPE))
    collect("福島県", lambda: import_official_records(database, "福島県", fetch_fukushima_records(), FUKUSHIMA_LIST_URL, FUKUSHIMA_SOURCE_TYPE))

    for label, prefecture, fetcher, source_type in (
        ("岩手県", "岩手県", fetch_iwate_records, IWATE_SOURCE_TYPE),
        ("秋田県", "秋田県", fetch_akita_records, AKITA_SOURCE_TYPE),
        ("青森県", "青森県", fetch_aomori_records, AOMORI_SOURCE_TYPE),
    ):
        def work(prefecture=prefecture, fetcher=fetcher, source_type=source_type):
            records, source_url = fetcher()
            return import_official_records(database, prefecture, records, source_url, source_type)
        collect(label, work)

    reconciled = reconcile_candidates(database)
    stats["matched"] = reconciled["matched"]
    stats["updated"] += reconciled["updated"]

    operator = operator_batch(database, limit=25)
    stats["operator_checked"] = operator["checked"]
    stats["operator_updated"] = operator["updated"]
    stats["company_found"] = operator["company_found"]
    stats["contact_found"] = operator["contact_found"]
    stats["errors"] = errors
    return stats


def register_official_discovery_pipeline(app):
    @app.post("/targets/run-official-pipeline", endpoint="run_official_target_pipeline")
    def run_official_target_pipeline():
        stats = run_official_discovery_pipeline(app.config["DATABASE"], app.config["SENDAI_SOURCE_URL"])
        message = (
            f"公式営業先発掘を実行: 公式{stats['sources_ok']}ソース成功 / "
            f"{stats['source_records']}件確認 / 新規{stats['inserted']}件 / "
            f"照合{stats['matched']}件 / 運営会社・連絡先更新{stats['operator_updated']}件。"
        )
        if stats["sources_failed"]:
            message += f" {stats['sources_failed']}ソースは取得失敗のためスキップしました。"
        flash(message, "success" if stats["sources_ok"] else "error")
        return redirect("/targets")

    return app
