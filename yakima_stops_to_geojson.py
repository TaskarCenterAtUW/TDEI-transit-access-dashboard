#!/usr/bin/env python3
"""
Build a Point GeoJSON from a bus-stop subset CSV.

- Coordinates use GeoJSON order: [longitude, latitude] (WGS84 / EPSG:4326).
- One feature per unique (stop_id, agency); duplicates in the CSV are merged.
- Properties: stop_id, agency, stop_name, and name (same as stop_name for walkshed logging).

Usage (defaults match each preset):
  python3 yakima_stops_to_geojson.py --preset yakima
  python3 yakima_stops_to_geojson.py --preset spokane
  python3 yakima_stops_to_geojson.py --preset seattle
  python3 yakima_stops_to_geojson.py --input other.csv --output out.geojson
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPOKANE_DATASET_DIR = ROOT / "data" / "cbb2ed42-c77f-4218-96de-1b13eafa939f" / "data" / "pois"
SEATTLE_DATASET_DIR = ROOT / "data" / "05776f25-f0f3-461c-ac34-4fa88a00936c" / "data" / "pois"

PRESETS = {
    "yakima": {
        "input": ROOT / "WA Bus Routes with score - Yakima city subset.csv",
        "output": ROOT / "yakima_unique_stops.geojson",
        "collection_name": "Yakima city unique bus stops",
    },
    "spokane": {
        "input": ROOT / "WA Bus Routes with score - Spokane city subset.csv",
        "output": SPOKANE_DATASET_DIR / "spokane_filtered_amenities.geojson",
        "collection_name": "Spokane city unique bus stops",
    },
    "seattle": {
        "input": ROOT / "WA Bus Routes with score - Seattle city subset.csv",
        "output": SEATTLE_DATASET_DIR / "seattle_filtered_amenities.geojson",
        "collection_name": "Seattle city unique bus stops",
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Bus stops CSV → Point GeoJSON")
    parser.add_argument(
        "--preset",
        choices=("yakima", "spokane", "seattle"),
        default=None,
        help="Default input/output paths for Yakima, Spokane, or Seattle city",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Input CSV (must include stop_lat, stop_lon, stop_id, agency)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output GeoJSON path",
    )
    args = parser.parse_args()

    if args.preset and (args.input is not None or args.output is not None):
        raise SystemExit("Use either --preset alone or explicit --input/--output, not both.")

    if args.preset:
        cfg = PRESETS[args.preset]
        input_path = cfg["input"]
        output_path = cfg["output"]
        collection_name = cfg["collection_name"]
    else:
        input_path = args.input or (
            ROOT / "WA Bus Routes with score - Yakima city subset.csv"
        )
        output_path = args.output or (ROOT / "yakima_unique_stops.geojson")
        collection_name = "Bus stops"

    if not input_path.is_file():
        raise SystemExit(f"Input not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    by_key: dict[tuple[str, str], dict] = {}
    coord_mismatches = 0

    with input_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"stop_lat", "stop_lon", "stop_id", "agency"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            missing = required - set(reader.fieldnames or [])
            raise SystemExit(f"CSV missing columns: {sorted(missing)}")

        for row in reader:
            sid = (row.get("stop_id") or "").strip()
            agency = (row.get("agency") or "").strip()
            if not sid or not agency:
                continue
            try:
                lat = float((row.get("stop_lat") or "").strip())
                lon = float((row.get("stop_lon") or "").strip())
            except ValueError:
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue

            key = (sid, agency)
            name = (row.get("stop_name") or "").strip()
            if key in by_key:
                prev = by_key[key]
                if abs(prev["lat"] - lat) > 1e-6 or abs(prev["lon"] - lon) > 1e-6:
                    coord_mismatches += 1
                continue
            by_key[key] = {
                "lat": lat,
                "lon": lon,
                "stop_id": sid,
                "agency": agency,
                "stop_name": name,
            }

    features = []
    for rec in sorted(by_key.values(), key=lambda r: (r["agency"], r["stop_id"])):
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [rec["lon"], rec["lat"]],
                },
                "properties": {
                    "stop_id": rec["stop_id"],
                    "agency": rec["agency"],
                    "stop_name": rec["stop_name"],
                    "name": rec["stop_name"] or "Unknown",
                },
            }
        )

    fc = {
        "type": "FeatureCollection",
        "name": collection_name,
        "features": features,
    }

    output_path.write_text(json.dumps(fc, indent=2), encoding="utf-8")
    print(f"Unique (stop_id, agency) pairs: {len(features)}")
    print(f"Rows with conflicting coords for same pair (skipped after first): {coord_mismatches}")
    print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
