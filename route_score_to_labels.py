#!/usr/bin/env python3
"""Replace route_score 4,3,2,1,0 with Great, Good, Acceptable, Ok, Poor in WA Bus Routes with score.csv."""
import csv

ROUTES_PATH = "WA Bus Routes with score.csv"
SCORE_LABELS = {"4": "Great", "3": "Good", "2": "Acceptable", "1": "Ok", "0": "Poor"}


def main():
    rows = []
    with open(ROUTES_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        for row in reader:
            rows.append(row)
    for row in rows:
        val = (row.get("route_score") or "").strip()
        row["route_score"] = SCORE_LABELS.get(val, val)
    with open(ROUTES_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Updated route_score to Great/Good/Acceptable/Ok/Poor in {ROUTES_PATH}")


if __name__ == "__main__":
    main()
