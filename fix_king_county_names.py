#!/usr/bin/env python3
"""
Fill missing wa_demo_census_tract_NAME in WA amenities.csv for King County
tracts so that the county name appears.

For any row where:
  - GEOID starts with \"53033\" (King County)
  - wa_demo_census_tract_NAME is empty
set wa_demo_census_tract_NAME to:
  "Census Tract <GEOID>; King County; Washington"
"""
import csv

PATH = "WA amenities.csv"


def main():
  rows = []
  with open(PATH, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = list(reader.fieldnames)
    for row in reader:
      rows.append(row)

  updated = 0
  for row in rows:
    name = (row.get("wa_demo_census_tract_NAME") or "").strip()
    geoid = (row.get("GEOID") or "").strip()
    if geoid.startswith("53033") and not name:
      tract_part = geoid[-5:]
      row["wa_demo_census_tract_NAME"] = f"Census Tract {tract_part}; King County; Washington"
      updated += 1

  with open(PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

  print(f"Updated {updated} King County rows in {PATH}")


if __name__ == "__main__":
  main()

