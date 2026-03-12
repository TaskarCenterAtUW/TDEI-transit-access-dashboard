#!/usr/bin/env python3
"""
Add transit_score (0-4) and transit_threshold to WA amenities.csv.

Transit score per tract = for each of the four services (peak_15min_weekday,
day_15min_weekday, night_60min_weekday, allday_60min_weekend), 1 if ANY stop
in that tract (census_tract_geoid) has YES for that service, else 0. Sum = 0-4.
Transit threshold = "high" if transit_score >= 3 else "low".

Uses WA Bus Routes.csv (one pass) then updates WA amenities.csv.
"""
import csv
import sys

BUS_ROUTES_PATH = "WA Bus Routes.csv"
AMENITIES_PATH = "WA amenities.csv"

SERVICE_COLS = [
    "peak_15min_weekday",
    "day_15min_weekday",
    "night_60min_weekday",
    "allday_60min_weekend",
]


def main():
    # One pass: for each tract, OR the four YES flags across all stops
    tract_has = {}  # geoid -> [bool]*4
    with open(BUS_ROUTES_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            geoid = (row.get("census_tract_geoid") or "").strip()
            if not geoid:
                continue
            if geoid not in tract_has:
                tract_has[geoid] = [False, False, False, False]
            for i, col in enumerate(SERVICE_COLS):
                if (row.get(col) or "").strip().upper() == "YES":
                    tract_has[geoid][i] = True

    # Compute score per tract (0-4)
    tract_score = {geoid: sum(flags) for geoid, flags in tract_has.items()}

    # Read amenities, add columns, write
    rows = []
    with open(AMENITIES_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        for row in reader:
            rows.append(row)

    fieldnames.extend(["transit_score", "transit_threshold"])
    default_score = 0
    for row in rows:
        geoid = (row.get("GEOID") or "").strip()
        score = tract_score.get(geoid, default_score)
        row["transit_score"] = str(score)
        row["transit_threshold"] = "high" if score >= 3 else "low"

    with open(AMENITIES_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    n_with_stops = len(tract_score)
    scores = list(tract_score.values()) or [0]
    print(f"Wrote {len(rows)} rows to {AMENITIES_PATH}")
    print(f"Tracts with at least one stop: {n_with_stops}")
    print(f"Transit score range: {min(scores)}–{max(scores)}")


if __name__ == "__main__":
    main()
