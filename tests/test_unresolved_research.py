import sqlite3

from app import create_app
from unresolved_research import build_search_queries, register_unresolved_research, unresolved_candidates


def _app(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "sales.db"), "APP_USERNAME": "", "APP_PASSWORD": ""})
    register_unresolved_research(app)
    return app


def _insert(app, name="", key="test:miyagi:ishinomaki:izumicho-2-9-10", **fields):
    values = {"name": name, "prefecture": "宮城県", "city": "石巻市", "address": "石巻市泉町2-9-10", "source_type": "宮城県公式 届出", "source_url": "https://www.pref.miyagi.jp/", "status": "pending", "research_status": "pending", "normalized_key": key, "official_url": "", "company_name": "", "phone": "", "email": "", "contact_url": "", "pet_friendly": 0, "whole_house": 0, "wood_floor": 0, "multiple_facilities": 0}
    values.update(fields)
    con = sqlite3.connect(app.config["DATABASE"])
    con.execute("""INSERT INTO lead_candidates (name,prefecture,city,address,source_type,source_url,status,research_status,normalized_key,official_url,company_name,phone,email,contact_url,pet_friendly,whole_house,wood_floor,multiple_facilities) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", tuple(values[k] for k in values))
    con.commit(); con.close()


def test_search_queries_use_exact_address():
    row = {"address": "石巻市泉町2-9-10", "prefecture": "宮城県", "city": "石巻市"}
    queries = build_search_queries(row)
    assert len(queries) == 4
    assert '"石巻市泉町2-9-10" 民泊' == queries[0]["query"]
    assert "特定商取引法" in queries[3]["query"]
    assert queries[0]["url"].startswith("https://www.google.com/search?q=")


def test_unresolved_official_candidate_is_queued(tmp_path):
    app = _app(tmp_path); _insert(app)
    items = unresolved_candidates(app.config["DATABASE"], "宮城県")
    assert len(items) == 1
    assert items[0]["missing_identity"] is True
    assert items[0]["missing_operator"] is True


def test_high_value_partial_candidate_is_researched_first(tmp_path):
    app = _app(tmp_path)
    _insert(app, key="plain")
    _insert(app, name="犬と泊まれる一棟貸し", key="high", pet_friendly=1, whole_house=1, wood_floor=1)
    items = unresolved_candidates(app.config["DATABASE"], "宮城県")
    assert len(items) == 2
    assert items[0]["candidate"]["normalized_key"] == "high"
    assert items[0]["research_priority"] > items[1]["research_priority"]


def test_page_renders(tmp_path):
    app = _app(tmp_path); _insert(app)
    response = app.test_client().get("/targets/unresolved?prefecture=宮城県")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "営業価値が高い未特定民泊から調査する" in text
    assert "石巻市泉町2-9-10" in text
    assert "調査優先" in text
