import io

from openpyxl import Workbook

from remaining_prefectures_official import parse_aomori_xlsx


def test_parse_aomori_xlsx_extracts_addresses():
    wb = Workbook()
    ws = wb.active
    ws.append(["届出番号", "届出住宅の所在地"])
    ws.append(["M020000001", "青森市本町1-2-3"])
    ws.append(["M020000002", "弘前市駅前2-3-4"])
    buf = io.BytesIO()
    wb.save(buf)
    records = parse_aomori_xlsx(buf.getvalue())
    assert [r["address"] for r in records] == ["青森市本町1-2-3", "弘前市駅前2-3-4"]


def test_remaining_routes_registered(tmp_path):
    import app as app_module
    from remaining_prefectures_official import register_remaining_prefectures_official

    database = tmp_path / "sales.db"
    test_app = app_module.create_app({"TESTING": True, "DATABASE": database, "SECRET_KEY": "test"})
    with test_app.app_context():
        app_module.init_db()
    register_remaining_prefectures_official(test_app)
    rules = {rule.rule for rule in test_app.url_map.iter_rules()}
    assert "/targets/import-iwate" in rules
    assert "/targets/import-akita" in rules
    assert "/targets/import-aomori" in rules
