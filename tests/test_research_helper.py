import sqlite3

import app as app_module


def make_app(tmp_path):
    return app_module.create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "research-helper.db",
        "SECRET_KEY": "test",
    })


def insert_candidate(application):
    with sqlite3.connect(application.config["DATABASE"]) as con:
        cursor = con.execute(
            """INSERT INTO lead_candidates
               (name,prefecture,city,address,official_url,source_url,source_type,normalized_key,status)
               VALUES ('','宮城県','仙台市','仙台市青葉区大町二丁目9-18','','https://example.test/source.pdf','仙台市公開資料','helper-test','pending')"""
        )
        return cursor.lastrowid


def test_candidate_edit_has_research_starter(tmp_path):
    application = make_app(tmp_path)
    candidate_id = insert_candidate(application)
    client = application.test_client()

    response = client.get(f"/candidates/{candidate_id}/edit")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "調査スターター" in text
    assert "住所＋民泊を検索" in text
    assert "運営会社を検索" in text
    assert "ペット可・一棟貸しを検索" in text
    assert "Airbnb候補を検索" in text
    assert "Booking候補を検索" in text
    assert "仙台市青葉区大町二丁目9-18 民泊 宿泊" in text


def test_research_forms_are_get_only_and_external(tmp_path):
    application = make_app(tmp_path)
    candidate_id = insert_candidate(application)
    client = application.test_client()

    text = client.get(f"/candidates/{candidate_id}/edit").get_data(as_text=True)

    assert 'method="get" action="https://www.google.com/search"' in text
    assert 'target="_blank"' in text
    assert "site:airbnb.com" in text
    assert "site:booking.com" in text
