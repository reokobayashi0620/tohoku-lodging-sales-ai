"""Discover public sale listing facts from Date City, Fukushima official Akiya Bank page.

Facts only. Does not open/download the linked photo or PDF files.
"""
from __future__ import annotations
import csv,re
from html import unescape
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data"/"discovered_listings_date_fukushima.csv"
URL="https://www.city.fukushima-date.lg.jp/soshiki/11/11412.html"
FIELDS=["source_id","source_url","prefecture","municipality","address","asking_price_jpy","property_type","building_sqm","land_sqm","features","retrieved_at"]

def clean(s):
 s=re.sub(r"<[^>]+>"," ",s); s=unescape(s).replace("\u3000"," ")
 return re.sub(r"\s+"," ",s).strip()

def main():
 html=urlopen(Request(URL,headers={"User-Agent":"NexT-DooR-Akiya-Monitor/1.0"}),timeout=30).read().decode("utf-8","ignore")
 rows=[]
 for tr in re.findall(r"<tr[^>]*>(.*?)</tr>",html,re.I|re.S):
  cells=[clean(x) for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>",tr,re.I|re.S)]
  if len(cells)<3: continue
  joined=" | ".join(cells)
  no=re.search(r"\b(\d{3})\b",joined)
  pm=re.search(r"売却\s*([0-9,]+)\s*万円",joined)
  if not(no and pm): continue
  # Address is normally the cell immediately after the 3-digit property number.
  idx=next((i for i,x in enumerate(cells) if re.fullmatch(r"0?\d{2,3}",x)),None)
  addr=cells[idx+1] if idx is not None and idx+1<len(cells) else ""
  if not addr: continue
  notes=[]
  if "要修繕" in joined: notes.append("Repair indicated")
  if "応相談" in joined: notes.append("Negotiable")
  notes.append("Property No. "+no.group(1))
  rows.append({"source_id":"date_fukushima_bank","source_url":URL,"prefecture":"Fukushima",
    "municipality":"Date","address":addr,"asking_price_jpy":int(pm.group(1).replace(",",""))*10000,
    "property_type":"Residential / sale","building_sqm":"","land_sqm":"",
    "features":"; ".join(notes),"retrieved_at":""})
 unique={(r["address"],r["asking_price_jpy"]):r for r in rows}
 OUT.parent.mkdir(parents=True,exist_ok=True)
 with OUT.open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(unique.values())
 print(f"Discovered {len(unique)} Date City sale listing(s): {OUT}")

if __name__=="__main__": main()
