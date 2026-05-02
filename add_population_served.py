#!/usr/bin/env python3
"""
Add to WA Bus Routes with score.csv:
- population_served: sum of TOTAL_POPU over all unique census tracts along the route (agency+route_path_id)
- population_served_low_wheelchair_essentials: same sum but only for tracts with wheelchair_essentials_threshold == "low"
- pct_served_low_essentials: percentage of population_served that is low wheelchair essentials, rounded to nearest percent (0-100)

Uses WA amenities.csv for population and wheelchair_essentials_threshold.
"""
import csv
from collections import defaultdict

AMENITIES_PATH = "WA amenities.csv"
ROUTES_PATH = "WA Bus Routes with score.csv"

POP_COL = "population_served"
LOW_ESS_COL = "population_served_low_wheelchair_essentials"
PCT_COL = "pct_served_low_essentials"


def safe_float(val):
    if val is None or val == "":
        return 0.0
    try:
        return float(val)
    except ValueError:
        return 0.0


def main():
    # Load amenities: geoid -> {pop, wheelchair_essentials_threshold}
    tract_info = {}
    with open(AMENITIES_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            geoid = (row.get("GEOID") or "").strip()
            if not geoid:
                continue
            pop = safe_float(row.get("TOTAL_POPU"))
            wheel_low = (row.get("wheelchair_essentials_threshold") or "").strip().lower() == "low"
            tract_info[geoid] = {"pop": pop, "wheel_low": wheel_low}

    # One pass over routes: (agency, route_path_id) -> set of census_tract_geoid
    route_tracts = defaultdict(set)
    rows = []
    with open(ROUTES_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        for row in reader:
            rows.append(row)
            agency = (row.get("agency") or "").strip()
            path_id = (row.get("route_path_id") or "").strip()
            geoid = (row.get("census_tract_geoid") or "").strip()
            if path_id and geoid:
                route_tracts[(agency, path_id)].add(geoid)

    # Per route: total pop and pop with low wheelchair essentials
    route_total_pop = {}
    route_low_ess_pop = {}
    for (agency, path_id), geoids in route_tracts.items():
        total = 0.0
        low_ess = 0.0
        for g in geoids:
            info = tract_info.get(g, {"pop": 0.0, "wheel_low": False})
            total += info["pop"]
            if info["wheel_low"]:
                low_ess += info["pop"]
        route_total_pop[(agency, path_id)] = total
        route_low_ess_pop[(agency, path_id)] = low_ess

    # Add columns to every row
    for col in (POP_COL, LOW_ESS_COL, PCT_COL):
        if col not in fieldnames:
            fieldnames.append(col)
    for row in rows:
        key = ((row.get("agency") or "").strip(), (row.get("route_path_id") or "").strip())
        total = route_total_pop.get(key, 0)
        low_ess = route_low_ess_pop.get(key, 0)
        row[POP_COL] = str(int(total))
        row[LOW_ESS_COL] = str(int(low_ess))
        pct = round(low_ess / total * 100) if total > 0 else 0
        row[PCT_COL] = str(pct)

    with open(ROUTES_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {ROUTES_PATH}")
    print(f"Added columns: {POP_COL}, {LOW_ESS_COL}, {PCT_COL}")
    total_all = sum(route_total_pop.values())
    low_all = sum(route_low_ess_pop.values())
    print(f"Sample: total population across routes (sum of unique tract pops): {total_all:.0f}; low wheelchair essentials portion: {low_all:.0f}")


if __name__ == "__main__":
    main()
