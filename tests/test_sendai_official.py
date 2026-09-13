import sqlite3

from sendai_official import import_sendai_official_records, register_sendai_official


def test_import_sendai_official_records_inserts_and_deduplicates(app):
    database = app.config["DATABASE"]
    addresses = ["仙台市青葉区大町二丁目9-18", "仙台市太白区萩ケ丘2-27"]
    first = import_sendai_official_records(database, addresses, "https://example.test/sendai.pdf")
    second = import_sendai_official_records(database, addresses, "https://example.test/sendai.pdf")
    assert first["inserted"] == 2
    assert second["inserted"] == 0
    assert second["duplicates"] == 2
    with sqlite3.connect(database) as con:
        rows = con.execute("SELECT city,address,source_type FROM lead_candidates WHERE source_type LIKE '仙台市公式%'").fetchall()
    assert len(rows) == 2
    assert all(row[0] == "仙台市" for row in rows)


def test_sendai_import_route_is_registered(app):
    register_sendai_official(app)
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/targets/import-sendai" in rules
