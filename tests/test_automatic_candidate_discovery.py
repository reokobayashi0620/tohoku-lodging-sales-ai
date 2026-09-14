from datetime import datetime

import app as app_module
from automatic_candidate_discovery import JST, get_auto_discovery_status, run_automatic_candidate_discovery


def make_app(tmp_path):
    return app_module.create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "sales.db",
        "APP_USERNAME": "",
        "APP_PASSWORD": "",
    })


def test_automatic_discovery_runs_only_once_per_jst_day(tmp_path):
    app = make_app(tmp_path)
    calls = []

    def fake_pipeline(database, sendai_source_url):
        calls.append((database, sendai_source_url))
        return {
            "sources_ok": 7,
            "sources_failed": 0,
            "source_records": 120,
            "inserted": 12,
            "updated": 3,
            "matched": 2,
            "operator_checked": 25,
            "operator_updated": 4,
            "company_found": 2,
            "contact_found": 1,
            "errors": [],
        }

    now = datetime(2026, 9, 14, 7, 0, tzinfo=JST)
    first = run_automatic_candidate_discovery(
        app.config["DATABASE"], app.config["SENDAI_SOURCE_URL"], now=now, pipeline=fake_pipeline
    )
    second = run_automatic_candidate_discovery(
        app.config["DATABASE"], app.config["SENDAI_SOURCE_URL"], now=now, pipeline=fake_pipeline
    )

    assert first["ran"] is True
    assert first["seeded"] == 8
    assert first["inserted"] == 12
    assert second == {"ran": False, "reason": "already_ran", "run_date": "2026-09-14"}
    assert len(calls) == 1

    status = get_auto_discovery_status(app.config["DATABASE"])
    assert status["enabled"] is True
    assert status["schedule"] == "毎日 06:30（日本時間）"
    assert status["last_run"]["status"] == "success"
    assert status["last_run"]["seeded"] == 8
    assert status["last_run"]["inserted"] == 12
    assert status["last_run"]["operator_updated"] == 4


def test_automatic_discovery_runs_again_next_day(tmp_path):
    app = make_app(tmp_path)

    def fake_pipeline(database, sendai_source_url):
        return {"inserted": 0, "operator_updated": 0}

    day1 = datetime(2026, 9, 14, 7, 0, tzinfo=JST)
    day2 = datetime(2026, 9, 15, 7, 0, tzinfo=JST)
    assert run_automatic_candidate_discovery(
        app.config["DATABASE"], app.config["SENDAI_SOURCE_URL"], now=day1, pipeline=fake_pipeline
    )["ran"] is True
    result = run_automatic_candidate_discovery(
        app.config["DATABASE"], app.config["SENDAI_SOURCE_URL"], now=day2, pipeline=fake_pipeline
    )
    assert result["ran"] is True
    assert result["run_date"] == "2026-09-15"
    assert result["seeded"] == 0
