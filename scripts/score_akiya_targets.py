#!/usr/bin/env python3
import csv
import sys

YES = {"yes", "y", "true", "1", "あり", "有"}

def yes(value):
    return (value or "").strip().lower() in YES

def score(row):
    total = 0
    if yes(row.get("foreign_support")): total += 3
    # Phase 1 CSV keeps the model intentionally small. A company entered here
    # is already assumed to handle akiya/local properties, so give +2.
    total += 2
    if yes(row.get("management")): total += 2
    if yes(row.get("renovation")): total += 1
    if yes(row.get("tohoku_support")): total += 1
    # Partner-network evidence is reviewed manually and can be reflected by
    # adding one point after review, capped at 10.
    return min(total, 10)

def main(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["score"] = str(score(row))
    rows.sort(key=lambda r: int(r["score"]), reverse=True)
    writer = csv.DictWriter(sys.stdout, fieldnames=rows[0].keys()) if rows else None
    if writer:
        writer.writeheader()
        writer.writerows(rows)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: score_akiya_targets.py <targets.csv>")
    main(sys.argv[1])
