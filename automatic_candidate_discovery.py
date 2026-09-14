import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

from official_discovery_pipeline import run_official_discovery_pipeline

JST = timezone(timedelta(hours=9))
RUN_HOUR_JST = 6
RUN_MINUTE_JST = 30
CHECK_INTERVAL_SECONDS = 15 * 60


def _connect(database):
    con = sqlite3.connect(database, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def ensure_auto_discovery_table(database):
    with _connect(database) as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS automatic_candidate_discovery_runs (
                run_date TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                seeded INTEGER NOT NULL DEFAULT 0,
                inserted INTEGER NOT NULL DEFAULT 0,
                operator_updated INTEGER NOT NULL DEFAULT 0,
                stats_json TEXT DEFAULT '',
                error TEXT DEFAULT ''
            )"""
        )


def _claim_run(database, run_date):
    ensure_auto_discovery_table(database)
    with _connect(database) as con:
        cursor = con.execute(
            """INSERT OR IGNORE INTO automatic_candidate_discovery_runs (run_date,status)
               VALUES (?, 'running')""",
            (run_date,),
        )
        return cursor.rowcount == 1


def _finish_run(database, run_date, *, status, seeded=0, stats=None, error=''):
    stats = stats or {}
    with _connect(database) as con:
        con.execute(
            """UPDATE automatic_candidate_discovery_runs
               SET status=?, finished_at=CURRENT_TIMESTAMP, seeded=?, inserted=?, operator_updated=?, stats_json=?, error=?
               WHERE run_date=?""",
            (
                status,
                seeded,
                int(stats.get('inserted', 0)),
                int(stats.get('operator_updated', 0)),
                json.dumps(stats, ensure_ascii=False),
                error[:2000],
                run_date,
            ),
        )


def run_automatic_candidate_discovery(database, sendai_source_url, *, now=None, pipeline=None):
    """Run at most once per JST calendar day and persist the result."""
    now = now or datetime.now(JST)
    run_date = now.astimezone(JST).date().isoformat()
    if not _claim_run(database, run_date):
        return {"ran": False, "reason": "already_ran", "run_date": run_date}

    try:
        # Local import avoids a module cycle: simple_sales_flow also reads this module's status.
        from simple_sales_flow import seed_businesses

        seeded = seed_businesses(database)
        runner = pipeline or run_official_discovery_pipeline
        stats = runner(database, sendai_source_url)
        _finish_run(database, run_date, status="success", seeded=seeded, stats=stats)
        return {"ran": True, "run_date": run_date, "seeded": seeded, **stats}
    except Exception as exc:
        _finish_run(database, run_date, status="failed", error=str(exc))
        raise


def get_auto_discovery_status(database):
    ensure_auto_discovery_table(database)
    with _connect(database) as con:
        row = con.execute(
            """SELECT * FROM automatic_candidate_discovery_runs
               ORDER BY run_date DESC LIMIT 1"""
        ).fetchone()
    if not row:
        return {"enabled": True, "last_run": None, "schedule": "毎日 06:30（日本時間）"}
    return {
        "enabled": True,
        "last_run": dict(row),
        "schedule": "毎日 06:30（日本時間）",
    }


def _due(now):
    local = now.astimezone(JST)
    return (local.hour, local.minute) >= (RUN_HOUR_JST, RUN_MINUTE_JST)


def _scheduler_loop(database, sendai_source_url, logger):
    # Start quickly after boot, then check periodically. The DB claim prevents duplicate daily runs.
    while True:
        try:
            now = datetime.now(JST)
            if _due(now):
                result = run_automatic_candidate_discovery(database, sendai_source_url, now=now)
                if result.get("ran"):
                    logger.info("automatic candidate discovery completed: %s", result)
        except Exception:
            logger.exception("automatic candidate discovery failed")
        time.sleep(CHECK_INTERVAL_SECONDS)


def register_automatic_candidate_discovery(app):
    ensure_auto_discovery_table(app.config["DATABASE"])
    if app.config.get("TESTING"):
        return app
    if app.extensions.get("automatic_candidate_discovery_started"):
        return app

    thread = threading.Thread(
        target=_scheduler_loop,
        args=(app.config["DATABASE"], app.config["SENDAI_SOURCE_URL"], app.logger),
        name="automatic-candidate-discovery",
        daemon=True,
    )
    thread.start()
    app.extensions["automatic_candidate_discovery_started"] = True
    return app
