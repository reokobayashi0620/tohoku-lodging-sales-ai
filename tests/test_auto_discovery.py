import sqlite3

from app import create_app
import auto_discovery
from auto_discovery import extract_official_site, import_records, parse_overpass, register_auto_discovery


def sample_payload():
    return {
        "elements": [
            {
                "type": "node",
                "id": 123,
                "lat": 38.2,
                "lon": 140.8,
                "tags": {
                    "name": "Pets Villa Test",
                    "tourism": "chalet",
                    "addr:city": "仙台市",
                    "addr:full": "宮城県仙台市青葉区1-2-3",
                    "website": "https://example.com/",
                    "contact:phone": "022-000-0000",
                    "dog": "yes",
                },
            }
        ]
    }


def test_parse_overpass_extracts_sales_signals():
    rows = parse_overpass(sample_payload(), "宮城県")
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Pets Villa Test"
    assert row["city"] == "仙台市"
    assert row["pet_friendly"] == 1
    assert row["whole_house"] == 1
    assert row["official_url"] == "https://example.com/"
    assert row["normalized_key"] == "osm|node|123"


def test_import_records_is_idempotent(tmp_path):
    db = tmp_path / "discovery.db"
    app = create_app({"TESTING": True, "DATABASE": db, "APP_USERNAME": "", "APP_PASSWORD": ""})
    records = parse_overpass(sample_payload(), "宮城県")
    first = import_records(db, records)
    second = import_records(db, records)
    assert first == (1, 0)
    assert second == (0, 1)
    with sqlite3.connect(db) as con:
        row = con.execute("SELECT name,pet_friendly,whole_house,source_type FROM lead_candidates").fetchone()
    assert row[0] == "Pets Villa Test"
    assert row[1] == 1
    assert row[2] == 1
    assert row[3] == auto_discovery.SOURCE_TYPE


def test_extract_official_site_finds_contact_and_attributes():
    html = '''
    <html><body>
      <a href="mailto:hello@example.jp">mail</a>
      <a href="tel:0221234567">phone</a>
      <a href="/contact">お問い合わせ</a>
      <p>愛犬同伴OK。一棟貸しの貸別荘です。無垢床を採用しています。</p>
      <script type="application/ld+json">
      {"@type":"LodgingBusiness","name":"Test Villa","parentOrganization":{"@type":"Organization","name":"株式会社テスト運営"}}
      </script>
    </body></html>
    '''
    result = extract_official_site(html, "https://example.jp/", "Test Villa")
    assert result["company_name"] == "株式会社テスト運営"
    assert result["email"] == "hello@example.jp"
    assert result["phone"] == "0221234567"
    assert result["contact_url"] == "https://example.jp/contact"
    assert result["pet_friendly"] == 1
    assert result["whole_house"] == 1
    assert result["wood_floor"] == 1


def test_auto_discovery_route_imports_candidates(tmp_path, monkeypatch):
    db = tmp_path / "route.db"
    app = create_app({"TESTING": True, "DATABASE": db, "APP_USERNAME": "", "APP_PASSWORD": ""})
    register_auto_discovery(app)
    monkeypatch.setattr(auto_discovery, "fetch_osm_records", lambda prefecture: parse_overpass(sample_payload(), prefecture))
    client = app.test_client()
    response = client.post("/auto-discovery/discover", data={"prefecture": "宮城県"}, follow_redirects=True)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "自動営業先発掘" in body
    assert "新規1件" in body
    with sqlite3.connect(db) as con:
        count = con.execute("SELECT COUNT(*) FROM lead_candidates WHERE source_type=?", (auto_discovery.SOURCE_TYPE,)).fetchone()[0]
    assert count == 1
