"""Discover public sale listing facts from Kurihara City's official migration/akiya page."""
from __future__ import annotations
import csv,re,urllib.request
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
URL="https://www.kuriharacity.jp/welcome/"
OUT=ROOT/"data"/"discovered_listings_kurihara.csv"
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
    chunks=re.split(r"(?=物件番号\s*0*\d+)",text)
    for chunk in chunks:
        no=re.search(r"物件番号\s*0*(\d+)",chunk)
        price=re.search(r"売却希望価格\s*[：:]?\s*([0-9,]+)\s*万円",chunk)
        if not(no and price): continue
        loc=re.search(r"所在地\s*[：:]?\s*(?:宮城県)?栗原市([^\n]+)",chunk)
        title=""
        for line in chunk.splitlines()[1:6]:
            line=line.strip("「」『』 ")
            if line and not line.startswith(("所在地","売却希望価格","賃貸希望価格")):
                title=line; break
        rows.append({
            "listing_id":no.group(1),"source_id":"kurihara_bank","prefecture":"Miyagi",
            "municipality":"Kurihara","property_type":"Residential / for sale",
            "asking_price_jpy":str(int(price.group(1).replace(",",""))*10000),
            "building_sqm":"","land_sqm":"",
            "features":("; ".join(x for x in [f"Property No. {no.group(1)}", title, ("Area: "+loc.group(1).strip()) if loc else ""] if x)),
            "source_url":URL,"source_updated_at":"","retrieved_at":now
        })
    unique={r["listing_id"]:r for r in rows}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(unique.values())
    print(f"Discovered {len(unique)} Kurihara sale listing(s): {OUT}")
    if not unique:
        raise SystemExit("No Kurihara sale listings parsed from official page")

if __name__=="__main__": main()
