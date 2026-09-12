import sqlite3

import pytest
import requests

import app as app_module


def test_stable_official_url_is_always_first():
    urls = app_module.miyagi_source_urls("https://example.invalid/old.pdf")
    assert urls[0] == app_module.MIYAGI_OFFICIAL_URL
    assert "https://example.invalid/old.pdf" in urls


def test_fetch_falls_back_when_official_url_fails(monkeypatch):
    configured = "https://example.test/fallback.pdf"
    calls = []

    def fake_download(url):
        calls.append(url)
        if url == app_module.MIYAGI_OFFICIAL_URL:
            raise requests.RequestException("temporary failure")
        return b"fake-pdf"

    monkeypatch.setattr(app_module, "download_pdf", fake_download)
    monkeypatch.setattr(app_module, "parse_miyagi_pdf", lambda data: ["石巻市泉町1-2-3"])

    addresses = app_module.fetch_miyagi_candidates(configured)

    assert addresses == ["石巻市泉町1-2-3"]
    assert addresses.source_url == configured
    assert calls[:2] == [app_module.MIYAGI_OFFICIAL_URL, configured]


def test_fetch_failure_message_does_not_expose_internal_urls(monkeypatch):
    def always_fail(url):
        raise requests.RequestException("blocked")

    monkeypatch.setattr(app_module, "download_pdf", always_fail)

    with pytest.raises(ValueError) as exc_info:
        app_module.fetch_miyagi_candidates("https://secret.example.test/source.pdf")

    message = str(exc_info.value)
    assert "複数の公式URL" in message
    assert "secret.example.test" not in message


def test_collect_stores_actual_source_url(monkeypatch, tmp_path):
    database = tmp_path / "source.db"
    application = app_module.create_app({
        "TESTING": True,
        "DATABASE": database,
        "SECRET_KEY": "test",
        "MIYAGI_SOURCE_URL": "https://stale.example.test/old.pdf",
    })
    client = application.test_client()
    actual_url = "https://www.pref.miyagi.jp/documents/30180/kunigaidorain.pdf"

    monkeypatch.setattr(
        app_module,
        "fetch_miyagi_candidates",
        lambda configured: app_module.CandidateBatch(["石巻市泉町1-2-3"], source_url=actual_url),
    )

    response = client.post("/collect", follow_redirects=True)
    assert response.status_code == 200
    assert "新規1件" in response.get_data(as_text=True)

    with sqlite3.connect(database) as con:
        row = con.execute(
            "SELECT address, source_url, status FROM lead_candidates WHERE address=?",
            ("石巻市泉町1-2-3",),
        ).fetchone()

    assert row == ("石巻市泉町1-2-3", actual_url, "pending")
