import ipaddress
import json
import re
import socket
import sqlite3
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from flask import flash, redirect, render_template, request

PREFECTURES = ["宮城県", "山形県", "岩手県", "福島県", "秋田県", "青森県"]
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SOURCE_TYPE = "OpenStreetMap 公開POI"
USER_AGENT = "TohokuLodgingSalesAI/1.0 (public-source research)"
CORPORATE_WORDS = ("株式会社", "合同会社", "有限会社", "一般社団法人", "一般財団法人", "LLC", "Inc.", "Co., Ltd")
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _clean(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def _first(tags, *keys):
    for key in keys:
        value = _clean(tags.get(key, ""))
        if value:
            return value
    return ""


def _build_address(tags, lat=None, lon=None):
    full = _first(tags, "addr:full")
    if full:
        return full
    parts = []
    for key in ("addr:province", "addr:city", "addr:town", "addr:village", "addr:suburb", "addr:quarter", "addr:neighbourhood", "addr:street", "addr:housenumber"):
        value = _clean(tags.get(key, ""))
        if value and value not in parts:
            parts.append(value)
    if parts:
        return " ".join(parts)
    if lat is not None and lon is not None:
        return f"所在地未確認（OSM座標 {float(lat):.5f},{float(lon):.5f}）"
    return "所在地未確認（OpenStreetMap）"


def _extract_city(tags):
    return _first(tags, "addr:city", "addr:town", "addr:village", "addr:suburb")


def _is_yes(value):
    return str(value or "").lower() in {"yes", "true", "1", "designated", "permissive"}


def parse_overpass(payload, prefecture):
    records = []
    seen = set()
    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        name = _first(tags, "name:ja", "name")
        if not name:
            continue
        osm_type = element.get("type", "node")
        osm_id = element.get("id")
        if not osm_id:
            continue
        key = f"osm|{osm_type}|{osm_id}"
        if key in seen:
            continue
        seen.add(key)
        center = element.get("center") or {}
        lat = element.get("lat", center.get("lat"))
        lon = element.get("lon", center.get("lon"))
        website = _first(tags, "contact:website", "website", "url")
        phone = _first(tags, "contact:phone", "phone", "mobile")
        email = _first(tags, "contact:email", "email")
        tourism = _clean(tags.get("tourism", ""))
        text = " ".join(str(v) for v in tags.values())
        pet = any(_is_yes(tags.get(k)) for k in ("dog", "dogs", "pets", "pet")) or bool(re.search(r"ペット可|ペット同伴|犬同伴", text))
        whole_house = tourism in {"chalet", "apartment"} or bool(re.search(r"一棟貸し|貸別荘|ヴィラ|villa|コテージ", name, re.I))
        records.append({
            "name": name,
            "prefecture": prefecture,
            "city": _extract_city(tags),
            "address": _build_address(tags, lat, lon),
            "official_url": website,
            "phone": phone,
            "email": email,
            "contact_url": "",
            "pet_friendly": int(pet),
            "whole_house": int(whole_house),
            "multiple_facilities": 0,
            "wood_floor": 0,
            "source_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
            "source_type": SOURCE_TYPE,
            "normalized_key": key,
            "research_status": "researching" if any((website, phone, email, pet, whole_house)) else "unresearched",
            "research_notes": f"[自動発掘] OpenStreetMapの公開POIから取得。tourism={tourism or '未設定'}。住所・属性は営業前に公式情報で確認。",
        })
    return records


def fetch_osm_records(prefecture):
    if prefecture not in PREFECTURES:
        raise ValueError("対象県が不正です。")
    query = f'''[out:json][timeout:35];
area["boundary"="administrative"]["name"="{prefecture}"]->.searchArea;
(
  nwr["tourism"~"^(hotel|guest_house|hostel|motel|chalet|apartment)$"](area.searchArea);
);
out center tags;'''
    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        timeout=50,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    return parse_overpass(payload, prefecture)


def import_records(database, records):
    inserted = skipped = 0
    con = sqlite3.connect(database)
    try:
        for item in records[:1000]:
            existing = con.execute("SELECT id FROM lead_candidates WHERE normalized_key=?", (item["normalized_key"],)).fetchone()
            if not existing and item.get("official_url"):
                existing = con.execute(
                    "SELECT id FROM lead_candidates WHERE official_url=? AND official_url<>'' LIMIT 1",
                    (item["official_url"],),
                ).fetchone()
            if existing:
                skipped += 1
                continue
            con.execute(
                """INSERT INTO lead_candidates
                (name,company_name,prefecture,city,address,official_url,phone,email,contact_url,
                 pet_friendly,whole_house,multiple_facilities,wood_floor,research_status,research_notes,
                 source_url,source_type,normalized_key,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending')""",
                (item["name"], "", item["prefecture"], item["city"], item["address"], item["official_url"],
                 item["phone"], item["email"], item["contact_url"], item["pet_friendly"], item["whole_house"],
                 item["multiple_facilities"], item["wood_floor"], item["research_status"], item["research_notes"],
                 item["source_url"], item["source_type"], item["normalized_key"]),
            )
            inserted += 1
        con.commit()
    finally:
        con.close()
    return inserted, skipped


def _hostname_is_public(hostname):
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return False
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return bool(infos)


def _safe_url(url):
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password and _hostname_is_public(parsed.hostname)


def _safe_get(url, max_redirects=3):
    current = url
    for _ in range(max_redirects + 1):
        if not _safe_url(current):
            raise ValueError("安全でないURLです。")
        response = requests.get(
            current,
            timeout=12,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            allow_redirects=False,
            stream=True,
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location", "")
            current = urljoin(current, location)
            continue
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            raise ValueError("HTMLではありません。")
        data = bytearray()
        for chunk in response.iter_content(64 * 1024):
            if chunk:
                data.extend(chunk)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise ValueError("ページサイズ上限を超えました。")
        response._content = bytes(data)
        return response, current
    raise ValueError("リダイレクトが多すぎます。")


def _robots_allowed(url):
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    if not _safe_url(robots_url):
        return False
    try:
        response = requests.get(robots_url, timeout=8, headers={"User-Agent": USER_AGENT}, allow_redirects=False)
        if response.status_code == 404:
            return True
        if response.status_code != 200:
            return False
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.parse(response.text.splitlines())
        return rp.can_fetch(USER_AGENT, url)
    except requests.RequestException:
        return False


def extract_official_site(html, base_url, facility_name=""):
    soup = BeautifulSoup(html, "html.parser")
    result = {"company_name": "", "phone": "", "email": "", "contact_url": "", "pet_friendly": 0, "whole_house": 0, "wood_floor": 0, "notes": []}
    for tag in soup.select('a[href^="mailto:"]'):
        value = tag.get("href", "")[7:].split("?")[0].strip()
        if value:
            result["email"] = value
            break
    for tag in soup.select('a[href^="tel:"]'):
        value = tag.get("href", "")[4:].strip()
        if value:
            result["phone"] = value
            break
    for tag in soup.find_all("a", href=True):
        href = tag.get("href", "")
        label = _clean(tag.get_text(" "))
        if re.search(r"contact|inquiry|お問い合わせ|お問合せ|問い合わせ|問合せ", href + " " + label, re.I):
            result["contact_url"] = urljoin(base_url, href)
            break
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (TypeError, json.JSONDecodeError):
            continue
        queue = data if isinstance(data, list) else [data]
        for obj in queue:
            if not isinstance(obj, dict):
                continue
            for key in ("parentOrganization", "provider", "brand"):
                org = obj.get(key)
                if isinstance(org, dict):
                    name = _clean(org.get("name", ""))
                    if name and name != facility_name and any(word in name for word in CORPORATE_WORDS):
                        result["company_name"] = name
                        break
            if result["company_name"]:
                break
        if result["company_name"]:
            break
    text = _clean(soup.get_text(" "))[:200000]
    if re.search(r"ペット可|ペット同伴|愛犬同伴|犬と泊ま", text):
        result["pet_friendly"] = 1
        result["notes"].append("ペット同伴表現")
    if re.search(r"一棟貸し|一棟貸切|貸別荘|プライベートヴィラ|private villa", text, re.I):
        result["whole_house"] = 1
        result["notes"].append("一棟貸し表現")
    if re.search(r"無垢床|フローリング|木の床|木質床", text):
        result["wood_floor"] = 1
        result["notes"].append("木質床表現")
    return result


def enrich_candidate(database, candidate):
    url = candidate["official_url"]
    if not url or not _safe_url(url) or not _robots_allowed(url):
        return False, "robots.txtまたはURL安全性の条件により自動調査をスキップ"
    response, final_url = _safe_get(url)
    extracted = extract_official_site(response.text, final_url, candidate["name"] or "")
    changes = {}
    for field in ("company_name", "phone", "email", "contact_url"):
        if not candidate[field] and extracted[field]:
            changes[field] = extracted[field]
    for field in ("pet_friendly", "whole_house", "wood_floor"):
        if not candidate[field] and extracted[field]:
            changes[field] = 1
    note_bits = extracted["notes"]
    note = f"[公式サイト自動調査] {final_url}"
    if note_bits:
        note += " / 検出: " + "、".join(note_bits)
    changes["research_notes"] = ((candidate["research_notes"] or "") + "\n" + note).strip()
    changes["research_status"] = "researching"
    if not changes:
        return False, "追加情報なし"
    sets = ", ".join(f"{key}=?" for key in changes)
    values = list(changes.values()) + [candidate["id"]]
    con = sqlite3.connect(database)
    try:
        con.execute(f"UPDATE lead_candidates SET {sets}, updated_at=CURRENT_TIMESTAMP WHERE id=?", values)
        con.commit()
    finally:
        con.close()
    return True, "更新"


def enrich_batch(database, limit=10):
    con = sqlite3.connect(database)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """SELECT * FROM lead_candidates
               WHERE status='pending' AND source_type=? AND official_url<>'' AND research_status<>'verified'
               ORDER BY CASE research_status WHEN 'unresearched' THEN 0 ELSE 1 END, id
               LIMIT ?""",
            (SOURCE_TYPE, limit),
        ).fetchall()
    finally:
        con.close()
    updated = skipped = failed = 0
    for row in rows:
        try:
            changed, _ = enrich_candidate(database, row)
            if changed:
                updated += 1
            else:
                skipped += 1
        except (requests.RequestException, ValueError, OSError):
            failed += 1
    return {"checked": len(rows), "updated": updated, "skipped": skipped, "failed": failed}


def register_auto_discovery(app):
    @app.get("/auto-discovery")
    def auto_discovery():
        con = sqlite3.connect(app.config["DATABASE"])
        try:
            total = con.execute("SELECT COUNT(*) FROM lead_candidates WHERE source_type=?", (SOURCE_TYPE,)).fetchone()[0]
            researchable = con.execute("SELECT COUNT(*) FROM lead_candidates WHERE source_type=? AND status='pending' AND official_url<>''", (SOURCE_TYPE,)).fetchone()[0]
        finally:
            con.close()
        return render_template("auto_discovery.html", prefectures=PREFECTURES, total=total, researchable=researchable)

    @app.post("/auto-discovery/discover")
    def auto_discovery_run():
        prefecture = request.form.get("prefecture", "").strip()
        try:
            records = fetch_osm_records(prefecture)
            inserted, skipped = import_records(app.config["DATABASE"], records)
            flash(f"{prefecture}: {len(records)}件を発見し、新規{inserted}件を候補へ追加しました（重複{skipped}件）。", "success")
        except (requests.RequestException, ValueError, json.JSONDecodeError):
            flash("公開データからの自動発掘に失敗しました。時間を置いて再度お試しください。", "error")
        return redirect("/auto-discovery")

    @app.post("/auto-discovery/enrich")
    def auto_discovery_enrich():
        stats = enrich_batch(app.config["DATABASE"], limit=10)
        flash(
            f"公式サイト自動調査: {stats['checked']}件確認 / {stats['updated']}件更新 / {stats['skipped']}件スキップ / {stats['failed']}件失敗。",
            "success" if stats["updated"] else "info",
        )
        return redirect("/auto-discovery")

    return app
