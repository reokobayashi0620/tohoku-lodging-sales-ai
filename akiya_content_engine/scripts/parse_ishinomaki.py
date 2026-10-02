"""Discover public sale-house facts from Ishinomaki City's official Akiya Bank site.

Public facts only. No listing photos are downloaded or reused.
"""
from __future__ import annotations
import csv,re
from html import unescape
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data"/"discovered_listings_ishinomaki.csv"
URL="https://ishinomaki-c04202.akiya-athome.jp/buy/house/area/miyagiken/ishinomakishi/list?gyosei_cd%5B%5D=04202"
FIELDS=["source_id","source_url","prefecture","municipality","address","asking_price_jpy","property_type","building_sqm","land_sqm","features","retrieved_at"]

def clean(s):
 s=re.sub(r"<[^>]+>"," ",s); s=unescape(s).replace("\u3000"," ")
 return re.sub(r"\s+"," ",s).strip()

def main():
 req=Request(URL,headers={"User-Agent":"NexT-DooR-Akiya-Monitor/1.0"})
 html=urlopen(req,timeout=30).read().decode("utf-8","ignore")
 text=clean(html)
 # Split around property type labels used on the municipal AtHome page.
 chunks=re.split(r"中古売戸建住宅",text)[1:]
 rows=[]
 for x in chunks:
  pm=re.search(r"([0-9,]+)万円",x)
  am=re.search(r"(宮城県石巻市[^|]{1,80}?)(?: JR| ＪＲ| 駅| 築|価格)",x)
  area=re.search(r"([0-9,.]+)㎡\s*/\s*([0-9,.]+)㎡",x)
  if not(pm and am and area): continue
  land,building=area.group(1),area.group(2)
  rows.append({"source_id":"ishinomaki_bank","source_url":URL,"prefecture":"Miyagi",
   "municipality":"Ishinomaki","address":am.group(1).strip(),
   "asking_price_jpy":int(pm.group(1).replace(",",""))*10000,
   "property_type":"Residential / sale","building_sqm":building,"land_sqm":land,
   "features":"","retrieved_at":""})
 # Stable de-dupe on address+price.
 unique={(r["address"],r["asking_price_jpy"]):r for r in rows}
 OUT.parent.mkdir(parents=True,exist_ok=True)
 with OUT.open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(unique.values())
 print(f"Discovered {len(unique)} Ishinomaki sale listing(s): {OUT}")

if __name__=="__main__": main()
