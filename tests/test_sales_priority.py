import sqlite3

from app import create_app
from sales_priority import register_sales_priority, score_candidate


class Row(dict):
    __getattr__ = dict.get


def test_score_requires_verified_and_contact_for_s_band():
    base = Row(pet_friendly=1, whole_house=1, wood_floor=1, multiple_facilities=1,
               company_name="運営会社", phone="", email="", contact_url="",
               official_url="https://example.com", research_status="verified", prefecture="宮城県")
    result = score_candidate(base)
    assert result["score"] >= 70
    assert result["band"] != "S"
    base["email"] = "info@example.com"
    result = score_candidate(base)
    assert result["band"] == "S"
    assert result["action"] == "今すぐ営業文を作成"


def test_unknown_information_does_not_add_fit_points():
    row = Row(pet_friendly=0, whole_house=0, wood_floor=0, multiple_facilities=0,
              company_name="", phone="", email="", contact_url="", official_url="",
              research_status="unresearched", prefecture="青森県")
    result = score_candidate(row)
    assert result["score"] == 0
    assert result["band"] == "C"
    assert "調査" in result["missing"]


def test_sales_priority_route_renders_ranked_candidates(tmp_path):
    db_path = tmp_path / "sales.db"
    app = create_app({"TESTING": True, "DATABASE": db_path, "APP_USERNAME": "", "APP_PASSWORD": ""})
    register_sales_priority(app)
    with sqlite3.connect(db_path) as con:
        con.execute("""INSERT INTO lead_candidates
          (name,company_name,prefecture,city,address,official_url,email,pet_friendly,whole_house,wood_floor,multiple_facilities,research_status,source_url,source_type,normalized_key,status)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')""",
          ("優先宿","運営社","宮城県","仙台市","仙台市青葉区1","https://example.com","info@example.com",1,1,1,1,"verified","src","test","miyagi|sendai|1"))
    client = app.test_client()
    response = client.get("/sales-priority")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "営業優先順位ダッシュボード" in text
    assert "優先宿" in text
    assert "今すぐ営業文を作成" in text
    assert "S" in text
