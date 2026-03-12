#!/usr/bin/env python3
"""
Add 4 columns to WA amenities.csv:
- pedestrian_essentials_count = pedestrian_grocery_store_count + pedestrian_healthcare_count + pedestrian_school_count
- pedestrian_essentials_threshold = "high" if count >= 3 else "low"
- wheelchair_essentials_count = wheelchair_grocery_store_count + wheelchair_healthcare_count + wheelchair_school_count
- wheelchair_essentials_threshold = "high" if count >= 3 else "low"
"""
import csv

INPUT_PATH = "WA amenities.csv"
OUTPUT_PATH = "WA amenities.csv"  # overwrite in place


def safe_float(val):
    if val is None or val == "":
        return 0.0
    try:
        return float(val)
    except ValueError:
        return 0.0


def main():
    rows = []
    with open(INPUT_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        for row in reader:
            rows.append(row)

    fieldnames.extend([
        "pedestrian_essentials_count",
        "pedestrian_essentials_threshold",
        "wheelchair_essentials_count",
        "wheelchair_essentials_threshold",
    ])

    for row in rows:
        ped_grocery = safe_float(row.get("pedestrian_grocery_store_count"))
        ped_healthcare = safe_float(row.get("pedestrian_healthcare_count"))
        ped_school = safe_float(row.get("pedestrian_school_count"))
        ped_count = ped_grocery + ped_healthcare + ped_school
        row["pedestrian_essentials_count"] = str(int(ped_count)) if ped_count == int(ped_count) else str(ped_count)
        row["pedestrian_essentials_threshold"] = "high" if ped_count >= 3 else "low"

        wheel_grocery = safe_float(row.get("wheelchair_grocery_store_count"))
        wheel_healthcare = safe_float(row.get("wheelchair_healthcare_count"))
        wheel_school = safe_float(row.get("wheelchair_school_count"))
        wheel_count = wheel_grocery + wheel_healthcare + wheel_school
        row["wheelchair_essentials_count"] = str(int(wheel_count)) if wheel_count == int(wheel_count) else str(wheel_count)
        row["wheelchair_essentials_threshold"] = "high" if wheel_count >= 3 else "low"

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")
    print("Added: pedestrian_essentials_count, pedestrian_essentials_threshold, wheelchair_essentials_count, wheelchair_essentials_threshold")


if __name__ == "__main__":
    main()
