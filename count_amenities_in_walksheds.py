#!/usr/bin/env python3
"""
Turn tagged walkshed *edges* into approximate walk *areas*, then count amenities per stop.

Pipeline
--------
1. Load combined reachable-tree edges (each feature has stop_id + agency on properties).
2. Group by (stop_id, agency), merge line geometries, buffer in meters → polygon per stop.
3. Load amenity *points* (GeoJSON or CSV with lat/lon).
4. Spatial join: which points fall inside each stop’s buffered polygon?
5. Write CSV: one row per stop that has a walkshed (all edge origins), including **amenity_count = 0**
   when no POIs fall inside the buffer (inner join alone would drop those rows).
6. Optionally write a second CSV: one row per (stop, amenity) with lat, lon, name, amenity type
   (only stops with ≥1 amenity; empty file is possible).

For **map line overlays** of raw walkshed edges, use `export_walkshed_edges_per_stop.py` instead
of buffering to polygons.

Notes
-----
- “Walkshed” here = buffer around the union of all edges returned for that origin. Tune
  BUFFER_METERS (e.g. 15–30 m) to taste; it’s an approximation, not an isochrone polygon.
- You need **point** amenities (lat/lon). Tract-level WA amenities.csv cannot be split
  per stop without point locations.
- Large edge files: this script streams groups; for very large files consider splitting
  by stop_id in a pre-pass.

Usage
-----
  python3 count_amenities_in_walksheds.py \\
    --edges "data/.../yakima_Unconstrained_Pedestrian_(Sidewalks_Only)_combined_edges.geojson" \\
    --amenities "path/to/amenities_points.geojson" \\
    --out "yakima_ped_amenity_counts.csv"

  # CSV amenities: columns lat, lon; use --amenity-type-col amenity for per-type columns (needed for yakima-routes.html / spokane-routes.html sidebars)
  python3 count_amenities_in_walksheds.py --edges ... --amenities pois.csv --lat-col lat --lon-col lon --amenity-type-col amenity

  # Per-amenity locations (default: <out>_amenity_locations.csv); disable with --no-amenity-locations
  python3 count_amenities_in_walksheds.py ... --out counts.csv --out-detail my_locations.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd


def load_amenities(path: Path, lat_col: str, lon_col: str, type_col: str | None) -> gpd.GeoDataFrame:
    if path.suffix.lower() in {".geojson", ".json"}:
        gdf = gpd.read_file(path)
        if gdf.crs is None:
            gdf.set_crs(4326, inplace=True)
        return gdf

    df = pd.read_csv(path)
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df[lon_col], df[lat_col], crs="EPSG:4326"),
    )
    if type_col and type_col not in gdf.columns:
        raise SystemExit(f"Column {type_col!r} not in CSV")
    return gdf


def main() -> None:
    ap = argparse.ArgumentParser(description="Count points inside per-stop buffered walkshed edges")
    ap.add_argument("--edges", type=Path, required=True, help="Combined walkshed edges GeoJSON")
    ap.add_argument("--amenities", type=Path, required=True, help="Points GeoJSON or CSV")
    ap.add_argument("--out", type=Path, required=True, help="Output CSV path")
    ap.add_argument(
        "--buffer-meters",
        type=float,
        default=20.0,
        help="Buffer distance around merged walk edges (meters). Default 20.",
    )
    ap.add_argument("--lat-col", default="lat", help="CSV latitude column")
    ap.add_argument("--lon-col", default="lon", help="CSV longitude column")
    ap.add_argument(
        "--amenity-type-col",
        default=None,
        help="Optional column for category (e.g. amenity, shop) for per-type counts",
    )
    ap.add_argument(
        "--name-col",
        default="name",
        help="Column for POI display name (CSV or GeoJSON). Default: name",
    )
    ap.add_argument(
        "--out-detail",
        type=Path,
        default=None,
        help="CSV: one row per amenity inside each walkshed (stop_id, agency, lat, lon, name, amenity). "
        "Default path: <out stem>_amenity_locations.csv next to --out",
    )
    ap.add_argument(
        "--no-amenity-locations",
        action="store_true",
        help="Do not write the per-amenity locations CSV.",
    )
    args = ap.parse_args()

    print("Loading edges (may take a minute)...")
    edges = gpd.read_file(args.edges)
    if edges.crs is None:
        edges.set_crs(4326, inplace=True)
    edges = edges.to_crs(3857)

    # Group by origin
    groups = edges.groupby(["stop_id", "agency"], sort=False)
    print(f"Building buffered walkshed polygons for {len(groups)} (stop_id, agency) groups...")

    rows = []
    for (stop_id, agency), sub in groups:
        geom = sub.geometry.union_all() if hasattr(sub.geometry, "union_all") else sub.geometry.unary_union
        if geom.is_empty:
            continue
        poly = geom.buffer(args.buffer_meters)
        rows.append(
            {
                "w_stop_id": stop_id,
                "w_agency": agency,
                "geometry": poly,
            }
        )

    walksheds = gpd.GeoDataFrame(rows, crs=3857)
    print(f"Walkshed polygons: {len(walksheds)}")

    print("Loading amenities...")
    pois = load_amenities(args.amenities, args.lat_col, args.lon_col, args.amenity_type_col)
    pois = pois.to_crs(3857)

    print("Spatial join...")
    joined = gpd.sjoin(pois, walksheds, how="inner", predicate="within")

    # Every walkshed origin gets a row, even when amenity_count is 0 (inner join alone omits those).
    base = walksheds[["w_stop_id", "w_agency"]].drop_duplicates().copy()
    base.rename(columns={"w_stop_id": "stop_id", "w_agency": "agency"}, inplace=True)
    base.reset_index(drop=True, inplace=True)

    hit = (
        joined.groupby(["w_stop_id", "w_agency"])
        .size()
        .reset_index(name="amenity_count")
        .rename(columns={"w_stop_id": "stop_id", "w_agency": "agency"})
    )
    counts = base.merge(hit, on=["stop_id", "agency"], how="left")
    counts["amenity_count"] = counts["amenity_count"].fillna(0).astype(int)

    if (
        args.amenity_type_col
        and args.amenity_type_col in joined.columns
        and len(joined) > 0
    ):
        pivot = (
            joined.groupby(
                ["w_stop_id", "w_agency", joined[args.amenity_type_col].fillna("unknown")]
            )
            .size()
            .unstack(fill_value=0)
        )
        pivot = pivot.reset_index().rename(columns={"w_stop_id": "stop_id", "w_agency": "agency"})
        counts = counts.merge(pivot, on=["stop_id", "agency"], how="left")
        for c in counts.columns:
            if c in ("stop_id", "agency", "amenity_count"):
                continue
            counts[c] = pd.to_numeric(counts[c], errors="coerce").fillna(0).astype(int)

    counts.to_csv(args.out, index=False)
    print(f"Wrote {args.out} ({len(counts)} rows)")

    if not args.no_amenity_locations:
        detail_path = args.out_detail or args.out.with_name(f"{args.out.stem}_amenity_locations.csv")
        joined_wgs = joined.to_crs(4326)
        detail = pd.DataFrame(
            {
                "stop_id": joined_wgs["w_stop_id"],
                "agency": joined_wgs["w_agency"],
                "lat": joined_wgs.geometry.y,
                "lon": joined_wgs.geometry.x,
            }
        )
        nc = args.name_col
        if nc in joined_wgs.columns:
            detail["name"] = joined_wgs[nc].fillna("").astype(str)
        else:
            detail["name"] = ""
        type_col = args.amenity_type_col
        if type_col and type_col in joined_wgs.columns:
            detail["amenity"] = joined_wgs[type_col].fillna("").astype(str)
        elif "amenity" in joined_wgs.columns:
            detail["amenity"] = joined_wgs["amenity"].fillna("").astype(str)
        else:
            detail["amenity"] = ""
        if "type" in joined_wgs.columns:
            detail["osm_type"] = joined_wgs["type"].fillna("").astype(str)
        detail = detail.sort_values(["stop_id", "agency", "lat", "lon", "name"])
        detail.to_csv(detail_path, index=False)
        print(f"Wrote {detail_path} ({len(detail)} amenity rows)")


if __name__ == "__main__":
    main()
