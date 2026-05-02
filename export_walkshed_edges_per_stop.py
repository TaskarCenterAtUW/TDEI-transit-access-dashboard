#!/usr/bin/env python3
"""
Split a combined walkshed *edges* GeoJSON into one GeoJSON per (stop_id, agency).

Use this for maps that need the actual walkable network (LineStrings), without loading
the full multi-megabyte combined file in the browser.

Output filenames match yakima-routes.html: {safe_agency}_{safe_stop_id}.geojson
(safe = non-word chars → underscore).

Usage
-----
  python3 export_walkshed_edges_per_stop.py \\
    --edges "data/.../yakima_Unconstrained_Pedestrian_(Sidewalks_Only)_combined_edges.geojson" \\
    --out-dir "data/.../data/walkshed_edges_by_stop"
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import geopandas as gpd


def safe_file_part(value: object) -> str:
    """Match JS: String(s).trim().replace(/[^\\w\\-]+/g,'_').replace(/_+/g,'_').strip(_)."""
    t = re.sub(r"[^\w\-]+", "_", str(value).strip(), flags=re.UNICODE)
    t = re.sub(r"_+", "_", t).strip("_")
    return t if t else "unknown"


def main() -> None:
    ap = argparse.ArgumentParser(description="Export per-stop walkshed edge GeoJSON files")
    ap.add_argument("--edges", type=Path, required=True, help="Combined *edges.geojson")
    ap.add_argument("--out-dir", type=Path, required=True, help="Directory for one .geojson per stop")
    args = ap.parse_args()

    if not args.edges.is_file():
        raise SystemExit(f"Edges file not found: {args.edges}")

    print("Loading edges (may take a while)...")
    edges = gpd.read_file(args.edges)
    if edges.crs is None:
        edges.set_crs(4326, inplace=True)
    edges = edges.to_crs(4326)

    required = {"stop_id", "agency", "geometry"}
    missing = required - set(edges.columns)
    if missing:
        raise SystemExit(f"Edges GeoJSON missing columns: {sorted(missing)}")

    args.out_dir.mkdir(parents=True, exist_ok=True)

    groups = edges.groupby(["stop_id", "agency"], sort=False)
    n = len(groups)
    print(f"Writing {n} files to {args.out_dir} ...")
    for i, ((stop_id, agency), sub) in enumerate(groups, start=1):
        fn = f"{safe_file_part(agency)}_{safe_file_part(stop_id)}.geojson"
        out_path = args.out_dir / fn
        out = sub[["geometry"]].copy()
        out["stop_id"] = stop_id
        out["agency"] = agency
        out.to_file(out_path, driver="GeoJSON")
        if i % 50 == 0 or i == n:
            print(f"  {i}/{n} {fn}")
    print("Done.")


if __name__ == "__main__":
    main()
