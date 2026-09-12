import sqlite3

import app as app_module


def make_app(tmp_path):
    return app_module.create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "research-queue.db",
        "SECRET_KEY": "test",
    })


def insert_candidate(application, **overrides):
    values = {
        "name": "",
        "prefecture": "宮城県",
        "city": "仙台市",
        "address": "仙台市青葉区大町二丁目9-18",
        "official_url": "",
        "source_url": "https://example.test/source.pdf",
        "source_type": "仙台市公開資料",
        "normalized_key": overrides.pop("normalized_key", "queue-test"),
        "status": "pending",
        "company_name": "",
        "phone": "",
        "email": "",
        "contact_url": "",
        "pet_friendly": 0,
        "whole_house": 0,
        "multiple_facilities": 0,
        "wood_floor": 0,
        "research_status": "unresearched",
        "research_notes": "",
    }
    values.update(overrides)
    columns = ",".join(values)
    placeholders = ",".join("?" for _ in values)
    with sqlite3.connect(application.config["DATABASE"]) as con:
        cursor = con.execute(
            f"INSERT INTO lead_candidates ({columns}) VALUES ({placeholders})",
            list(values.values()),
        )
        return cursor.lastrowid


def test_candidates_page_shows_research_queue_and_next_action(tmp_path):
    application = make_app(tmp_path)
    insert_candidate(application)
    client = application.test_client()

    response = client.get("/candidates")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "調査キュー" in text
    assert "情報充足" in text
    assert "次の確認" in text
    assert "施設名" in text
    assert 'data-research-rank="0"' in text
    assert 'data-completeness="0"' in text


def test_candidate_edit_shows_progress_and_checklist(tmp_path):
    application = make_app(tmp_path)
    candidate_id = insert_candidate(
        application,
        name="青葉ステイ",
        company_name="青葉運営株式会社",
        official_url="https://example.test/stay",
        contact_url="https://example.test/contact",
        pet_friendly=1,
        research_notes="公式サイトで確認",
        research_status="verified",
    )
    client = application.test_client()

    response = client.get(f"/candidates/{candidate_id}/edit")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "調査進捗 100%" in text
    assert "営業リストへ登録できます" in text
    assert "✓ 施設名" in text
    assert "✓ 連絡先" in text
    assert "✓ 営業属性" in text
