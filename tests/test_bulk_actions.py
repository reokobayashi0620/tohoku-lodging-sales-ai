import sqlite3

import app as app_module
from bulk_actions import register_bulk_actions


def make_app(tmp_path):
    application = app_module.create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "bulk-actions.db",
        "SECRET_KEY": "test",
    })
    register_bulk_actions(application)
    return application


def insert_candidate(application, key, research_status="unresearched", status="pending"):
    with sqlite3.connect(application.config["DATABASE"]) as con:
        cursor = con.execute(
            """INSERT INTO lead_candidates
               (name,prefecture,city,address,official_url,source_url,source_type,normalized_key,status,research_status)
               VALUES ('','宮城県','仙台市',?,'','https://example.test/source.pdf','テスト公開資料',?,?,?)""",
            (f"仙台市青葉区テスト{key}", key, status, research_status),
        )
        return cursor.lastrowid


def get_candidate(application, candidate_id):
    with sqlite3.connect(application.config["DATABASE"]) as con:
        con.row_factory = sqlite3.Row
        return con.execute("SELECT * FROM lead_candidates WHERE id=?", (candidate_id,)).fetchone()


def test_bulk_start_research_updates_only_unresearched_pending(tmp_path):
    application = make_app(tmp_path)
    first = insert_candidate(application, "bulk-1")
    verified = insert_candidate(application, "bulk-2", research_status="verified")
    promoted = insert_candidate(application, "bulk-3", status="promoted")
    client = application.test_client()

    response = client.post("/candidates/bulk", data={
        "action": "start_research",
        "candidate_ids": [str(first), str(verified), str(promoted)],
        "return_status": "pending",
    })

    assert response.status_code == 302
    assert get_candidate(application, first)["research_status"] == "researching"
    assert get_candidate(application, verified)["research_status"] == "verified"
    assert get_candidate(application, promoted)["research_status"] == "unresearched"


def test_bulk_exclude_only_pending_candidates(tmp_path):
    application = make_app(tmp_path)
    pending = insert_candidate(application, "bulk-4")
    promoted = insert_candidate(application, "bulk-5", status="promoted")
    client = application.test_client()

    client.post("/candidates/bulk", data={
        "action": "exclude",
        "candidate_ids": [str(pending), str(promoted)],
    })

    assert get_candidate(application, pending)["status"] == "excluded"
    assert get_candidate(application, promoted)["status"] == "promoted"


def test_bulk_requires_selection(tmp_path):
    application = make_app(tmp_path)
    client = application.test_client()

    response = client.post("/candidates/bulk", data={"action": "start_research"}, follow_redirects=True)
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "候補を1件以上選択してください" in text


def test_candidates_page_has_bulk_controls_and_filters(tmp_path):
    application = make_app(tmp_path)
    insert_candidate(application, "bulk-6")
    client = application.test_client()

    response = client.get("/candidates?status=pending")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "表示中を全選択" in text
    assert "選択した候補に実行" in text
    assert 'id="research-filter"' in text
    assert 'id="priority-filter"' in text
    assert 'action="/candidates/bulk"' in text
    assert "確認済への変更は一括操作に含めず" in text
