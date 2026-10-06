"""Run one discovery parser safely, remove stale output first, and publish source health."""
from __future__ import annotations
from pathlib import Path
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "output"
HEALTH = OUT / "source_health.json"
HEALTH_MD = OUT / "source_health.md"

SOURCES = {
    "iwate": {
        "label": "Iwate / Iwate Town",
        "script": "parse_iwate_town.py",
        "output": DATA / "discovered_listings.csv",
    },
    "aomori": {
        "label": "Aomori / Hirosaki Area",
        "script": "parse_hirosaki_area.py",
        "output": DATA / "discovered_listings_hirosaki.csv",
    },
    "miyagi": {
        "label": "Miyagi / Ishinomaki",
        "script": "parse_ishinomaki.py",
        "output": DATA / "discovered_listings_ishinomaki.csv",
    },
    "akita": {
        "label": "Akita / Kazuno",
        "script": "parse_kazuno.py",
        "output": DATA / "discovered_listings_kazuno.csv",
    },
    "yamagata": {
        "label": "Yamagata / Nagai",
        "script": "parse_nagai.py",
        "output": DATA / "discovered_listings_nagai.csv",
    },
    "fukushima": {
        "label": "Fukushima / Date City",
        "script": "parse_date_fukushima.py",
        "output": DATA / "discovered_listings_date_fukushima.csv",
    },
}

def load_health():
    if HEALTH.exists():
        try:
            return json.loads(HEALTH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def row_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as fh:
        return sum(1 for _ in csv.DictReader(fh))

def save_health(data):
    OUT.mkdir(exist_ok=True)
    HEALTH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Akiya source health",
        "",
        "Generated automatically. A failed source is visible here and is not silently treated as current data.",
        "",
        "| Source | Status | Listings | Checked (UTC) | Detail |",
        "|---|---|---:|---|---|",
    ]
    for key in SOURCES:
        item = data.get(key, {})
        detail = str(item.get("detail", "")).replace("|", "/").replace("\n", " ")[:180]
        lines.append(
            f"| {SOURCES[key]['label']} | {item.get('status','not_checked')} | "
            f"{item.get('listings',0)} | {item.get('checked_at','')} | {detail} |"
        )
    HEALTH_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

def main():
    if len(sys.argv) != 2 or sys.argv[1] not in SOURCES:
        raise SystemExit("Usage: run_source.py " + "|".join(SOURCES))
    key = sys.argv[1]
    cfg = SOURCES[key]
    output = cfg["output"]
    # Never merge a stale checked-in feed after today's source failed.
    if output.exists():
        output.unlink()
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).with_name(cfg["script"]))],
        text=True,
        capture_output=True,
        timeout=180,
    )
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")
    count = row_count(output)
    ok = proc.returncode == 0 and output.exists()
    detail = "ok"
    if not ok:
        tail = (proc.stderr or proc.stdout or f"exit code {proc.returncode}").strip().splitlines()
        detail = tail[-1] if tail else f"exit code {proc.returncode}"
        if output.exists():
            output.unlink()
        count = 0
    data = load_health()
    data[key] = {
        "label": cfg["label"],
        "status": "ok" if ok else "failed",
        "listings": count,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "detail": detail,
    }
    save_health(data)
    print(f"SOURCE_HEALTH {key}: {data[key]['status']} listings={count} detail={detail}")
    # Source failure is recorded but does not stop the resilient multi-source pipeline.
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
