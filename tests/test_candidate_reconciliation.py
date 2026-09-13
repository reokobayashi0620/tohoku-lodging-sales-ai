import sqlite3

from candidate_reconciliation import normalize_address, reconcile_candidates, register_candidate_reconciliation


def _app(tmp_path):
    import app as app_module
    database = tmp_path / "sales.db"
    app = app_module.create_app({"TESTING": True, "DATABASE": database, "SECRET_KEY": "test"})
    register_candidate_reconciliation(app)
    return app, database


def _insert(database, *, name, address, source_type, source_url, official_url="", phone="", pet=0):
    with sqlite3.connect(database) as con:
        con.execute(
            """INSERT INTO lead_candidates
            (name,company_name,prefecture,city,address,official_url,phone,email,contact_url,
             pet_friendly,whole_house,multiple_facilities,wood_floor,research_status,research_notes,
             source_url,source_type,normalized_key,status)
            VALUES (?,'','宮城県','仙台市',?,?,?,'','',?,0,0,0,'unresearched','',?,?,?,'pending')""",
            (name, address, official_url, phone, pet, source_url, source_type, f"test|{source_type}|{name or address}"),
        )


def test_normalize_address_handles_japanese_numbering():
    assert normalize_address("宮城県仙台市青葉区本町1丁目2番3号") == normalize_address("宮城県 仙台市青葉区本町1-2-3")


def test_reconcile_exact_address_enriches_official_candidate(tmp_path):
    app, database = _app(tmp_path)
    _insert(database, name="", address="宮城県仙台市青葉区本町1丁目2番3号", source_type="宮城県公式 届出住宅一覧", source_url="https://www.pref.miyagi.jp/example")
    _insert(database, name="仙台ペットヴィラ", address="宮城県仙台市青葉区本町1-2-3", source_type="OpenStreetMap 公開POI", source_url="https://www.openstreetmap.org/node/1", official_url="https://example.com", phone="022-000-0000", pet=1)
    stats = reconcile_candidates(database, "宮城県")
    assert stats["matched"] == 1
    with sqlite3.connect(database) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM lead_candidates WHERE source_type LIKE '宮城県公式%'").fetchone()
    assert row["name"] == "仙台ペットヴィラ"
    assert row["official_url"] == "https://example.com"
    assert row["phone"] == "022-000-0000"
    assert row["pet_friendly"] == 1
    assert "候補自動照合" in row["research_notes"]


def test_reconcile_does_not_use_fuzzy_address(tmp_path):
    app, database = _app(tmp_path)
    _insert(database, name="", address="宮城県仙台市青葉区本町1-2-3", source_type="宮城県公式 届出住宅一覧", source_url="https://www.pref.miyagi.jp/example")
    _insert(database, name="別施設", address="宮城県仙台市青葉区本町1-2-4", source_type="OpenStreetMap 公開POI", source_url="https://www.openstreetmap.org/node/2")
    stats = reconcile_candidates(database, "宮城県")
    assert stats["matched"] == 0


def test_reconcile_route_registered(tmp_path):
    app, _ = _app(tmp_path)
    assert "/targets/reconcile" in {rule.rule for rule in app.url_map.iter_rules()}
