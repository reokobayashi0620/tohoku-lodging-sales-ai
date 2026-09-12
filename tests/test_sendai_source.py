import sqlite3

import app as app_module


def test_parse_sendai_pdf_prefixes_sendai_city(monkeypatch):
    text = """
住宅宿泊事業法に基づく届出住宅一覧
1 施設住所 青葉区上愛子字蛇台原49-38
2 施設住所 泉区住吉台東4丁目9-7
3 施設住所 青葉区上愛子字蛇台原49-38
"""
    monkeypatch.setattr(app_module, "pdf_text", lambda data: text)

    addresses = app_module.parse_sendai_pdf(b"dummy")

    assert addresses == [
        "仙台市青葉区上愛子字蛇台原49-38",
        "仙台市泉区住吉台東4丁目9-7",
    ]


def test_sendai_source_stable_url_is_first():
    urls = app_module.sendai_source_urls("https://example.invalid/old.pdf")
    assert urls[0] == app_module.SENDAI_OFFICIAL_URL
    assert "https://example.invalid/old.pdf" in urls


def test_collect_sendai_candidate(monkeypatch, tmp_path):
    database = tmp_path / "sendai.db"
    application = app_module.create_app({
        "TESTING": True,
        "DATABASE": database,
        "SECRET_KEY": "test",
    })
    client = application.test_client()
    actual_url = app_module.SENDAI_OFFICIAL_URL

    monkeypatch.setattr(
        app_module,
        "fetch_sendai_candidates",
        lambda configured: app_module.CandidateBatch(
            ["仙台市青葉区上愛子字蛇台原49-38"], source_url=actual_url
        ),
    )

    response = client.post("/collect", data={"source": "sendai"}, follow_redirects=True)
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "仙台市: 1件を確認し、新規1件" in page

    with sqlite3.connect(database) as con:
        row = con.execute(
            "SELECT prefecture, city, address, source_url, source_type, status FROM lead_candidates"
        ).fetchone()

    assert row == (
        "宮城県",
        "仙台市",
        "仙台市青葉区上愛子字蛇台原49-38",
        actual_url,
        app_module.SENDAI_SOURCE_TYPE,
        "pending",
    )
