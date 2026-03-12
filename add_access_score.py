#!/usr/bin/env python3
"""
Add pedestrian_access_score and wheelchair_access_score (HH, HL, LH, LL) to WA amenities.csv:
  High transit + High essentials = HH
  High transit + Low essentials  = HL
  Low transit  + High essentials = LH
  Low transit  + Low essentials  = LL
Each column uses the matching essentials threshold (pedestrian or wheelchair).
"""
import csv

AMENITIES_PATH = "WA amenities.csv"

PED_COL = "pedestrian_access_score"
WHEEL_COL = "wheelchair_access_score"


def access_value(transit_high, essentials_high):
    if transit_high and essentials_high:
        return "HH"
    if transit_high and not essentials_high:
        return "HL"
    if not transit_high and essentials_high:
        return "LH"
    return "LL"


def main():
    rows = []
    with open(AMENITIES_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(dict.fromkeys(reader.fieldnames))  # dedupe
        for row in reader:
            rows.append(row)

    # Drop old combined "Access score" if present; add distinguishable columns
    fieldnames = [c for c in fieldnames if c != "Access score"]
    for col in (PED_COL, WHEEL_COL):
        if col not in fieldnames:
            fieldnames.append(col)

    for row in rows:
        transit_high = (row.get("transit_threshold") or "").strip().lower() == "high"
        ped_high = (row.get("pedestrian_essentials_threshold") or "").strip().lower() == "high"
        wheel_high = (row.get("wheelchair_essentials_threshold") or "").strip().lower() == "high"
        row[PED_COL] = access_value(transit_high, ped_high)
        row[WHEEL_COL] = access_value(transit_high, wheel_high)

    with open(AMENITIES_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {AMENITIES_PATH}")
    print(f"Added columns: {PED_COL}, {WHEEL_COL} (HH, HL, LH, LL)")


if __name__ == "__main__":
    main()
