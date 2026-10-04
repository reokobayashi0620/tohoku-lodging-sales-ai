"""Generate review-ready English social drafts. This never publishes."""
from __future__ import annotations
import csv, hashlib, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/"data"/"akiya_content_candidates.csv"
OUTPUT=ROOT/"output"/"social_drafts.md"
SITE="https://reokobayashi0620.github.io/tohoku-lodging-sales-ai"

def money(v):
    try:return f"¥{int(float(v)):,}"
    except:return v or "See source"
def slug(v): return re.sub(r"[^a-z0-9]+","-",str(v).lower()).strip("-") or "listing"
def listing_url(r):
    return f"{SITE}/properties/{slug(r.get('prefecture'))}-{slug(r.get('municipality'))}-{slug(r.get('listing_id'))}.html"
def score(r):
    s=0
    try:
        p=float(r.get("asking_price_jpy") or 0)
        if 0<p<=5_000_000:s+=4
        elif p<=10_000_000:s+=2
    except: pass
    if r.get("building_sqm"):s+=2
    if r.get("land_sqm"):s+=2
    if r.get("features"):s+=1
    return s
def make_post(r):
    facts=[f"📍 {r.get('municipality','')}, {r.get('prefecture','')}, Japan",f"💴 Listed price: {money(r.get('asking_price_jpy',''))}"]
    if r.get("building_sqm"):facts.append(f"🏠 Building: {r['building_sqm']} m²")
    if r.get("land_sqm"):facts.append(f"🌿 Land: {r['land_sqm']} m²")
    return "\n".join([f"AKIYA FIND — {r.get('prefecture','').upper()}, JAPAN 🇯🇵","",*facts,"","Explore the summary and send NexT DooR your preferred area and budget.",listing_url(r),"",f"Original public source: {r.get('source_url','')}","Information may change. Confirm availability and details with the original source.","","#Japan #Akiya #Tohoku #JapanProperty #CountrysideJapan"])
def main():
    rows=list(csv.DictReader(INPUT.open(encoding="utf-8"))) if INPUT.exists() else []
    approved=[r for r in rows if r.get("status")=="approved_for_draft"]
    # If nothing has been manually approved, prepare a small review queue only.
    # This is draft generation, not publication.
    selected=approved or sorted(rows,key=score,reverse=True)[:6]
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    blocks=["# NexT DooR social review queue","","> Drafts only — human approval is required before publishing.",""]
    for r in selected:
        base=make_post(r); url=listing_url(r)
        blocks += [f"## {r.get('listing_id')} — score {score(r)}","",base,"","### Pinterest",f"Title: Akiya in {r.get('municipality')}, {r.get('prefecture')}, Japan",f"Link: {url}",f"Description: Explore a public akiya summary in {r.get('municipality')}, {r.get('prefecture')}, Tohoku, Japan. Local field support is available through NexT DooR.","","---",""]
    OUTPUT.write_text("\n".join(blocks),encoding="utf-8")
    print(f"Generated {len(selected)} review draft(s); approved={len(approved)}")
if __name__=="__main__":main()
