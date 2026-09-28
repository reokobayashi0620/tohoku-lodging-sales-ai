"""Turn reviewed discovery rows into deduplicated social-content candidates.

Input: data/discovered_listings.csv
Output: data/akiya_content_candidates.csv

Discovery/parsing is intentionally source-specific. Rows must include the original
public source URL and should only contain factual fields supported by that source.
No images are copied here.
"""
from __future__ import annotations
import csv, hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DISCOVERED=ROOT/"data"/"discovered_listings.csv"
CANDIDATES=ROOT/"data"/"akiya_content_candidates.csv"

FIELDS=["listing_id","source_id","prefecture","municipality","property_type",
        "asking_price_jpy","building_sqm","land_sqm","features","source_url",
        "source_updated_at","retrieved_at","status"]

def stable_id(r:dict)->str:
    key="|".join([r.get("source_id",""),r.get("source_url",""),
                  r.get("municipality",""),r.get("asking_price_jpy","")])
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def main():
    if not DISCOVERED.exists():
        raise SystemExit(f"Missing {DISCOVERED}")
    rows=list(csv.DictReader(DISCOVERED.open(encoding="utf-8")))
    existing=[]
    if CANDIDATES.exists():
        existing=list(csv.DictReader(CANDIDATES.open(encoding="utf-8")))
    by_id={r.get("listing_id",""):r for r in existing if r.get("listing_id")}
    added=0
    for r in rows:
        lid=r.get("listing_id") or stable_id(r)
        if lid in by_id:
            continue
        out={k:r.get(k,"") for k in FIELDS}
        out["listing_id"]=lid
        out["status"]="needs_review"
        by_id[lid]=out
        added+=1
    CANDIDATES.parent.mkdir(parents=True,exist_ok=True)
    with CANDIDATES.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(by_id.values())
    print(f"discovered={len(rows)} added={added} total={len(by_id)}")

if __name__=="__main__": main()
