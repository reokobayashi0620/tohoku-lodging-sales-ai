import sqlite3

import app as app_module
from simple_sales_flow import build_flow, register_simple_sales_flow, seed_businesses


def make_app(tmp_path):
    app = app_module.create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "sales.db",
        "APP_USERNAME": "",
        "APP_PASSWORD": "",
    })
    register_simple_sales_flow(app)
    return app


def test_seed_businesses_is_idempotent(tmp_path):
    app = make_app(tmp_path)
    assert seed_businesses(app.config["DATABASE"]) == 8
    assert seed_businesses(app.config["DATABASE"]) == 0
    with sqlite3.connect(app.config["DATABASE"]) as con:
        count = con.execute("SELECT COUNT(*) FROM lead_candidates WHERE source_type='事業者発掘'").fetchone()[0]
    assert count == 8


def test_flow_moves_sent_and_replied(tmp_path):
    app = make_app(tmp_path)
    seed_businesses(app.config["DATABASE"])
    groups = build_flow(app.config["DATABASE"])
    assert len(groups["new"]) == 8
    candidate_id = groups["new"][0]["candidate"]["id"]

    client = app.test_client()
    response = client.post(
        f"/sales-flow/{candidate_id}/activity",
        data={"activity_type": "sent", "channel": "email"},
    )
    assert response.status_code == 302
    assert any(item["candidate"]["id"] == candidate_id for item in build_flow(app.config["DATABASE"])["sent"])

    response = client.post(
        f"/sales-flow/{candidate_id}/activity",
        data={"activity_type": "replied", "channel": "email"},
    )
    assert response.status_code == 302
    assert any(item["candidate"]["id"] == candidate_id for item in build_flow(app.config["DATABASE"])["replied"])


def test_sales_flow_page_and_discovery_route(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    response = client.get("/sales-flow")
    assert response.status_code == 200
    assert "見つける" in response.get_data(as_text=True)

    response = client.post("/sales-flow/discover", follow_redirects=True)
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "宮城民泊運営代行株式会社" in text
    assert "株式会社エイチ・ティー・プランニング" in text
    assert "合同会社Bebop" in text
    assert "株式会社Blue First" in text
    assert "株式会社ガイア" in text
    assert "株式会社たびのレシピ" in text
