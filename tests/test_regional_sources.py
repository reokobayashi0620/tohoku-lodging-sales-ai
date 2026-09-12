import sqlite3
from io import BytesIO

import app as app_module
from openpyxl import Workbook
from regional_sources import (
    SOURCES,
    discover_aomori_xlsx,
    discover_akita_pdf,
    import_records,
    parse_aomori_xlsx,
    parse_akita_pdf,
    parse_fukushima_html,
    parse_yamagata_pdf,
)


def make_app(tmp_path):
    return app_module.create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "test.db",
        "APP_USERNAME": "",
        "APP_PASSWORD": "",
    })


def test_phase_2_10_enables_aomori_and_akita_import():
    assert SOURCES["aomori"]["mode"] == "import"
    assert SOURCES["akita"]["mode"] == "import"
    assert SOURCES["iwate"]["mode"] == "source_only"


def test_discover_aomori_xlsx_prefers_housing_resource():
    html = """
    <a href='/files/other.xlsx'>別資料</a>
    <a href='/dataset/2047/resource/1/住宅宿泊事業届出一覧.xlsx'>住宅宿泊事業届出一覧</a>
    """
    url = discover_aomori_xlsx(html, "https://opendata.pref.aomori.lg.jp/dataset/2047.html")
    assert url == "https://opendata.pref.aomori.lg.jp/dataset/2047/resource/1/住宅宿泊事業届出一覧.xlsx"


def test_parse_aomori_xlsx_uses_headers_not_fixed_columns():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["説明", "青森県住宅宿泊事業法届出住宅一覧"])
    sheet.append(["電話番号", "届出者氏名又は名称", "届出住宅の所在地", "商号・屋号"])
    sheet.append(["017-000-0000", "株式会社青森ステイ", "青森市本町1-2-3", "青森の宿"])
    sheet.append(["090-1111-2222", "山田太郎", "弘前市元寺町4-5", "個人宿"])
    buffer = BytesIO()
    workbook.save(buffer)

    records = parse_aomori_xlsx(buffer.getvalue())
    assert records[0]["address"] == "青森市本町1-2-3"
    assert records[0]["name"] == "青森の宿"
    assert records[0]["company_name"] == "株式会社青森ステイ"
    assert records[0]["phone"] == "017-000-0000"
    assert records[1]["company_name"] == ""


def test_discover_akita_pdf_targets_business_list():
    html = """
    <a href='/a/rules.pdf'>住宅宿泊事業法に係る運用について</a>
    <a href='/a/list.pdf'>住宅宿泊事業者一覧（PDF）</a>
    """
    url = discover_akita_pdf(html, "https://www.pref.akita.lg.jp/pages/archive/31592")
    assert url == "https://www.pref.akita.lg.jp/a/list.pdf"


def test_parse_akita_pdf_separates_owner_and_residence(monkeypatch):
    header = (
        " " * 4
        + "届出番号".ljust(15)
        + "届出者氏名".ljust(20)
        + "届出者住所".ljust(28)
        + "届出住宅の所在地".ljust(32)
        + "電話番号"
    )
    row1 = (
        "1   "
        + "M050001234".ljust(15)
        + "株式会社秋田宿".ljust(20)
        + "大仙市花館字下殿屋敷46".ljust(28)
        + "仙北市角館町水ノ目沢15-1".ljust(32)
        + "0187-62-8123   ○"
    )
    row2 = (
        "2   "
        + "M050001235".ljust(15)
        + "佐藤太郎".ljust(20)
        + "男鹿市戸賀塩浜字平床50".ljust(28)
        + "同左".ljust(32)
        + "0185-47-7335   ×"
    )

    class FakePage:
        def extract_text(self, extraction_mode=None):
            return "\n".join([header, row1, row2])

    class FakeReader:
        def __init__(self, _stream):
            self.pages = [FakePage()]

    monkeypatch.setattr("regional_sources.PdfReader", FakeReader)
    records = parse_akita_pdf(b"%PDF-fake")
    assert records[0]["address"] == "仙北市角館町水ノ目沢15-1"
    assert records[0]["company_name"] == "株式会社秋田宿"
    assert records[0]["phone"] == "0187-62-8123"
    assert records[1]["address"] == "男鹿市戸賀塩浜字平床50"
    assert records[1]["company_name"] == ""


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
