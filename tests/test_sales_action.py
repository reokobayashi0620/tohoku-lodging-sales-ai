import sqlite3

import app as app_module
from sales_action import build_sales_draft, recommend_theme, register_sales_action


def make_app(tmp_path):
    application = app_module.create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "test.db",
        "APP_USERNAME": "",
        "APP_PASSWORD": "",
    })
    register_sales_action(application)
    return application


def candidate_row(**overrides):
    data = {
        "name": "森の宿",
        "company_name": "株式会社テスト",
        "prefecture": "宮城県",
        "city": "仙台市",
        "address": "仙台市青葉区1-2-3",
        "official_url": "https://example.test/facility",
        "phone": "022-000-0000",
        "email": "info@example.test",
        "contact_url": "https://example.test/contact",
        "pet_friendly": 0,
        "whole_house": 0,
        "multiple_facilities": 0,
        "wood_floor": 0,
        "research_status": "verified",
    }
    data.update(overrides)
    return data


def test_recommend_theme_prefers_pet_then_floor():
    assert recommend_theme(candidate_row(pet_friendly=1, wood_floor=1)) == "pet_damage"
    assert recommend_theme(candidate_row(wood_floor=1)) == "floor_repair"
    assert recommend_theme(candidate_row(whole_house=1)) == "coating"


def test_build_sales_draft_uses_selected_theme_without_claiming_condition():
    draft = build_sales_draft(candidate_row(), "floor_repair")
    assert "森の宿" in draft
    assert "交換・張り替え前" in draft
    assert "写真を数枚" in draft
    assert "傷んでいる" not in draft


def test_sales_action_page_renders_draft_and_human_review_notice(tmp_path):
    application = make_app(tmp_path)
    with sqlite3.connect(application.config["DATABASE"]) as con:
        con.execute(
            """INSERT INTO lead_candidates
            (name,company_name,prefecture,city,address,official_url,phone,email,contact_url,
             pet_friendly,whole_house,multiple_facilities,wood_floor,research_status,source_url,source_type,normalized_key,status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')""",
            ("森の宿","株式会社テスト","宮城県","仙台市","仙台市青葉区1-2-3","https://example.test/facility",
             "022-000-0000","info@example.test","https://example.test/contact",1,1,0,1,"verified","https://example.test/source","test","key-1"),
        )
        candidate_id = con.execute("SELECT id FROM lead_candidates").fetchone()[0]
    response = application.test_client().get(f"/sales-action/{candidate_id}")
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "営業アクション" in text
    assert "ペット傷・汚れ対策" in text
    assert "自動送信は行いません" in text
    assert "info@example.test" in text
