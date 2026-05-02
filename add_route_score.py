#!/usr/bin/env python3
"""
Add a route_score column to WA Bus Routes.csv.
Score = 0-4: for each route (agency + route_path_id), count how many of these
four services have at least one YES among its stops:
  peak_15min_weekday, day_15min_weekday, night_60min_weekday, allday_60min_weekend
Every stop on that route gets the same route_score.
Output: WA Bus Routes with score.csv (or overwrite with --in-place)
"""
import csv
import sys
from collections import defaultdict

SERVICE_COLS = [
    "peak_15min_weekday",
    "day_15min_weekday",
    "night_60min_weekday",
    "allday_60min_weekend",
]

INPUT_PATH = "WA Bus Routes.csv"
OUTPUT_PATH = "WA Bus Routes with score.csv"

SCORE_LABELS = {4: "Great", 3: "Good", 2: "Acceptable", 1: "Ok", 0: "Poor"}


def main():
    in_path = INPUT_PATH
    out_path = OUTPUT_PATH
    if "--in-place" in sys.argv:
        out_path = in_path

    # Read all rows and group by (agency, route_path_id)
    rows = []
    route_has_service = defaultdict(lambda: {col: False for col in SERVICE_COLS})

    with open(in_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        for row in reader:
            rows.append(row)
            key = (row.get("agency", "").strip(), row.get("route_path_id", "").strip())
            for col in SERVICE_COLS:
                if (row.get(col) or "").strip().upper() == "YES":
                    route_has_service[key][col] = True

    # Compute score per route (0-4)
    route_score = {}
    for key, services in route_has_service.items():
        route_score[key] = sum(1 for col in SERVICE_COLS if services[col])

    # Add route_score column
    if "route_score" not in fieldnames:
        fieldnames.append("route_score")
    for row in rows:
        key = (row.get("agency", "").strip(), row.get("route_path_id", "").strip())
        row["route_score"] = SCORE_LABELS.get(route_score.get(key, 0), str(route_score.get(key, 0)))

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_path}")
    print(f"Route scores: min={min(route_score.values())}, max={max(route_score.values())}")


if __name__ == "__main__":
    main()
