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
    _insert(db, "蔵王ペット貸別荘", "宮城県 民泊届出一覧", "https://www.pref.miyagi.jp/example", "official-1", pet_friendly=1, whole_house=1, wood_floor=1)
    _insert(db, "一般ホテル", "OpenStreetMap 公開POI", "https://openstreetmap.org/1", "osm-1")
    rows = find_targets(db, prefecture="宮城県")
    assert len(rows) == 1
    assert rows[0]["candidate"]["name"] == "蔵王ペット貸別荘"
    assert rows[0]["target_band"] == "S"


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
