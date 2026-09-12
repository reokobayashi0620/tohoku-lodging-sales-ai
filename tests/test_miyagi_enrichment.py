import sqlite3

import app as app_module
import miyagi_enrichment as enrichment


def make_app(tmp_path):
    application = app_module.create_app({
        "TESTING": True,
        "DATABASE": tmp_path / "miyagi-enrichment.db",
        "SECRET_KEY": "test",
    })
    enrichment.register_miyagi_enrichment(application)
    return application


def insert_candidate(application, address="刈田郡蔵王町遠刈田温泉字七日原2-418"):
    with sqlite3.connect(application.config["DATABASE"]) as con:
        cursor = con.execute(
            """INSERT INTO lead_candidates
               (name,prefecture,city,address,official_url,source_url,source_type,normalized_key,status)
               VALUES ('','宮城県','刈田郡蔵王町',?,'','https://example.test/source.pdf','test','phase28-key','pending')""",
            (address,),
        )
        return cursor.lastrowid


def sample_html():
    return """
    <html><body><table>
      <tr><th>届出番号</th><th>受理年月日</th><th>商号・名称</th><th>届出者</th><th>施設所在地</th><th>電話番号</th><th>メール</th><th>HP</th></tr>
      <tr>
        <td>M040047775</td><td>令和7年2月5日</td><td>PetsFriendlyGokyo</td><td>有限会社五橋商事</td>
        <td>989-0916 刈田郡蔵王町遠刈田温泉字七日原2-418</td><td>022-724-7447</td>
        <td><a href="mailto:info@example.test">Mail</a></td>
        <td><a href="https://gokyo.example.test/">施設HP</a></td>
      </tr>
    </table></body></html>
    """


def test_parse_miyagi_detail_html_extracts_public_fields():
    records = enrichment.parse_miyagi_detail_html(sample_html())
    assert len(records) == 1
    record = records[0]
    assert record["name"] == "PetsFriendlyGokyo"
    assert record["operator"] == "有限会社五橋商事"
    assert record["phone"] == "022-724-7447"
    assert record["email"] == "info@example.test"
    assert record["official_url"] == "https://gokyo.example.test/"


def test_normalize_match_address_ignores_postcode_prefecture_and_width():
    left = enrichment.normalize_match_address("〒989-0916 宮城県刈田郡蔵王町遠刈田温泉字七日原２－４１８")
    right = enrichment.normalize_match_address("刈田郡蔵王町遠刈田温泉字七日原2-418")
    assert left == right


def test_enrich_pending_candidate_only_fills_empty_fields(tmp_path):
    application = make_app(tmp_path)
    candidate_id = insert_candidate(application)
    records = enrichment.parse_miyagi_detail_html(sample_html())

    stats = enrichment.enrich_pending_candidates(application.config["DATABASE"], records)
    assert stats == {"matched": 1, "changed": 1, "source_records": 1}

    with sqlite3.connect(application.config["DATABASE"]) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM lead_candidates WHERE id=?", (candidate_id,)).fetchone()
    assert row["name"] == "PetsFriendlyGokyo"
    assert row["company_name"] == "有限会社五橋商事"
    assert row["phone"] == "022-724-7447"
    assert row["email"] == "info@example.test"
    assert row["official_url"] == "https://gokyo.example.test/"
    assert row["research_status"] == "researching"
    assert "宮城県公式HTML自動照合" in row["research_notes"]


def test_enrichment_does_not_overwrite_existing_candidate_data(tmp_path):
    application = make_app(tmp_path)
    candidate_id = insert_candidate(application)
    with sqlite3.connect(application.config["DATABASE"]) as con:
        con.execute(
            "UPDATE lead_candidates SET name='手動確認済み名称', phone='090-0000-0000' WHERE id=?",
            (candidate_id,),
        )

    enrichment.enrich_pending_candidates(
        application.config["DATABASE"],
        enrichment.parse_miyagi_detail_html(sample_html()),
    )
    with sqlite3.connect(application.config["DATABASE"]) as con:
        row = con.execute("SELECT name,phone FROM lead_candidates WHERE id=?", (candidate_id,)).fetchone()
    assert row == ("手動確認済み名称", "090-0000-0000")


def test_enrichment_page_and_route_are_registered(tmp_path, monkeypatch):
    application = make_app(tmp_path)
    insert_candidate(application)
    monkeypatch.setattr(enrichment, "fetch_miyagi_detail_records", lambda: enrichment.parse_miyagi_detail_html(sample_html()))
    client = application.test_client()

    page = client.get("/enrichment")
    assert page.status_code == 200
    assert "宮城県公式情報で自動照合" in page.get_data(as_text=True)

    response = client.post("/candidates/enrich-miyagi", follow_redirects=True)
    assert response.status_code == 200
    assert "住所一致1件・更新1件" in response.get_data(as_text=True)
