#!/usr/bin/env python3
"""
Run the full transit accessibility pipeline for a single WA jurisdiction.

This script orchestrates all steps from raw route data to a finished HTML map:
  1.  Subset WA Bus Routes CSV to stops inside city boundary
  2.  Generate bus stops GeoJSON (unique stop points)
  3.  Run TDEI walkshed API — Pedestrian profile (batched)
  4.  Export per-stop walkshed edge files — Pedestrian
  5.  Run TDEI walkshed API — Manual Wheelchair profile (batched)
  6.  Export per-stop walkshed edge files — Wheelchair
  7.  Query OSM for amenity points inside the city's walkshed bounding box
  8.  Count amenities per stop — Pedestrian
  9.  Count amenities per stop — Wheelchair
  10. Generate HTML city map from seattle-routes.html template
  11. Update pipeline_progress.json

Skips already-completed steps based on output file existence.
Generates a placeholder map page for cities with zero bus stops.

Usage:
  python3 run_city_pipeline.py --city WSP_Aberdeen_City
  python3 run_city_pipeline.py --city WSP_Seattle_City --batch-size 500
  python3 run_city_pipeline.py --city WSP_Aberdeen_City --skip-walksheds
  python3 run_city_pipeline.py --city WSP_Aberdeen_City --force-step subset_routes
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JURISDICTION_CSV = ROOT / "Jurisdiction Codes.csv"
BOUNDS_DIR = ROOT / "jurisdiction_bounds"
DATA_DIR = ROOT / "data"
CITIES_DIR = ROOT / "cities"
PROGRESS_FILE = ROOT / "pipeline_progress.json"
TEMPLATE_SOURCE = ROOT / "seattle-routes.html"

# Jurisdiction type suffixes (last token of WSP name after stripping WSP_)
KNOWN_TYPES = {"City", "city", "UI", "County", "Plus"}


# ── Jurisdiction resolution ──────────────────────────────────────────────────

def load_highest_version_datasets() -> dict[str, tuple[float, str]]:
    """Return {wsp_name: (version, dataset_id)} for the highest-version entry per jurisdiction."""
    best: dict[str, tuple[float, str]] = {}
    with JURISDICTION_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            uid, name, ver_str = row[0].strip(), row[1].strip(), row[2].strip()
            try:
                ver = float(ver_str)
            except ValueError:
                continue
            if name not in best or ver > best[name][0]:
                best[name] = (ver, uid)
    return best


def parse_wsp_name(wsp_name: str) -> tuple[str, str]:
    """
    Split a WSP jurisdiction name into (place, type).

    Examples:
      WSP_Aberdeen_City         → ('Aberdeen', 'City')
      WSP_Aberdeen_Cosmopolis_City → ('Aberdeen_Cosmopolis', 'City')
      WSP_Adams_UI              → ('Adams', 'UI')
      WSP_King_County           → ('King', 'County')
    """
    name = wsp_name.removeprefix("WSP_")
    tokens = name.split("_")
    if not tokens:
        return name, "City"

    # Handle multi-word trailing types like "Renton Health Through Housing"
    # by checking known single-token types first, then falling back.
    if tokens[-1] in KNOWN_TYPES:
        return "_".join(tokens[:-1]), tokens[-1]

    # Fall back: treat last token as type
    return "_".join(tokens[:-1]), tokens[-1]


def to_display_name(place: str) -> str:
    """'Aberdeen_Cosmopolis' → 'Aberdeen Cosmopolis'"""
    return place.replace("_", " ")


def to_slug(display: str) -> str:
    """'Aberdeen Cosmopolis' → 'aberdeen-cosmopolis'"""
    return re.sub(r"[^a-z0-9]+", "-", display.lower()).strip("-")


def find_boundary_file(place: str, type_str: str) -> str | None:
    """
    Find the best-matching boundary GeoJSON filename in jurisdiction_bounds/.

    Returns just the filename (e.g. 'Aberdeen_city_limits.geojson'), not full path.
    """
    candidates: list[str] = []
    t = type_str.lower()

    if t in ("city",):
        # Try both naming conventions: "Benton_city_limits.geojson" and
        # "Benton_City_city_limits.geojson" (places where "City" is baked into the name)
        candidates = [
            f"{place}_city_limits.geojson",
            f"{place}_City_city_limits.geojson",
        ]
    elif t == "ui":
        # Urban Interface areas map to county boundaries
        candidates = [
            f"{place}_County_county_limits.geojson",
            f"{place}_county_limits.geojson",
            f"{place}_city_limits.geojson",
        ]
    elif t == "county":
        candidates = [
            f"{place}_county_limits.geojson",
            f"{place}_County_county_limits.geojson",
        ]
    elif t == "plus":
        candidates = [
            f"{place}_city_limits.geojson",
            f"{place}_City_city_limits.geojson",
            f"{place}_county_limits.geojson",
        ]
    else:
        candidates = [
            f"{place}_{type_str}_limits.geojson",
            f"{place}_city_limits.geojson",
        ]

    for candidate in candidates:
        if (BOUNDS_DIR / candidate).exists():
            return candidate

    # Fuzzy fallback: any file whose stem starts with the place name.
    # Prefer file types that match the jurisdiction type — for "city" jurisdictions
    # never silently fall back to "_county_limits" files (those are huge regions).
    fuzzy_matches = [
        f.name for f in BOUNDS_DIR.iterdir()
        if f.name.startswith(place + "_") and "limits" in f.name
    ]
    if t == "city":
        # Filter out any county-type fallbacks for city jurisdictions
        city_only = [n for n in fuzzy_matches if "_county_limits" not in n.lower()]
        if city_only:
            return sorted(city_only)[0]
        # No city-shaped match → don't accept a county fallback
        return None
    if fuzzy_matches:
        return sorted(fuzzy_matches)[0]

    return None


def compute_map_center_and_zoom(boundary_filename: str) -> tuple[float, float, int]:
    """
    Read a boundary GeoJSON and return (lon, lat, zoom) for map initialisation.
    Zoom is estimated from bounding box size.
    """
    path = BOUNDS_DIR / boundary_filename
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return -120.5, 47.5, 10  # WA state center fallback

    min_lon, min_lat, max_lon, max_lat = 180.0, 90.0, -180.0, -90.0

    def walk(coords: object) -> None:
        nonlocal min_lon, min_lat, max_lon, max_lat
        if not coords:
            return
        if isinstance(coords[0], (int, float)):
            min_lon = min(min_lon, coords[0])
            max_lon = max(max_lon, coords[0])
            min_lat = min(min_lat, coords[1])
            max_lat = max(max_lat, coords[1])
        else:
            for c in coords:
                walk(c)

    for feat in data.get("features", [data] if "coordinates" in data.get("geometry", {}) else []):
        geom = feat.get("geometry") or feat
        if geom:
            walk(geom.get("coordinates", []))

    if min_lon > max_lon:
        return -120.5, 47.5, 10

    center_lon = round((min_lon + max_lon) / 2, 5)
    center_lat = round((min_lat + max_lat) / 2, 5)
    span = max(max_lon - min_lon, (max_lat - min_lat) * 1.5)

    if span > 0.8:
        zoom = 10
    elif span > 0.4:
        zoom = 11
    elif span > 0.15:
        zoom = 12
    elif span > 0.06:
        zoom = 13
    else:
        zoom = 14

    return center_lon, center_lat, zoom


# ── Progress tracking ────────────────────────────────────────────────────────

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_progress(progress: dict) -> None:
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2), encoding="utf-8")


# ── Subprocess helpers ───────────────────────────────────────────────────────

def run(cmd: list[str], step_name: str) -> None:
    """Run a subprocess command, raising on failure."""
    print(f"\n{'='*60}")
    print(f"  STEP: {step_name}")
    print(f"  CMD:  {' '.join(str(c) for c in cmd)}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"Step '{step_name}' failed (exit {result.returncode})")


def py(*args) -> list[str]:
    """Return [sys.executable, *args] for subprocess calls."""
    return [sys.executable, *[str(a) for a in args]]


# ── HTML generation ──────────────────────────────────────────────────────────

def generate_city_html(
    city_display: str,
    city_slug: str,
    dataset_id: str,
    center_lon: float,
    center_lat: float,
    zoom: int,
    boundary_filename: str,
) -> str:
    """
    Generate a city HTML map by substituting city-specific values into the
    seattle-routes.html template. All data paths are relative to cities/.
    """
    html = TEMPLATE_SOURCE.read_text(encoding="utf-8")

    # Title and heading
    html = html.replace(
        "<title>Seattle city — bus routes & stops</title>",
        f"<title>{city_display} city — bus routes & stops</title>",
    )
    html = html.replace(
        "Seattle city transit",
        f"{city_display} city transit",
    )

    # Sidebar muted text
    html = html.replace(
        "Routes: <code>WA Bus Routes with score - Seattle city subset.csv</code>",
        f"Routes: <code>route_subsets/WA Bus Routes with score - {city_display} city subset.csv</code>",
    )
    html = html.replace(
        "Blue tint: Seattle city limits (<code>jurisdiction_bounds/Seattle_city_limits.geojson</code>).",
        f"Blue tint: {city_display} city limits (<code>jurisdiction_bounds/{boundary_filename}</code>).",
    )

    # JS map constants
    html = html.replace(
        "const SEATTLE_CENTER = [-122.33, 47.61];",
        f"const CENTER = [{center_lon}, {center_lat}];",
    )
    html = html.replace("const SEATTLE_ZOOM = 11;", f"const ZOOM = {zoom};")
    html = html.replace("center: SEATTLE_CENTER,", "center: CENTER,")
    html = html.replace("zoom: SEATTLE_ZOOM", "zoom: ZOOM")

    # DATASET path: large data lives on Azure Blob Storage (via DATA_BASE)
    html = html.replace(
        "const DATASET = `${DATA_BASE}/data/05776f25-f0f3-461c-ac34-4fa88a00936c/data`;",
        f"const DATASET = `${{DATA_BASE}}/data/{dataset_id}/data`;",
    )

    # Amenity CSV filenames
    html = html.replace("metrics/seattle_ped_amenity_counts.csv",
                         f"metrics/{city_slug}_ped_amenity_counts.csv")
    html = html.replace("metrics/seattle_ped_amenity_counts_amenity_locations.csv",
                         f"metrics/{city_slug}_ped_amenity_counts_amenity_locations.csv")
    html = html.replace("metrics/seattle_wc_amenity_counts.csv",
                         f"metrics/{city_slug}_wc_amenity_counts.csv")
    html = html.replace("metrics/seattle_wc_amenity_counts_amenity_locations.csv",
                         f"metrics/{city_slug}_wc_amenity_counts_amenity_locations.csv")

    # Boundary URL (on Azure Blob Storage via DATA_BASE)
    html = html.replace(
        "const SEATTLE_CITY_BOUNDARY_URL = `${DATA_BASE}/jurisdiction_bounds/Seattle_city_limits.geojson`;",
        f"const CITY_BOUNDARY_URL = `${{DATA_BASE}}/jurisdiction_bounds/{boundary_filename}`;",
    )

    # Routes CSV fetch (relative from cities/)
    html = html.replace(
        "fetch('route_subsets/WA Bus Routes with score - Seattle city subset.csv'),",
        f"fetch('../route_subsets/WA Bus Routes with score - {city_display} city subset.csv'),",
    )

    # Boundary fetch and warn
    html = html.replace("fetch(SEATTLE_CITY_BOUNDARY_URL)", "fetch(CITY_BOUNDARY_URL)")
    html = html.replace(
        "console.warn('Seattle city boundary not loaded:', boundaryResp.status, SEATTLE_CITY_BOUNDARY_URL);",
        f"console.warn('{city_display} city boundary not loaded:', boundaryResp.status, CITY_BOUNDARY_URL);",
    )

    # MapLibre source/layer IDs
    html = html.replace("'seattle-city-boundary'", "'city-boundary'")
    html = html.replace("'seattle-city-boundary-fill'", "'city-boundary-fill'")
    html = html.replace("'seattle-city-boundary-outline'", "'city-boundary-outline'")

    # Error alert
    html = html.replace(
        "alert('Failed to load Seattle routes: ' + err.message);",
        f"alert('Failed to load {city_display} routes: ' + err.message);",
    )

    # Generic comment
    html = html.replace(
        "/** Seattle city subset: no agency exclusions; collect deduped stop points for map. */",
        "/** No agency exclusions; collect deduped stop points for map. */",
    )

    return html


def generate_placeholder_html(city_display: str, city_slug: str) -> str:
    """Generate a simple placeholder page for cities with no bus stops in the dataset."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{city_display} — No Transit Data</title>
  <style>
    body {{ font-family: system-ui, sans-serif; display: flex; align-items: center;
           justify-content: center; height: 100vh; margin: 0; background: #f8f9fa; }}
    .box {{ text-align: center; padding: 40px; background: #fff; border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1); max-width: 400px; }}
    h1 {{ font-size: 22px; margin: 0 0 12px; }}
    p {{ color: #555; margin: 6px 0; }}
    a {{ color: #1d4ed8; }}
  </style>
</head>
<body>
  <div class="box">
    <h1>{city_display}</h1>
    <p>No bus stop data found for this jurisdiction in the current WA Bus Routes dataset.</p>
    <p>This map page will be updated when route data becomes available.</p>
    <p style="margin-top:20px"><a href="index.html">← Back to all cities</a></p>
  </div>
</body>
</html>
"""


# ── Pipeline steps ───────────────────────────────────────────────────────────

def count_stops_in_geojson(geojson_path: Path) -> int:
    try:
        data = json.loads(geojson_path.read_text(encoding="utf-8"))
        return len(data.get("features", []))
    except Exception:
        return 0


def find_combined_edges(data_path: Path, profile_fragment: str) -> Path | None:
    """Find the merged *_combined_edges.geojson for a given profile fragment."""
    wg = data_path / "walkshed_geojson"
    if not wg.is_dir():
        return None
    for f in wg.iterdir():
        if profile_fragment in f.name and f.name.endswith("_combined_edges.geojson") \
                and "batch" not in f.name:
            return f
    return None


def walkshed_edges_dir_populated(path: Path) -> bool:
    return path.is_dir() and any(path.glob("*.geojson"))


def amenities_csv_exists(data_path: Path, dataset_id: str) -> bool:
    return (data_path / "csv_pois" / f"{dataset_id}_filtered_amenities.csv").is_file()


# ── Main ─────────────────────────────────────────────────────────────────────

def run_pipeline(
    wsp_name: str,
    batch_size: int = 500,
    skip_walksheds: bool = False,
    force_step: str | None = None,
    dataset_id_override: str | None = None,
) -> str:
    """
    Run the full pipeline for one jurisdiction. Returns the final status string
    ('completed', 'no_stops', 'failed').
    """
    print(f"\n{'#'*70}")
    print(f"  PIPELINE: {wsp_name}")
    print(f"{'#'*70}\n")

    # ── Resolve jurisdiction ─────────────────────────────────────────────────
    all_datasets = load_highest_version_datasets()
    if wsp_name not in all_datasets:
        raise SystemExit(f"Unknown jurisdiction: {wsp_name}\nCheck Jurisdiction Codes.csv")

    _, dataset_id = all_datasets[wsp_name]
    if dataset_id_override:
        dataset_id = dataset_id_override
        print(f"  (dataset ID overridden to {dataset_id})")
    place, type_str = parse_wsp_name(wsp_name)
    city_display = to_display_name(place)
    city_slug = to_slug(city_display)

    boundary_filename = find_boundary_file(place, type_str)
    if not boundary_filename:
        print(f"WARNING: No boundary file found for {wsp_name} (place={place}, type={type_str}). "
              "Skipping city.")
        return "no_boundary"

    center_lon, center_lat, zoom = compute_map_center_and_zoom(boundary_filename)

    print(f"  Display name : {city_display}")
    print(f"  Slug         : {city_slug}")
    print(f"  Dataset ID   : {dataset_id}")
    print(f"  Boundary     : {boundary_filename}")
    print(f"  Map center   : [{center_lon}, {center_lat}] zoom {zoom}")

    # ── Paths ────────────────────────────────────────────────────────────────
    data_path = DATA_DIR / dataset_id / "data"
    stops_dir = data_path / "stops"
    metrics_dir = data_path / "metrics"
    walkshed_geojson_dir = data_path / "walkshed_geojson"
    ped_edges_dir = data_path / "walkshed_edges_by_stop"
    wc_edges_dir = data_path / "walkshed_edges_by_stop_wheelchair"

    routes_subset_csv = ROOT / "route_subsets" / f"WA Bus Routes with score - {city_display} city subset.csv"
    stops_geojson = stops_dir / f"{city_slug}_bus_stops.geojson"
    amenities_csv = data_path / "csv_pois" / f"{dataset_id}_filtered_amenities.csv"
    ped_counts_csv = metrics_dir / f"{city_slug}_ped_amenity_counts.csv"
    wc_counts_csv = metrics_dir / f"{city_slug}_wc_amenity_counts.csv"
    html_out = CITIES_DIR / f"{city_slug}.html"

    # Create required directories
    for d in [stops_dir, metrics_dir, walkshed_geojson_dir, ped_edges_dir, wc_edges_dir,
              data_path / "csv_pois", data_path / "overpass_tile_cache", CITIES_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    def should_run(step: str, output_exists: bool) -> bool:
        if force_step == step:
            return True
        return not output_exists

    # ── Step 1: Subset routes ────────────────────────────────────────────────
    if should_run("subset_routes", routes_subset_csv.is_file()):
        run(py("subset_yakima_city_routes.py",
               "--boundary", BOUNDS_DIR / boundary_filename,
               "--output", routes_subset_csv,
               "--label", city_display),
            "subset_routes")
    else:
        print(f"[SKIP] subset_routes — {routes_subset_csv.name} exists")

    # ── Step 2: Generate bus stops GeoJSON ───────────────────────────────────
    if should_run("stops_geojson", stops_geojson.is_file()):
        run(py("yakima_stops_to_geojson.py",
               "--city-slug", city_slug,
               "--dataset-id", dataset_id,
               "--input", routes_subset_csv),
            "stops_geojson")
    else:
        print(f"[SKIP] stops_geojson — {stops_geojson.name} exists")

    # ── Check stop count ─────────────────────────────────────────────────────
    stop_count = count_stops_in_geojson(stops_geojson)
    print(f"\n  Stop count: {stop_count}")

    if stop_count == 0:
        print(f"  → No bus stops found. Generating placeholder HTML.")
        html_out.write_text(generate_placeholder_html(city_display, city_slug), encoding="utf-8")
        return "no_stops"

    if not skip_walksheds:
        # ── Step 3: Pedestrian walksheds (batched) ───────────────────────────
        ped_profile = "Unconstrained_Pedestrian"
        ped_combined = find_combined_edges(data_path, ped_profile)
        if should_run("walksheds_ped", ped_combined is not None):
            # Run in batches of batch_size
            for start in range(0, stop_count, batch_size):
                end = min(start + batch_size, stop_count)
                run(py("run_walksheds_from_geojson.py",
                       "--dataset", dataset_id,
                       "--batch-size", batch_size,
                       "--batch-index", start // batch_size),
                    f"walksheds_ped batch {start}-{end}")
            # Merge batches and delete intermediates to save disk space
            run(py("run_walksheds_from_geojson.py",
                   "--dataset", dataset_id,
                   "--merge-batches",
                   "--delete-batch-files"),
                "walksheds_ped merge")
            ped_combined = find_combined_edges(data_path, ped_profile)
        else:
            print(f"[SKIP] walksheds_ped — combined edges file exists")

        # ── Step 4: Export per-stop edges — Pedestrian ───────────────────────
        if ped_combined and should_run("export_ped", walkshed_edges_dir_populated(ped_edges_dir)):
            run(py("export_walkshed_edges_per_stop.py",
                   "--edges", ped_combined,
                   "--out-dir", ped_edges_dir),
                "export_ped")
        else:
            print(f"[SKIP] export_ped — directory already populated")

        # ── Step 5: Wheelchair walksheds (batched) ───────────────────────────
        wc_profile = "Manual_Wheelchair"
        wc_combined = find_combined_edges(data_path, wc_profile)
        if should_run("walksheds_wc", wc_combined is not None):
            for start in range(0, stop_count, batch_size):
                end = min(start + batch_size, stop_count)
                run(py("run_walksheds_from_geojson.py",
                       "--dataset", dataset_id,
                       "--batch-size", batch_size,
                       "--batch-index", start // batch_size),
                    f"walksheds_wc batch {start}-{end}")
            run(py("run_walksheds_from_geojson.py",
                   "--dataset", dataset_id,
                   "--merge-batches",
                   "--delete-batch-files"),
                "walksheds_wc merge")
            wc_combined = find_combined_edges(data_path, wc_profile)
        else:
            print(f"[SKIP] walksheds_wc — combined edges file exists")

        # ── Step 6: Export per-stop edges — Wheelchair ───────────────────────
        if wc_combined and should_run("export_wc", walkshed_edges_dir_populated(wc_edges_dir)):
            run(py("export_walkshed_edges_per_stop.py",
                   "--edges", wc_combined,
                   "--out-dir", wc_edges_dir),
                "export_wc")
        else:
            print(f"[SKIP] export_wc — directory already populated")

    # ── Step 7: Query OSM amenities ──────────────────────────────────────────
    if should_run("query_osm", amenities_csv_exists(data_path, dataset_id)):
        run(py("query_osm_pois.py", "--dataset", dataset_id), "query_osm")
    else:
        print(f"[SKIP] query_osm — amenities CSV exists")

    # ── Step 8 & 9: Count amenities (ped + wheelchair) ───────────────────────
    ped_combined = find_combined_edges(data_path, "Unconstrained_Pedestrian")
    wc_combined = find_combined_edges(data_path, "Manual_Wheelchair")

    if ped_combined and amenities_csv.is_file():
        if should_run("count_ped", ped_counts_csv.is_file()):
            run(py("count_amenities_in_walksheds.py",
                   "--edges", ped_combined,
                   "--amenities", amenities_csv,
                   "--lat-col", "lat",
                   "--lon-col", "lon",
                   "--amenity-type-col", "amenity",
                   "--out", ped_counts_csv,
                   "--out-detail", metrics_dir / f"{city_slug}_ped_amenity_counts_amenity_locations.csv"),
                "count_ped")
        else:
            print(f"[SKIP] count_ped — {ped_counts_csv.name} exists")
    else:
        print("[WARN] count_ped skipped — missing pedestrian combined edges or amenities CSV")

    if wc_combined and amenities_csv.is_file():
        if should_run("count_wc", wc_counts_csv.is_file()):
            run(py("count_amenities_in_walksheds.py",
                   "--edges", wc_combined,
                   "--amenities", amenities_csv,
                   "--lat-col", "lat",
                   "--lon-col", "lon",
                   "--amenity-type-col", "amenity",
                   "--out", wc_counts_csv,
                   "--out-detail", metrics_dir / f"{city_slug}_wc_amenity_counts_amenity_locations.csv"),
                "count_wc")
        else:
            print(f"[SKIP] count_wc — {wc_counts_csv.name} exists")
    else:
        print("[WARN] count_wc skipped — missing wheelchair combined edges or amenities CSV")

    # ── Step 10: Generate HTML ───────────────────────────────────────────────
    print(f"\n[STEP] generate_html → {html_out}")
    html_content = generate_city_html(
        city_display, city_slug, dataset_id,
        center_lon, center_lat, zoom, boundary_filename,
    )
    html_out.write_text(html_content, encoding="utf-8")
    print(f"  Wrote: {html_out}")

    # ── Step 11: Update statewide manifest ───────────────────────────────────
    try:
        agency = _infer_agency_from_routes(routes_subset_csv)
        update_processed_cities_manifest(
            slug=city_slug, name=city_display, agency=agency,
            stops=stop_count, dataset_id=dataset_id,
            boundary=boundary_filename,
            center=[center_lon, center_lat], zoom=zoom,
        )
    except Exception as exc:
        print(f"  [WARN] Failed to update statewide manifest: {exc}")

    return "completed"


# ── Manifest helpers ─────────────────────────────────────────────────────────

PROCESSED_CITIES_MANIFEST = CITIES_DIR / "processed_cities.json"


def _infer_agency_from_routes(routes_csv: Path) -> str:
    """Return the most common agency name from a routes subset CSV."""
    from collections import Counter
    try:
        with routes_csv.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            agencies = [r.get("agency", "").strip() for r in reader if r.get("agency", "").strip()]
        return Counter(agencies).most_common(1)[0][0] if agencies else ""
    except Exception:
        return ""


def update_processed_cities_manifest(*, slug, name, agency, stops,
                                     dataset_id, boundary, center, zoom):
    """Add/update this city's entry in cities/processed_cities.json."""
    manifest: dict = {}
    if PROCESSED_CITIES_MANIFEST.is_file():
        try:
            manifest = json.loads(PROCESSED_CITIES_MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    manifest[slug] = {
        "name": name,
        "agency": agency,
        "stops": stops,
        "dataset_id": dataset_id,
        "boundary": boundary,
        "center": center,
        "zoom": zoom,
    }
    # Stable, alphabetical ordering for diffs
    ordered = {k: manifest[k] for k in sorted(manifest)}
    PROCESSED_CITIES_MANIFEST.write_text(
        json.dumps(ordered, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  Updated manifest: {PROCESSED_CITIES_MANIFEST}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run the full transit map pipeline for a single WA jurisdiction."
    )
    ap.add_argument(
        "--city",
        required=True,
        help="WSP jurisdiction name, e.g. WSP_Aberdeen_City (from Jurisdiction Codes.csv)",
    )
    ap.add_argument(
        "--dataset-id",
        default=None,
        help="Override the dataset ID instead of using the highest-version one from Jurisdiction Codes.csv",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of stops per walkshed batch (default: 500)",
    )
    ap.add_argument(
        "--skip-walksheds",
        action="store_true",
        help="Skip walkshed generation steps (useful if walksheds already exist)",
    )
    ap.add_argument(
        "--force-step",
        default=None,
        choices=[
            "subset_routes", "stops_geojson", "walksheds_ped", "export_ped",
            "walksheds_wc", "export_wc", "query_osm", "count_ped", "count_wc",
            "generate_html",
        ],
        help="Force a specific step to re-run even if its output already exists",
    )
    args = ap.parse_args()

    progress = load_progress()
    try:
        status = run_pipeline(
            wsp_name=args.city,
            batch_size=args.batch_size,
            skip_walksheds=args.skip_walksheds,
            force_step=args.force_step,
            dataset_id_override=args.dataset_id,
        )
        progress[args.city] = {"status": status}
        save_progress(progress)
        print(f"\n{'='*60}")
        print(f"  DONE: {args.city} → {status}")
        print(f"{'='*60}\n")
    except Exception as exc:
        progress[args.city] = {"status": "failed", "error": str(exc)}
        save_progress(progress)
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
