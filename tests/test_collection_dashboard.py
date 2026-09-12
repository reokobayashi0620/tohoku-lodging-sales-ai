import sqlite3

import app as app_module
from collection_dashboard import (
    collection_summary,
    discover_iwate_status_pdf,
    parse_iwate_municipality_counts,
    register_collection_dashboard,
    save_iwate_snapshot,
)


def make_app(tmp_path):
    application = app_module.create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "test.db",
        "APP_USERNAME": "",
        "APP_PASSWORD": "",
    })
    register_collection_dashboard(application)
    return application


def test_discover_iwate_status_pdf_prefers_status_list():
    html = """
    <a href='/docs/guide.pdf'>住宅宿泊事業の手引書</a>
    <a href='/docs/todokede080630.pdf'>住宅宿泊事業法に基づく届出状況一覧(令和8年6月30日時点)</a>
    """
    url, label = discover_iwate_status_pdf(html, "https://www.pref.iwate.jp/page.html")
    assert url == "https://www.pref.iwate.jp/docs/todokede080630.pdf"
    assert "届出状況一覧" in label


def test_parse_iwate_municipality_counts(monkeypatch):
    class FakePage:
        def extract_text(self):
            return """
            住宅宿泊事業法に基づく届出状況一覧
            盛岡市 12 件
            八幡平市 8
            雫石町 5
            一関市
            9
            合計 34
            """

    class FakeReader:
        def __init__(self, _stream):
            self.pages = [FakePage()]

    monkeypatch.setattr("collection_dashboard.PdfReader", FakeReader)
    rows = parse_iwate_municipality_counts(b"%PDF-fake")
    assert ("盛岡市", 12) in rows
    assert ("一関市", 9) in rows
    assert rows[0][1] >= rows[-1][1]


def test_save_snapshot_and_dashboard_summary(tmp_path):
    application = make_app(tmp_path)
    count = save_iwate_snapshot(
        application.config["DATABASE"],
        [("盛岡市", 12), ("一関市", 9)],
        "令和8年6月30日",
        "https://example.test/iwate.pdf",
    )
    assert count == 2

    with sqlite3.connect(application.config["DATABASE"]) as con:
        con.execute(
            """INSERT INTO lead_candidates
               (name,prefecture,city,address,normalized_key,status,research_status)
               VALUES ('','岩手県','盛岡市','盛岡市本町1-1','iwate|morioka|1','pending','unresearched')"""
        )

    summary, iwate_rows = collection_summary(application.config["DATABASE"])
    iwate = next(row for row in summary if row["prefecture"] == "岩手県")
    assert iwate["total"] == 1
    assert iwate["unresearched"] == 1
    assert iwate_rows[0]["area_name"] == "盛岡市"
    assert iwate_rows[0]["reported_count"] == 12


def test_dashboard_page_explains_iwate_safety_policy(tmp_path):
    application = make_app(tmp_path)
    client = application.test_client()
    response = client.get("/collection-dashboard")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "収集ダッシュボード" in text
    assert "岩手県：調査エリア優先順位" in text
    assert "住所を推測せず" in text
