"""Discover public sale listings from Kazuno City's Akiya Bank (Kazuno Gurashi).

Facts only; no listing images are downloaded or reused.
"""
from __future__ import annotations
import csv,re
from html import unescape
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urljoin

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data"/"discovered_listings_kazuno.csv"
BASE="https://kazuno-gurashi.jp/akiya_bank"
FIELDS=["source_id","source_url","prefecture","municipality","address","asking_price_jpy","property_type","building_sqm","land_sqm","features","retrieved_at"]

def clean(s):
 s=re.sub(r"<[^>]+>"," ",s); s=unescape(s).replace("\u3000"," ")
 return re.sub(r"\s+"," ",s).strip()

def fetch(url):
 return urlopen(Request(url,headers={"User-Agent":"NexT-DooR-Akiya-Monitor/1.0"}),timeout=30).read().decode("utf-8","ignore")

def value(text,label):
 m=re.search(rf"{label}[^0-9]*([0-9,.]+)\s*㎡",text)
 return m.group(1).replace(",","") if m else ""

def main():
 listing_urls=set()
 # Follow paginated public index; stop when a page yields no new detail links.
 for page in range(1,15):
  url=BASE if page==1 else f"{BASE}/page/{page}"
  try: html=fetch(url)
  except Exception as e:
   print(f"WARN index {page}: {e}"); break
  found=set(re.findall(r'href=["\']([^"\']*akiya_bank/[^"\']+)["\']',html,re.I))
  before=len(listing_urls)
  for href in found:
   full=urljoin(url,href)
   if "/page/" not in full and full.rstrip("/")!=BASE: listing_urls.add(full)
  if len(listing_urls)==before and page>1: break

 rows=[]
 for url in sorted(listing_urls):
  try: text=clean(fetch(url))
  except Exception as e: print(f"WARN detail {url}: {e}"); continue
  no=re.search(r"(?:物件番号|管理No\.)[^0-9]*([0-9]+)",text)
  addr=re.search(r"(?:所在地)[^\u4e00-\u9fff]*(?:秋田県)?(鹿角市.{2,80}?)(?=\s*(?:建物面積|築年月|売買))",text)
  price=re.search(r"売買\s*([0-9,]+)\s*万円",text)
  if not(addr and price): continue
  features=[]
  layout=re.search(r"間取り\s*([^\s|]{1,12})",text)
  built=re.search(r"築年月\s*([0-9]{4}年(?:[0-9]{1,2}月)?)",text)
  if no: features.append("Property No. "+no.group(1))
  if layout: features.append("Layout "+layout.group(1))
  if built: features.append("Built "+built.group(1))
  rows.append({"source_id":"kazuno_bank","source_url":url,"prefecture":"Akita","municipality":"Kazuno",
   "address":addr.group(1).strip(),"asking_price_jpy":int(price.group(1).replace(",",""))*10000,
   "property_type":"Residential / sale","building_sqm":value(text,"建物面積"),
   "land_sqm":value(text,"土地面積"),"features":"; ".join(features),"retrieved_at":""})
 unique={(r["source_url"],r["asking_price_jpy"]):r for r in rows}
 OUT.parent.mkdir(parents=True,exist_ok=True)
 with OUT.open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(unique.values())
 print(f"Discovered {len(unique)} Kazuno sale listing(s): {OUT}")

if __name__=="__main__": main()
