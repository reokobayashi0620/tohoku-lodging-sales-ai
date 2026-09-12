import sqlite3

import app as app_module


def make_app(tmp_path):
    return app_module.create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "source-intake.db",
        "SECRET_KEY": "test",
    })


def insert_candidate(application):
    with sqlite3.connect(application.config["DATABASE"]) as con:
        cursor = con.execute(
            """INSERT INTO lead_candidates
               (name,prefecture,city,address,official_url,source_url,source_type,normalized_key,status)
               VALUES ('','宮城県','仙台市','仙台市青葉区大町二丁目9-18','','https://example.test/source.pdf','仙台市公開資料','source-intake-test','pending')"""
        )
        return cursor.lastrowid


def test_candidate_edit_has_source_intake_ui(tmp_path):
    application = make_app(tmp_path)
    candidate_id = insert_candidate(application)
    client = application.test_client()

    response = client.get(f"/candidates/{candidate_id}/edit")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "PHASE 2-6" in text
    assert "公開ページから半自動抽出" in text
    assert 'id="source-evidence-url"' in text
    assert 'id="public-source-text"' in text
    assert 'id="extract-source"' in text
    assert "本文から候補を抽出" in text


def test_source_intake_script_keeps_human_review(tmp_path):
    application = make_app(tmp_path)
    candidate_id = insert_candidate(application)
    client = application.test_client()

    text = client.get(f"/candidates/{candidate_id}/edit").get_data(as_text=True)

    assert "自動抽出は候補提示です" in text
    assert "既に入力済みの文字項目は上書きしません" in text
    assert "Airbnb・Booking等への自動アクセスやスクレイピングは行いません" in text
    assert "元ページと照合してから" in text
    assert "setIfEmpty" in text
    assert "pet_friendly" in text
    assert "whole_house" in text
    assert "wood_floor" in text
    assert "multiple_facilities" in text


def test_source_intake_extracts_expected_patterns_in_client_script(tmp_path):
    application = make_app(tmp_path)
    candidate_id = insert_candidate(application)
    client = application.test_client()

    text = client.get(f"/candidates/{candidate_id}/edit").get_data(as_text=True)

    assert "施設名" in text
    assert "運営会社" in text
    assert "お問い合わせ" in text
    assert "ペット可" in text
    assert "一棟貸し" in text
    assert "フローリング" in text
    assert "系列施設" in text
