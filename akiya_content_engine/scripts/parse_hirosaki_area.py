"""Discover public sale listings from the official Hirosaki Area Akiya Bank.

Reads the official HTML tables only. It does not download listing photos and does not
publish anything. Prices on the official table are displayed in units of 10,000 JPY.
"""
from __future__ import annotations
import csv, re
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data"/"discovered_listings_hirosaki.csv"
BASE="https://www.city.hirosaki.aomori.jp/akiyabank-8"
AREAS={
 "Hirosaki":"hirosaki","Kuroishi":"kuroishi","Hirakawa":"hirakawa","Fujisaki":"fujisaki",
 "Itayanagi":"itayanagi","Owanii":"oowani","Inakadate":"inakadate","Nishimeya":"nishimeya",
}
FIELDS=["source_id","source_url","prefecture","municipality","address","asking_price_jpy","property_type","building_sqm","land_sqm","features","retrieved_at"]

def clean(s):
 s=re.sub(r"<[^>]+>"," ",s); s=unescape(s).replace("\u3000"," ")
 return re.sub(r"\s+"," ",s).strip()

def fetch(url):
 req=Request(url,headers={"User-Agent":"NexT-DooR-Akiya-Monitor/1.0"})
 return urlopen(req,timeout=20).read().decode("utf-8","ignore")

def parse_rows(html, municipality, url):
 out=[]
 for tr in re.findall(r"<tr[^>]*>(.*?)</tr>",html,re.I|re.S):
  cells=[clean(x) for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>",tr,re.I|re.S)]
  if len(cells)<4: continue
  joined=" | ".join(cells)
  m_land=re.search(r"土地[：:]?\s*([0-9,.]+)",joined)
  m_build=re.search(r"建物[：:]?\s*([0-9,.]+)",joined)
  nums=re.findall(r"(?<![0-9.])([0-9][0-9,]*)\s*(?:万円)?",cells[3] if len(cells)>3 else "")
  if not (m_land or m_build) or not nums: continue
  price=int(nums[0].replace(",",""))*10000
  address=cells[1] if len(cells)>1 else ""
  out.append({"source_id":"hirosaki_area_bank","source_url":url,"prefecture":"Aomori",
   "municipality":municipality,"address":address,"asking_price_jpy":price,"property_type":"Residential / sale",
   "building_sqm":m_build.group(1).replace(",","") if m_build else "",
   "land_sqm":m_land.group(1).replace(",","") if m_land else "",
   "features":"","retrieved_at":""})
 return out

def main():
 rows=[]
 for municipality,slug in AREAS.items():
  url=f"{BASE}/{slug}/akiya.html"
  try: rows.extend(parse_rows(fetch(url),municipality,url))
  except Exception as e: print(f"WARN {municipality}: {e}")
 OUT.parent.mkdir(parents=True,exist_ok=True)
 with OUT.open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
 print(f"Discovered {len(rows)} Hirosaki-area sale listing(s): {OUT}")

if __name__=="__main__": main()
