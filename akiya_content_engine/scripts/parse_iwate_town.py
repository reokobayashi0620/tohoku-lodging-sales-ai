"""Iwate Town Akiya Bank parser (public sale listings only).

Fetches the official listing index and extracts conservative factual fields.
Does not download/reuse listing images and does not publish anything.
"""
from __future__ import annotations
import csv,re,urllib.request
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
URL="https://town.iwate.iwate.jp/akiya/akiyabank/"
OUT=ROOT/"data"/"discovered_listings.csv"
UA="NexT-DooR-Akiya-Monitor/1.0"

class Text(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]
    def handle_data(self,d):
        d=" ".join(d.split())
        if d:self.parts.append(d)

def fetch()->str:
    req=urllib.request.Request(URL,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=20) as r:
        return r.read().decode("utf-8","ignore")

def yen(s:str)->str:
    m=re.search(r"(\d+(?:\.\d+)?)万円",s)
    return str(int(float(m.group(1))*10000)) if m else ""

def main():
    html=fetch(); p=Text(); p.feed(html); text="\n".join(p.parts)
    # Official cards expose title, price, address and last-update text.
    pat=re.compile(r"売買物件\n(?P<title>[^\n]+)\n価格\n(?P<price>[^\n]+)\n所在地\n(?P<addr>[^\n]+).*?最終更新日[:：]\s*(?P<date>\d{4}年\d{1,2}月\d{1,2}日)",re.S)
    now=datetime.now(timezone.utc).isoformat()
    rows=[]
    for m in pat.finditer(text):
        g=m.groupdict()
        rows.append({
          "listing_id":"","source_id":"iwate_town","prefecture":"Iwate",
          "municipality":"Iwate Town","property_type":"Residential / for sale",
          "asking_price_jpy":yen(g["price"]),"building_sqm":"","land_sqm":"",
          "features":g["title"],"source_url":URL,
          "source_updated_at":g["date"],"retrieved_at":now
        })
    fields=["listing_id","source_id","prefecture","municipality","property_type","asking_price_jpy","building_sqm","land_sqm","features","source_url","source_updated_at","retrieved_at"]
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    print(f"iwate_town listings={len(rows)} -> {OUT}")
if __name__=="__main__":main()
