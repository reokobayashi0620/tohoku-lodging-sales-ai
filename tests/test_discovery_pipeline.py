import sqlite3

from app import create_app
from discovery_pipeline import build_ready_queue, register_discovery_pipeline


def _make_app(tmp_path):
    db_path = tmp_path / "pipeline.db"
    return create_app({"TESTING": True, "DATABASE": db_path, "APP_USERNAME": "", "APP_PASSWORD": ""})


def _insert_candidate(database, **overrides):
    values = {"name":"ペットヴィラ仙台","company_name":"株式会社テスト宿泊","prefecture":"宮城県","city":"仙台市","address":"宮城県仙台市青葉区1-1","official_url":"https://example.com","phone":"022-000-0000","email":"","contact_url":"https://example.com/contact","pet_friendly":1,"whole_house":1,"multiple_facilities":0,"wood_floor":1,"research_status":"verified","research_notes":"公式確認済","source_url":"https://example.com/source","source_type":"test","normalized_key":"pipeline-test-1"}
    values.update(overrides)
    with sqlite3.connect(database) as con:
        con.execute("""INSERT INTO lead_candidates (name,company_name,prefecture,city,address,official_url,phone,email,contact_url,pet_friendly,whole_house,multiple_facilities,wood_floor,research_status,research_notes,source_url,source_type,normalized_key,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')""", tuple(values[k] for k in values))


def test_ready_queue_includes_sales_draft(tmp_path):
    app = _make_app(tmp_path)
    _insert_candidate(app.config["DATABASE"])
    ready = build_ready_queue(app.config["DATABASE"], prefecture="宮城県")
    assert len(ready) == 1
    assert ready[0]["band"] == "S"
    assert "ペット" in ready[0]["theme"]
    assert "ペットヴィラ仙台" in ready[0]["draft"]


def test_ready_queue_filters_prefecture(tmp_path):
    app = _make_app(tmp_path)
    _insert_candidate(app.config["DATABASE"])
    assert build_ready_queue(app.config["DATABASE"], prefecture="青森県") == []


def test_pipeline_page_renders_ready_candidate(tmp_path):
    app = _make_app(tmp_path)
    register_discovery_pipeline(app)
    _insert_candidate(app.config["DATABASE"])
    response = app.test_client().get("/pipeline?prefecture=宮城県")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "一括営業パイプライン" in text
    assert "ペットヴィラ仙台" in text
    assert "営業文を確認" in text
    assert "自動送信はしません" in text


def test_pipeline_rejects_invalid_prefecture(tmp_path):
    app = _make_app(tmp_path)
    register_discovery_pipeline(app)
    response = app.test_client().post("/pipeline/run", data={"prefecture":"東京都"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/pipeline")
