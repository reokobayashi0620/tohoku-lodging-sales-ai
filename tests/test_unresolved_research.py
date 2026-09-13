import sqlite3

from app import create_app
from unresolved_research import build_search_queries, register_unresolved_research, unresolved_candidates


def _app(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "sales.db"), "APP_USERNAME": "", "APP_PASSWORD": ""})
    register_unresolved_research(app)
    return app


def _insert(app):
    con = sqlite3.connect(app.config["DATABASE"])
    con.execute("""INSERT INTO lead_candidates (name,prefecture,city,address,source_type,source_url,status,research_status,normalized_key) VALUES (?,?,?,?,?,?,?,?,?)""", ("", "宮城県", "石巻市", "石巻市泉町2-9-10", "宮城県公式 届出", "https://www.pref.miyagi.jp/", "pending", "pending", "test:miyagi:ishinomaki:izumicho-2-9-10"))
    con.commit(); con.close()


def test_search_queries_use_exact_address():
    row = {"address": "石巻市泉町2-9-10", "prefecture": "宮城県", "city": "石巻市"}
    queries = build_search_queries(row)
    assert len(queries) == 4
    assert '"石巻市泉町2-9-10" 民泊' == queries[0]["query"]
    assert queries[0]["url"].startswith("https://www.google.com/search?q=")


def test_unresolved_official_candidate_is_queued(tmp_path):
    app = _app(tmp_path); _insert(app)
    items = unresolved_candidates(app.config["DATABASE"], "宮城県")
    assert len(items) == 1
    assert items[0]["missing_identity"] is True
    assert items[0]["missing_operator"] is True


def test_page_renders(tmp_path):
    app = _app(tmp_path); _insert(app)
    response = app.test_client().get("/targets/unresolved?prefecture=宮城県")
    assert response.status_code == 200
    assert "所在地しか分からない民泊を特定する" in response.get_data(as_text=True)
    assert "石巻市泉町2-9-10" in response.get_data(as_text=True)
