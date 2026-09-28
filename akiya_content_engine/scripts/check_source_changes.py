"""Check configured public akiya source pages for changes.

Safety-first MVP: this stores page fingerprints and reports changed sources.
It does not copy listing photos, publish posts, or bypass site restrictions.
Municipal parsers can be added per source after terms/access are verified.
"""
from __future__ import annotations
import csv, hashlib, json, urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
SOURCES=ROOT/"data"/"sources.csv"
STATE=ROOT/"data"/"source_state.json"
REPORT=ROOT/"output"/"source_changes.md"
UA="NexT-DooR-Akiya-Monitor/1.0 (+public-source-change-check)"

def fetch(url:str)->bytes:
    req=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=20) as r:
        return r.read()

def main():
    rows=list(csv.DictReader(SOURCES.open(encoding="utf-8")))
    old=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    new=dict(old); changed=[]; errors=[]
    for r in rows:
        if r.get("enabled","").lower()!="true": continue
        try:
            body=fetch(r["source_url"])
            digest=hashlib.sha256(body).hexdigest()
            prev=old.get(r["source_id"],{}).get("sha256")
            if prev and prev!=digest: changed.append(r)
            new[r["source_id"]]={"sha256":digest,"checked_at":datetime.now(timezone.utc).isoformat(),"url":r["source_url"]}
        except Exception as e:
            errors.append((r,str(e)))
    STATE.write_text(json.dumps(new,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    lines=["# Akiya source change report","",f"Changed sources: {len(changed)}",""]
    for r in changed: lines += [f"- {r['prefecture']} / {r['municipality']} — {r['source_name']}",f"  - {r['source_url']}"]
    if errors:
        lines += ["","## Errors",""]
        for r,e in errors: lines.append(f"- {r['source_id']}: {e}")
    REPORT.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(f"checked={len(rows)} changed={len(changed)} errors={len(errors)}")

if __name__=="__main__": main()
