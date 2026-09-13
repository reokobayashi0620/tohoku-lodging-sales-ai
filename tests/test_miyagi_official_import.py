import sqlite3

import app as app_module
from miyagi_enrichment import import_miyagi_official_records


def make_app(tmp_path):
    application = app_module.create_app({"TESTING": True, "DATABASE": tmp_path / "test.db"})
    return application


def test_import_miyagi_official_record(tmp_path):
    application = make_app(tmp_path)
    records = [{
        "name": "蔵王ペットヴィラ",
        "operator": "株式会社テスト宿泊",
        "address": "刈田郡蔵王町遠刈田温泉字七日原1-2",
        "phone": "0224-00-0000",
        "email": "hello@example.com",
        "official_url": "https://example.com/zao",
    }]
    stats = import_miyagi_official_records(application.config["DATABASE"], records)
    assert stats["inserted"] == 1
    with sqlite3.connect(application.config["DATABASE"]) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM lead_candidates").fetchone()
    assert row["name"] == "蔵王ペットヴィラ"
    assert row["company_name"] == "株式会社テスト宿泊"
    assert row["source_type"] == "宮城県公式 民泊届出施設紹介"
    assert row["research_status"] == "researching"


def test_import_updates_existing_without_duplicate(tmp_path):
    application = make_app(tmp_path)
    first = [{"name": "", "operator": "", "address": "石巻市泉町2-9-10", "phone": "", "email": "", "official_url": ""}]
    second = [{"name": "石巻の宿", "operator": "合同会社運営", "address": "石巻市泉町2-9-10", "phone": "0225-00-0000", "email": "", "official_url": "https://example.com/ishinomaki"}]
    assert import_miyagi_official_records(application.config["DATABASE"], first)["inserted"] == 1
    stats = import_miyagi_official_records(application.config["DATABASE"], second)
    assert stats["inserted"] == 0
    assert stats["duplicates"] == 1
    with sqlite3.connect(application.config["DATABASE"]) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM lead_candidates").fetchall()
    assert len(rows) == 1
    assert rows[0]["name"] == "石巻の宿"
    assert rows[0]["company_name"] == "合同会社運営"


def test_targets_page_has_official_import_button(tmp_path):
    application = make_app(tmp_path)
    from target_finder import register_target_finder
    from miyagi_enrichment import register_miyagi_enrichment
    register_target_finder(application)
    register_miyagi_enrichment(application)
    response = application.test_client().get("/targets")
    assert response.status_code == 200
    assert "宮城県公式民泊を更新" in response.get_data(as_text=True)
