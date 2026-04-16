#!/usr/bin/env python3
"""
Subset WA Bus Routes with score.csv for a local map / walkshed run.

  --area yakima   Stops inside Yakima *city limits* (`Yakima_city_limits.geojson`).
  --area spokane  Stops inside Spokane *city limits* (`Spokane_city_limits.geojson`).

Both use the municipal boundary polygon, not county FIPS.

Usage:
  python3 subset_yakima_city_routes.py --area yakima
  python3 subset_yakima_city_routes.py --area spokane
  python3 subset_yakima_city_routes.py --area seattle
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parent
INPUT_CSV = ROOT / "WA Bus Routes with score.csv"
JURISDICTION = ROOT / "jurisdiction_bounds"

YAKIMA_BOUNDARY = JURISDICTION / "Yakima_city_limits.geojson"
YAKIMA_OUTPUT = ROOT / "WA Bus Routes with score - Yakima city subset.csv"

SPOKANE_BOUNDARY = JURISDICTION / "Spokane_city_limits.geojson"
SPOKANE_OUTPUT = ROOT / "WA Bus Routes with score - Spokane city subset.csv"

SEATTLE_BOUNDARY = JURISDICTION / "Seattle_city_limits.geojson"
SEATTLE_OUTPUT = ROOT / "WA Bus Routes with score - Seattle city subset.csv"


def subset_by_city_limits(
    boundary_path: Path,
    output_csv: Path,
    area_label: str,
) -> None:
    """Keep CSV rows whose stop (lon, lat) lies inside the city limits polygon."""
    if not boundary_path.is_file():
        raise SystemExit(f"Boundary not found: {boundary_path}")

    boundary_gdf = gpd.read_file(boundary_path)
    if boundary_gdf.empty:
        raise RuntimeError(f"{area_label} boundary file has no features.")

    boundary_geom = boundary_gdf.geometry.union_all()

    kept_rows = 0
    total_rows = 0

    with INPUT_CSV.open("r", newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise RuntimeError("Input CSV header is missing.")

        with output_csv.open("w", newline="", encoding="utf-8") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()

            for row in reader:
                total_rows += 1
                try:
                    lat = float((row.get("stop_lat") or "").strip())
                    lon = float((row.get("stop_lon") or "").strip())
                except ValueError:
                    continue

                pt = Point(lon, lat)
                if boundary_geom.covers(pt):
                    writer.writerow(row)
                    kept_rows += 1

    print(f"Input rows checked: {total_rows}")
    print(f"Rows inside {area_label} city limits: {kept_rows}")
    print(f"Wrote: {output_csv}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Subset WA Bus Routes CSV by city limits")
    ap.add_argument(
        "--area",
        choices=("yakima", "spokane", "seattle"),
        required=True,
        help="City polygon from jurisdiction_bounds/",
    )
    args = ap.parse_args()

    if not INPUT_CSV.is_file():
        raise SystemExit(f"Input not found: {INPUT_CSV}")

    if args.area == "yakima":
        subset_by_city_limits(YAKIMA_BOUNDARY, YAKIMA_OUTPUT, "Yakima")
        return
    if args.area == "spokane":
        subset_by_city_limits(SPOKANE_BOUNDARY, SPOKANE_OUTPUT, "Spokane")
        return
    subset_by_city_limits(SEATTLE_BOUNDARY, SEATTLE_OUTPUT, "Seattle")


if __name__ == "__main__":
    main()
