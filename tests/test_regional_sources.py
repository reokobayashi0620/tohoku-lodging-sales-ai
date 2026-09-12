import sqlite3

import app as app_module
from regional_sources import import_records, parse_fukushima_html, parse_yamagata_pdf


def make_app(tmp_path):
    return app_module.create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "test.db",
        "APP_USERNAME": "",
        "APP_PASSWORD": "",
    })


def test_parse_fukushima_html_extracts_public_fields():
    html = """
    <table>
      <tr><th>商号</th><th>屋号</th><th>届出住宅の住所</th><th>緊急連絡先</th></tr>
      <tr><td>株式会社テスト</td><td>森の宿</td><td>福島市渡利字高倉57-2</td><td>024-000-0000</td></tr>
      <tr><td></td><td>個人宿</td><td>郡山市西田町大田字中洞475</td><td></td></tr>
    </table>
    """
    records = parse_fukushima_html(html)
    assert records[0]["name"] == "森の宿"
    assert records[0]["company_name"] == "株式会社テスト"
    assert records[0]["phone"] == "024-000-0000"
    assert records[1]["company_name"] == ""


def test_import_records_is_deduplicated(tmp_path):
    application = make_app(tmp_path)
    records = [{
        "address": "福島市渡利字高倉57-2",
        "name": "森の宿",
        "company_name": "株式会社テスト",
        "phone": "024-000-0000",
        "official_url": "",
    }]
    first = import_records(application.config["DATABASE"], "fukushima", records, "https://example.test/source")
    second = import_records(application.config["DATABASE"], "fukushima", records, "https://example.test/source")
    assert first == {"total": 1, "new": 1, "duplicate": 0}
    assert second == {"total": 1, "new": 0, "duplicate": 1}
    with sqlite3.connect(application.config["DATABASE"]) as con:
        row = con.execute("SELECT name,prefecture,phone,status FROM lead_candidates").fetchone()
    assert row == ("森の宿", "福島県", "024-000-0000", "pending")


def test_parse_yamagata_pdf_uses_only_address_like_lines(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "山形県住宅宿泊事業者一覧\n1 山形市蔵王温泉199番地\n2 米沢市城南5-4-13\n令和8年現在"

    class FakeReader:
        def __init__(self, _stream):
            self.pages = [FakePage()]

    monkeypatch.setattr("regional_sources.PdfReader", FakeReader)
    addresses = parse_yamagata_pdf(b"%PDF-fake")
    assert addresses == ["山形市蔵王温泉199番地", "米沢市城南5-4-13"]
