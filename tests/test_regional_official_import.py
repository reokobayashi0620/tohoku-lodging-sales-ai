import sqlite3

from app import create_app
from regional_official_import import import_official_records, parse_fukushima_html, register_regional_official_import


def _app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": tmp_path / "regional.db", "APP_USERNAME": "", "APP_PASSWORD": ""})


def test_import_official_records_inserts_and_deduplicates(tmp_path):
    app = _app(tmp_path)
    records = [{"name": "テスト民泊", "operator": "株式会社テスト", "address": "福島市渡利字高倉57-2", "phone": "024-000-0000"}]
    first = import_official_records(app.config["DATABASE"], "福島県", records, "https://example.test", "福島県公式 民泊一覧")
    second = import_official_records(app.config["DATABASE"], "福島県", records, "https://example.test", "福島県公式 民泊一覧")
    assert first["inserted"] == 1
    assert second["duplicates"] == 1
    with sqlite3.connect(app.config["DATABASE"]) as con:
        row = con.execute("SELECT name,company_name,phone FROM lead_candidates WHERE prefecture='福島県'").fetchone()
    assert row == ("テスト民泊", "株式会社テスト", "024-000-0000")


def test_parse_fukushima_html():
    html = "<table><tr><td>株式会社宿</td><td>ペット貸別荘</td><td>福島市大町1-2</td><td>024-111-2222</td><td></td></tr></table>"
    records = parse_fukushima_html(html)
    assert records[0]["name"] == "ペット貸別荘"
    assert records[0]["address"] == "福島市大町1-2"


def test_regional_routes_are_registered(tmp_path):
    app = _app(tmp_path)
    register_regional_official_import(app)
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/targets/import-yamagata" in rules
    assert "/targets/import-fukushima" in rules
