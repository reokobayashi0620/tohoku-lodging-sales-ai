"""Generate approval-ready English social drafts from reviewed candidate CSV rows.

This script does NOT scrape websites and does NOT publish to Meta.
Only rows with status=approved_for_draft are processed.
"""
from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "akiya_content_candidates.csv"
OUTPUT = ROOT / "output" / "social_drafts.md"

def money(v: str) -> str:
    try:
        return f"¥{int(float(v)):,}"
    except (ValueError, TypeError):
        return v or "See source"

def make_post(r: dict) -> str:
    features = [x.strip() for x in (r.get("features") or "").split(";") if x.strip()]
    facts = [
        f"📍 {r.get('municipality','')}, {r.get('prefecture','')}, Japan",
        f"💴 Asking price: {money(r.get('asking_price_jpy',''))}",
    ]
    if r.get("property_type"): facts.append(f"🏠 {r['property_type']}")
    if r.get("building_sqm"): facts.append(f"Building: {r['building_sqm']} m²")
    if r.get("land_sqm"): facts.append(f"Land: {r['land_sqm']} m²")
    if features: facts.append("Highlights: " + ", ".join(features[:4]))
    return "\n".join([
        f"AKIYA FIND — {r.get('prefecture','').upper()}, JAPAN 🇯🇵",
        "",
        *facts,
        "",
        "Looking for a home in Tohoku? Tell NexT DooR your preferred area and budget.",
        "https://next-door-akiya.netlify.app/",
        "",
        f"Original listing: {r.get('source_url','')}",
        "Listing information may change. Confirm current availability and details with the original source.",
        "",
        "#Japan #Akiya #Tohoku #JapanProperty #CountrysideJapan"
    ])

def main():
    if not INPUT.exists():
        raise SystemExit(f"Create {INPUT} from the example CSV and review each row first.")
    rows=list(csv.DictReader(INPUT.open(encoding="utf-8")))
    approved=[r for r in rows if r.get("status")=="approved_for_draft"]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    blocks=[]
    for r in approved:
        blocks += [f"## {r.get('listing_id') or 'Listing'}", "", make_post(r), "", "---", ""]
    OUTPUT.write_text("\n".join(blocks) if blocks else "# No approved drafts\n", encoding="utf-8")
    print(f"Generated {len(approved)} draft(s): {OUTPUT}")

if __name__ == "__main__":
    main()
