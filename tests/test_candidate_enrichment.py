import sqlite3

import app as app_module


def make_app(tmp_path):
    return app_module.create_app({"TESTING": True, "DATABASE": tmp_path / "candidate.db", "SECRET_KEY": "test"})


def insert_candidate(database):
    key = app_module.candidate_key("宮城県", "仙台市", "仙台市青葉区一番町1-2-3")
    with sqlite3.connect(database) as con:
        cursor = con.execute(
            """INSERT INTO lead_candidates
            (name,prefecture,city,address,official_url,source_url,source_type,normalized_key,status)
            VALUES ('','宮城県','仙台市','仙台市青葉区一番町1-2-3','','https://example.test/source.pdf','仙台市公開資料',?,'pending')""",
            (key,),
        )
        return cursor.lastrowid


def test_candidate_edit_saves_research_fields(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    candidate_id = insert_candidate(app.config["DATABASE"])

    response = client.post(f"/candidates/{candidate_id}/edit", data={
        "name": "青葉ステイ",
        "company_name": "東北ホスピタリティ株式会社",
        "official_url": "https://example.test/aoba",
        "phone": "022-000-0000",
        "email": "info@example.test",
        "contact_url": "https://example.test/contact",
        "pet_friendly": "on",
        "whole_house": "on",
        "wood_floor": "on",
        "research_status": "verified",
        "research_notes": "公式サイトで確認",
    }, follow_redirects=True)

    assert response.status_code == 200
    assert "候補の調査情報を保存しました" in response.get_data(as_text=True)
    with sqlite3.connect(app.config["DATABASE"]) as con:
        row = con.execute(
            """SELECT name,company_name,official_url,pet_friendly,whole_house,wood_floor,
            research_status,research_notes FROM lead_candidates WHERE id=?""",
            (candidate_id,),
        ).fetchone()
    assert row == (
        "青葉ステイ", "東北ホスピタリティ株式会社", "https://example.test/aoba",
        1, 1, 1, "verified", "公式サイトで確認",
    )


def test_promote_inherits_candidate_research_and_priority(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    candidate_id = insert_candidate(app.config["DATABASE"])
    client.post(f"/candidates/{candidate_id}/edit", data={
        "name": "青葉ステイ",
        "company_name": "東北ホスピタリティ株式会社",
        "official_url": "https://example.test/aoba",
        "contact_url": "https://example.test/contact",
        "pet_friendly": "on",
        "whole_house": "on",
        "wood_floor": "on",
        "research_status": "verified",
        "research_notes": "ペット可・一棟貸し・木質床を確認",
    })

    response = client.post(f"/candidates/{candidate_id}/promote", follow_redirects=True)
    assert response.status_code == 200
    with sqlite3.connect(app.config["DATABASE"]) as con:
        row = con.execute(
            """SELECT name,company_name,official_url,contact_url,pet_friendly,whole_house,wood_floor,
            notes,priority,status FROM facilities WHERE address='仙台市青葉区一番町1-2-3'"""
        ).fetchone()
    assert row[0] == "青葉ステイ"
    assert row[1] == "東北ホスピタリティ株式会社"
    assert row[2] == "https://example.test/aoba"
    assert row[3] == "https://example.test/contact"
    assert row[4:7] == (1, 1, 1)
    assert row[7] == "ペット可・一棟貸し・木質床を確認"
    assert row[8] == "S"
    assert row[9] == "未連絡"


def test_promote_uses_clear_unknown_name_placeholder(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    candidate_id = insert_candidate(app.config["DATABASE"])
    client.post(f"/candidates/{candidate_id}/promote")
    with sqlite3.connect(app.config["DATABASE"]) as con:
        name = con.execute("SELECT name FROM facilities WHERE address='仙台市青葉区一番町1-2-3'").fetchone()[0]
    assert name.startswith("名称未確認（")
