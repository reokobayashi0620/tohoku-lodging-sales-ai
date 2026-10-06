"""Discover public sale listing facts from Tendo City's official Akiya Bank page."""
from __future__ import annotations
import csv,re,urllib.request
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
URL="https://www.city.tendo.yamagata.jp/lifeinfo/sumai/akiyabanku_tourokuakiya.html"
OUT=ROOT/"data"/"discovered_listings_tendo.csv"
UA="NexT-DooR-Akiya-Monitor/1.0"
FIELDS=["listing_id","source_id","prefecture","municipality","property_type","asking_price_jpy","building_sqm","land_sqm","features","source_url","source_updated_at","retrieved_at"]

class Text(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]
    def handle_data(self,d):
        d=" ".join(d.split())
        if d:self.parts.append(d)

def main():
    req=urllib.request.Request(URL,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=30) as r:
        raw=r.read().decode("utf-8","ignore")
    p=Text(); p.feed(raw); text="\n".join(p.parts)
    now=datetime.now(timezone.utc).isoformat()
    rows=[]
    chunks=re.split(r"(?=登録第\s*\d+\s*号)",text)
    for chunk in chunks:
        no=re.search(r"登録第\s*(\d+)\s*号",chunk)
        price=re.search(r"売却希望価格\s*([0-9,]+)\s*万円",chunk)
        if not(no and price): continue
        land=re.search(r"敷地面積\s*([0-9.]+)\s*平方メートル",chunk)
        heading=""
        first=chunk.splitlines()[0] if chunk.splitlines() else ""
        hm=re.search(r"登録第\s*\d+\s*号\s*(.*?)(?:【|〖|\[|$)",first)
        if hm: heading=hm.group(1).strip()
        rows.append({
            "listing_id":no.group(1),"source_id":"tendo_bank","prefecture":"Yamagata",
            "municipality":"Tendo","property_type":"Residential / for sale",
            "asking_price_jpy":str(int(price.group(1).replace(",",""))*10000),
            "building_sqm":"","land_sqm":land.group(1) if land else "",
            "features":"; ".join(x for x in [f"Property No. {no.group(1)}", heading] if x),
            "source_url":URL,"source_updated_at":"","retrieved_at":now
        })
    unique={r["listing_id"]:r for r in rows}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(unique.values())
    print(f"Discovered {len(unique)} Tendo sale listing(s): {OUT}")
    if not unique:
        raise SystemExit("No Tendo sale listings parsed from official page")

if __name__=="__main__": main()
