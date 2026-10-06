"""Merge all available municipal discovery feeds without letting one blocked source stop the pipeline."""
from pathlib import Path
import csv

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
OUTPUT=DATA/"discovered_listings.csv"
FILES=[
 "discovered_listings_iwate.csv","discovered_listings_hirosaki.csv",
 "discovered_listings_kurihara.csv","discovered_listings_kazuno.csv",
 "discovered_listings_tendo.csv","discovered_listings_date_fukushima.csv",
]
# The Iwate parser historically writes discovered_listings.csv; preserve it before overwrite.
inputs=[]
for name in FILES:
 p=DATA/name
 if p.exists(): inputs.append(p)
legacy=DATA/"discovered_listings.csv"
if legacy.exists(): inputs.insert(0,legacy)
rows=[]; fields=[]
seen=set()
for p in inputs:
 with p.open(encoding="utf-8") as fh:
  reader=csv.DictReader(fh)
  if not fields: fields=reader.fieldnames or []
  for row in reader:
   key=(row.get("source_url",""),row.get("listing_id",""),row.get("municipality",""),row.get("asking_price_jpy",""))
   if key in seen: continue
   seen.add(key); rows.append(row)
if not fields:
 raise SystemExit("No discovery feed was produced by any source")
with OUTPUT.open("w",newline="",encoding="utf-8") as fh:
 w=csv.DictWriter(fh,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)
print(f"Merged {len(rows)} unique listings from {len(inputs)} available feeds")
