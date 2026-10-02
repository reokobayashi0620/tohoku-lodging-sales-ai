"""Discover public sale-house facts from Nagai City's official Akiya Bank feed.

The city states that its current Akiya Bank is operated on AtHome. Facts only:
no listing images are downloaded or reused.
"""
from __future__ import annotations
import csv,re
from html import unescape
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data"/"discovered_listings_nagai.csv"
URL="https://nagai-c06209.akiya-athome.jp/buy/house/area/yamagataken/nagaishi/list?gyosei_cd%5B%5D=06209"
FIELDS=["source_id","source_url","prefecture","municipality","address","asking_price_jpy","property_type","building_sqm","land_sqm","features","retrieved_at"]

def clean(s):
 s=re.sub(r"<[^>]+>"," ",s); s=unescape(s).replace("\u3000"," ")
 return re.sub(r"\s+"," ",s).strip()

def main():
 req=Request(URL,headers={"User-Agent":"NexT-DooR-Akiya-Monitor/1.0"})
 html=urlopen(req,timeout=30).read().decode("utf-8","ignore")
 text=clean(html)
 chunks=re.split(r"中古売戸建住宅",text)[1:]
 rows=[]
 for x in chunks:
  pm=re.search(r"([0-9,]+)万円",x)
  am=re.search(r"(山形県長井市.{1,80}?)(?=\s*(?:JR|ＪＲ|駅|築|価格))",x)
  area=re.search(r"([0-9,.]+)㎡\s*/\s*([0-9,.]+)㎡",x)
  if not(pm and am and area): continue
  land,building=area.group(1),area.group(2)
  rows.append({"source_id":"nagai_bank","source_url":URL,"prefecture":"Yamagata",
   "municipality":"Nagai","address":am.group(1).strip(),
   "asking_price_jpy":int(pm.group(1).replace(",",""))*10000,
   "property_type":"Residential / sale","building_sqm":building,"land_sqm":land,
   "features":"","retrieved_at":""})
 unique={(r["address"],r["asking_price_jpy"]):r for r in rows}
 OUT.parent.mkdir(parents=True,exist_ok=True)
 with OUT.open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(unique.values())
 print(f"Discovered {len(unique)} Nagai sale listing(s): {OUT}")

if __name__=="__main__": main()
