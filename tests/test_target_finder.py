import sqlite3

from app import create_app
from target_finder import find_targets, register_target_finder, target_fit


def _app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": tmp_path / "targets.db", "APP_USERNAME": "", "APP_PASSWORD": ""})


def _insert(database, name, source_type, source_url, normalized_key, **overrides):
    values = {
        "name": name, "company_name": "", "prefecture": "宮城県", "city": "蔵王町", "address": "宮城県蔵王町",
        "official_url": "", "phone": "", "email": "", "contact_url": "", "pet_friendly": 0, "whole_house": 0,
        "multiple_facilities": 0, "wood_floor": 0, "research_status": "unresearched", "research_notes": "",
        "source_url": source_url, "source_type": source_type, "normalized_key": normalized_key,
    }
    values.update(overrides)
    with sqlite3.connect(database) as con:
        con.execute("""INSERT INTO lead_candidates
        (name,company_name,prefecture,city,address,official_url,phone,email,contact_url,pet_friendly,whole_house,multiple_facilities,wood_floor,research_status,research_notes,source_url,source_type,normalized_key,status)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')""", tuple(values[k] for k in values))


def test_official_minpaku_beats_osm(tmp_path):
    app = _app(tmp_path)
    db = app.config["DATABASE"]
    _insert(db, "蔵王ペット貸別荘", "宮城県 民泊届出一覧", "https://www.pref.miyagi.jp/example", "official-1", pet_friendly=1, whole_house=1, wood_floor=1, official_url="https://example.com", contact_url="https://example.com/contact")
    _insert(db, "一般ホテル", "OpenStreetMap 公開POI", "https://openstreetmap.org/1", "osm-1")
    rows = find_targets(db, prefecture="宮城県")
    assert len(rows) == 1
    assert rows[0]["candidate"]["name"] == "蔵王ペット貸別荘"
    assert rows[0]["target_band"] == "S"
    assert rows[0]["sales_ready"] is True


def test_address_only_official_candidate_never_becomes_sales_ready(tmp_path):
    app = _app(tmp_path)
    db = app.config["DATABASE"]
    _insert(db, "", "宮城県公式 住宅宿泊事業法届出住宅一覧", "https://www.pref.miyagi.jp/example", "official-address-only", pet_friendly=1, whole_house=1, wood_floor=1)
    row = find_targets(db)[0]
    assert row["sales_ready"] is False
    assert row["target_band"] in {"B", "C"}
    assert row["target_score"] <= 35


def test_named_candidate_without_contact_is_research_not_sales_ready(tmp_path):
    app = _app(tmp_path)
    db = app.config["DATABASE"]
    _insert(db, "蔵王貸別荘", "宮城県 民泊届出一覧", "https://www.pref.miyagi.jp/example", "official-no-contact", whole_house=1, official_url="https://example.com")
    row = find_targets(db)[0]
    assert row["sales_ready"] is False
    assert row["target_band"] == "B"


def test_sales_ready_candidates_sort_before_research_candidates(tmp_path):
    app = _app(tmp_path)
    db = app.config["DATABASE"]
    _insert(db, "", "宮城県公式 住宅宿泊事業法届出住宅一覧", "https://www.pref.miyagi.jp/example", "research", pet_friendly=1, whole_house=1, wood_floor=1)
    _insert(db, "蔵王ヴィラ", "宮城県 民泊届出一覧", "https://www.pref.miyagi.jp/example", "ready", official_url="https://villa.example", email="sales@example.com")
    rows = find_targets(db)
    assert rows[0]["candidate"]["name"] == "蔵王ヴィラ"
    assert rows[0]["sales_ready"] is True


def test_osm_can_be_included_as_reference(tmp_path):
    app = _app(tmp_path)
    db = app.config["DATABASE"]
    _insert(db, "一般ホテル", "OpenStreetMap 公開POI", "https://openstreetmap.org/1", "osm-1")
    assert find_targets(db) == []
    assert len(find_targets(db, include_osm=True)) == 1


def test_target_page_renders(tmp_path):
    app = _app(tmp_path)
    register_target_finder(app)
    _insert(app.config["DATABASE"], "古民家一棟貸し", "宮城県 民泊届出一覧", "https://www.pref.miyagi.jp/example", "official-2", whole_house=1)
    response = app.test_client().get("/targets?prefecture=宮城県")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "民泊・貸別荘 特化の営業先発掘" in text
    assert "古民家一棟貸し" in text
    assert "OpenStreetMap由来の一般宿泊POIを除外" in text
    assert "今すぐ営業可能" in text
