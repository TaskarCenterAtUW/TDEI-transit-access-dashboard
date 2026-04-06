# 3. This code extracts the POIs from each edges file
#
# Large walkshed bbox: Overpass is queried on a GRID of sub-bboxes (same full extent),
# results merged and deduped by (type, id). Tune with env:
#   OVERPASS_GRID_COLS, OVERPASS_GRID_ROWS (default 4x4 = 16 tiles)
#   OVERPASS_TILE_DELAY seconds between tiles (default 2)
#   OVERPASS_TIMEOUT per-query seconds in query string (default 180)
#   OVERPASS_URL single interpreter URL, or default mirrors in query_overpass_api
#   OVERPASS_CLEAR_TILE_CACHE=1 — delete tile cache before run (fresh Overpass)
#
# Tile cache: data/<dataset>/data/overpass_tile_cache/manifest.json + tile_XXXX.json
# If a tile fails, re-run the same command; completed tiles load from disk and only missing tiles hit Overpass.

import json
import os
import shutil
import requests
import geopandas as gpd
import csv
import time

BASE_PATH=os.path.join(os.getcwd(), "data")
PROCESSED_LOG_PATH = f"{BASE_PATH}/processed_amenities_folders.txt"

def load_processed_folders():
    if os.path.exists(PROCESSED_LOG_PATH):
        with open(PROCESSED_LOG_PATH, "r") as f:
            return set(line.strip() for line in f.readlines())
    return set()

def save_processed_folder(folder_name):
    with open(PROCESSED_LOG_PATH, "a") as f:
        f.write(folder_name + "\n")

# Parses the GeoJSON file to get the bounding box coordinates.
def get_bounding_box(geojson_file):
    gdf = gpd.read_file(geojson_file)
    bounds = gdf.total_bounds
    return bounds

def build_overpass_query(bounds):
    # Constructs an Overpass QL query to retrieve specified amenities.
    minx, miny, maxx, maxy = bounds
    amenity_tags = [
        "community_centre", "day_care_center", "place_of_worship", "emergency_shelter", "food_bank", 
        "library", "hospital", "residential_treatment_center", "work_source_site", "fed_qualified_health_center",
        "ffqhc_tribal", "fqhc_tribal", "college", "shopping_center", "apprentice_program", 
        "accessibility_disability_assistance", "wic_clinic", "wic_vendor", "farmers_market", 
        "middle_or_high_school", "elementary_school", "other_school", "municipal_services", 
        "orca_lift_enrollment_center", "housing_entry_point", "senior_center", "grocery_store", 
        "election_drop_box", "nursing_home", "assisted_living_facility", "orca_tvm", 
        "orca_fare_outlet", "accessibility_disability_assistance", "residential_treatment_centers", 
        "social_facility", "school", "polling_station", "doctors", "clinic"
    ]
    # Keep in sync with filter_amenities additional_tags below (shop=supermarket, healthcare=*)
    additional_tags = {
        "shop": ["supermarket"],
        "healthcare": ["*"],
    }

    # Construct query parts
    amenity_query = " || ".join([f't["amenity"] == "{amenity}"' for amenity in amenity_tags])
    additional_query_parts = []
    for key, values in additional_tags.items():
        for value in values:
            if value == "*":
                additional_query_parts.append(f't["{key}"]')
            else:
                additional_query_parts.append(f't["{key}"] == "{value}"')
    
    additional_query = " || ".join(additional_query_parts)
    
    # [timeout:N] asks the server for a longer run (seconds). Helps reduce 504 on big areas.
    overpass_timeout = int(os.getenv("OVERPASS_TIMEOUT", "180"))
    # Combine into the final Overpass query
    query = f"""
    [out:json][timeout:{overpass_timeout}];
    (
      node(if:({amenity_query} || {additional_query}))({miny},{minx},{maxy},{maxx});
      way(if:({amenity_query} || {additional_query}))({miny},{minx},{maxy},{maxx});
      relation(if:({amenity_query} || {additional_query}))({miny},{minx},{maxy},{maxx});
    );
    out body;
    """
    return query

# Default mirrors — rotate on 502/503/504. Override with OVERPASS_URL (single URL).
DEFAULT_OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def query_overpass_api(query, tries_per_url=4):
    """POST query to Overpass; retry with backoff and alternate mirrors on timeout errors."""
    urls = (
        [os.getenv("OVERPASS_URL").strip()]
        if os.getenv("OVERPASS_URL")
        else DEFAULT_OVERPASS_URLS
    )
    urls = [u for u in urls if u]

    attempt = 0
    for url in urls:
        for _ in range(tries_per_url):
            attempt += 1
            print(f"Fetching Overpass ({url}) attempt {attempt}...")
            try:
                response = requests.post(
                    url,
                    data={"data": query},
                    timeout=(30, 600),
                )
            except requests.RequestException as e:
                print(f"  Request error: {e}")
                time.sleep(min(15 + 5 * _, 90))
                continue

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    print("  Invalid JSON in response")
            else:
                snippet = (response.text or "")[:300].replace("\n", " ")
                print(f"  HTTP {response.status_code}: {snippet}")

            # 429/502/503/504: wait and retry (server busy / timeout)
            if response.status_code in (429, 502, 503, 504):
                wait = min(30 + 20 * _, 120)
                print(f"  Waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                time.sleep(10)

    print("Overpass: all URLs and retries exhausted.")
    return None

def filter_amenities(data, amenities_list, additional_tags):
    """
    Filters the results for the specified amenities and additional tags.
    Adds non-amenity feature types (e.g., bus_stop, station) to the amenity column.
    """
    filtered = []
    for element in data.get("elements", []):
        if 'tags' in element:
            tags = element['tags']
            
            # Check if the element matches an amenity
            if 'amenity' in tags and tags['amenity'] in amenities_list:
                filtered.append(element)
            else:
                # Check if the element matches an additional tag
                for key, values in additional_tags.items():
                    if key in tags:
                        if "*" in values or tags[key] in values:
                            if key == "healthcare":
                                tags['amenity'] = "healthcare"
                            else:
                                tags['amenity'] = tags[key]  # store the tag type in the 'amenity' column
                            filtered.append(element)
                            break
    return filtered

def get_node_coordinates(node_id):
    """Lat/lon for a way's first node via OSM API (plain requests; no Azure cache)."""
    api_url = f"https://api.openstreetmap.org/api/0.6/node/{node_id}.json"
    print(f"Fetching coordinates for node {node_id}...")
    try:
        response = requests.get(api_url, timeout=30)
        if response.status_code == 200:
            data = response.json()
            node = data["elements"][0]
            return node.get("lat", ""), node.get("lon", "")
        print(f"Failed to retrieve data for node {node_id}: {response.status_code}")
    except requests.RequestException as e:
        print(f"Request failed for node {node_id}: {e}")
    return "", ""

def _iter_edges_geojson_paths(folder_path):
    """BBox sources: direct children of folder_path and walkshed_geojson/ (combined_edges, etc.)."""
    search_roots = [folder_path, os.path.join(folder_path, "walkshed_geojson")]
    for root in search_roots:
        if not os.path.isdir(root):
            continue
        for file_name in os.listdir(root):
            if not file_name.endswith("edges.geojson"):
                continue
            if "incomplete.edges.geojson" in file_name:
                continue
            yield os.path.join(root, file_name)


def _pick_bbox_geojson_path(folder_path):
    """Pick bbox source: prefer pedestrian combined walkshed (full extent for integrity)."""
    paths = list(_iter_edges_geojson_paths(folder_path))
    if not paths:
        return None
    for p in paths:
        if "Unconstrained_Pedestrian" in p or "Sidewalks_Only" in p:
            return p
    return paths[0]


def _iter_bounds_tiles(minx, miny, maxx, maxy, n_cols, n_rows):
    """Yield (minx, miny, maxx, maxy) for each grid cell covering the bbox."""
    dx = (maxx - minx) / n_cols
    dy = (maxy - miny) / n_rows
    for i in range(n_cols):
        for j in range(n_rows):
            x0 = minx + i * dx
            y0 = miny + j * dy
            x1 = minx + (i + 1) * dx
            y1 = miny + (j + 1) * dy
            yield (x0, y0, x1, y1)


def _element_key(el):
    return (el.get("type"), el.get("id"))


def _read_tile_manifest(manifest_path):
    if not os.path.isfile(manifest_path):
        return None
    try:
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _manifest_matches(manifest, bounds, n_cols, n_rows, n_tiles):
    if not manifest or manifest.get("schema_version") != 1:
        return False
    eps = 1e-6
    minx, miny, maxx, maxy = bounds
    try:
        return (
            abs(manifest["minx"] - minx) < eps
            and abs(manifest["miny"] - miny) < eps
            and abs(manifest["maxx"] - maxx) < eps
            and abs(manifest["maxy"] - maxy) < eps
            and int(manifest["n_cols"]) == n_cols
            and int(manifest["n_rows"]) == n_rows
            and int(manifest.get("n_tiles", -1)) == n_tiles
        )
    except (KeyError, TypeError, ValueError):
        return False


def _write_tile_manifest(manifest_path, bounds, n_cols, n_rows, n_tiles, complete=False):
    minx, miny, maxx, maxy = bounds
    payload = {
        "schema_version": 1,
        "minx": minx,
        "miny": miny,
        "maxx": maxx,
        "maxy": maxy,
        "n_cols": n_cols,
        "n_rows": n_rows,
        "n_tiles": n_tiles,
        "complete": complete,
    }
    os.makedirs(os.path.dirname(manifest_path) or ".", exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def query_overpass_tiled_merged(bounds, cache_dir=None):
    """
    Split the full bounding box into a grid of smaller bboxes, query Overpass per tile,
    merge elements and dedupe by (type, id). Preserves coverage of the full walkshed area
    while avoiding single huge queries that 504.

    If cache_dir is set, each successful tile is saved as tile_XXXX.json; re-runs skip cached
    tiles until all succeed, then merge. manifest.json records bbox + grid (must match or cache is cleared).
    """
    minx, miny, maxx, maxy = bounds
    n_cols = max(1, int(os.getenv("OVERPASS_GRID_COLS", "6")))
    n_rows = max(1, int(os.getenv("OVERPASS_GRID_ROWS", "6")))
    delay = float(os.getenv("OVERPASS_TILE_DELAY", "2"))

    tiles = list(_iter_bounds_tiles(minx, miny, maxx, maxy, n_cols, n_rows))
    n_tiles = len(tiles)
    print(
        f"Tiling Overpass: {n_cols}x{n_rows} = {n_tiles} tiles over bbox "
        f"[{minx:.5f},{miny:.5f},{maxx:.5f},{maxy:.5f}]"
    )

    manifest_path = None
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        manifest_path = os.path.join(cache_dir, "manifest.json")
        manifest = _read_tile_manifest(manifest_path)
        if manifest and not _manifest_matches(manifest, bounds, n_cols, n_rows, n_tiles):
            print(
                "Tile cache bbox/grid mismatch — clearing cached tiles "
                "(change OVERPASS_GRID_* or bbox source, or set OVERPASS_CLEAR_TILE_CACHE=1)."
            )
            for name in os.listdir(cache_dir):
                os.remove(os.path.join(cache_dir, name))
            manifest = None
        if not manifest or not _manifest_matches(manifest, bounds, n_cols, n_rows, n_tiles):
            _write_tile_manifest(manifest_path, bounds, n_cols, n_rows, n_tiles, complete=False)

    seen = set()
    merged_elements = []
    cached_count = 0
    fetched_count = 0

    for idx, tile in enumerate(tiles):
        tx0, ty0, tx1, ty1 = tile
        query = build_overpass_query(tile)
        tile_path = os.path.join(cache_dir, f"tile_{idx:04d}.json") if cache_dir else None
        data = None

        if tile_path and os.path.isfile(tile_path):
            try:
                with open(tile_path, encoding="utf-8") as tf:
                    data = json.load(tf)
            except (json.JSONDecodeError, OSError) as e:
                print(f"  Tile {idx + 1}/{n_tiles} cache read failed ({e}), re-fetching...")
                data = None
            else:
                data = {"elements": data.get("elements", [])}

        if tile_path and os.path.isfile(tile_path) and data is not None:
            print(f"  Tile {idx + 1}/{n_tiles} {tile}... (from cache, {len(data.get('elements', []))} elements)")
            cached_count += 1
        else:
            print(f"  Tile {idx + 1}/{n_tiles} {tile}...")
            data = query_overpass_api(query)
            if data is None:
                print(
                    f"  Tile {idx + 1} failed after retries. Progress saved under {cache_dir or '(no cache)'}."
                    " Re-run the same command to resume."
                )
                return None
            fetched_count += 1
            if tile_path:
                try:
                    with open(tile_path, "w", encoding="utf-8") as tf:
                        json.dump({"elements": data.get("elements", [])}, tf)
                except OSError as e:
                    print(f"  Warning: could not write tile cache {tile_path}: {e}")

        for el in data.get("elements", []):
            key = _element_key(el)
            if key[0] is None or key[1] is None:
                continue
            if key in seen:
                continue
            seen.add(key)
            merged_elements.append(el)
        if idx < n_tiles - 1 and delay > 0:
            time.sleep(delay)

    if cache_dir and manifest_path:
        _write_tile_manifest(manifest_path, bounds, n_cols, n_rows, n_tiles, complete=True)

    print(
        f"Merged {len(merged_elements)} unique OSM elements from {n_tiles} tiles "
        f"({cached_count} from cache, {fetched_count} fetched)."
    )
    return {"elements": merged_elements}


def process_geojson_files_in_folder(folder_path):
    # Processes all GeoJSON files in the specified folder and saves filtered amenities to corresponding CSV files.
    # Create a new folder for the CSV files
    output_folder = os.path.join(folder_path, "csv_pois")

    if os.path.exists(output_folder):
        if len(os.listdir(output_folder)) > 0:
            print(f"Output folder {output_folder} already exists and has results. Skipping this dataset.")
            return

    os.makedirs(output_folder, exist_ok=True)

    geojson_file_path = _pick_bbox_geojson_path(folder_path)
    if not geojson_file_path:
        print(f"No *edges.geojson found under {folder_path} (or walkshed_geojson/). Skipping.")
        return

    # Get the name of the parent folder containing the 'data' folder
    parent_folder_name = os.path.basename(os.path.dirname(folder_path))
    csv_file_name = os.path.join(output_folder, f"{parent_folder_name}_filtered_amenities.csv")

    print(f"Using bbox from: {geojson_file_path}")

    # Step 1: Parse GeoJSON to get bounding box
    bounds = get_bounding_box(geojson_file_path)

    cache_dir = os.path.join(folder_path, "overpass_tile_cache")
    if os.getenv("OVERPASS_CLEAR_TILE_CACHE", "").strip().lower() in ("1", "true", "yes"):
        shutil.rmtree(cache_dir, ignore_errors=True)
        print(f"Cleared Overpass tile cache: {cache_dir}")

    # Step 2–3: Overpass — tiled merge (full bbox integrity, smaller per-request load; resume via cache_dir)
    data = query_overpass_tiled_merged(bounds, cache_dir=cache_dir)

    if data is None:
        exit(1)

    # Step 4: Filter for specific amenities (aligned with WA/TDEI-style amenity tags)
    amenities_list = [
        "community_centre", "day_care_center", "place_of_worship", "emergency_shelter", "food_bank",
        "library", "hospital", "residential_treatment_center", "work_source_site", "fed_qualified_health_center",
        "ffqhc_tribal", "fqhc_tribal", "college", "shopping_center", "apprentice_program",
        "accessibility_disability_assistance", "wic_clinic", "wic_vendor", "farmers_market",
        "middle_or_high_school", "elementary_school", "other_school", "municipal_services",
        "orca_lift_enrollment_center", "housing_entry_point", "senior_center", "grocery_store",
        "election_drop_box", "nursing_home", "assisted_living_facility", "orca_tvm",
        "orca_fare_outlet", "accessibility_disability_assistance", "residential_treatment_centers",
        "social_facility", "school", "polling_station", "doctors", "clinic",
    ]
    # OSM: supermarket often tagged shop=supermarket; generic healthcare as healthcare=*
    additional_tags = {
        "shop": ["supermarket"],
        "healthcare": ["*"],
    }
    filtered_data = filter_amenities(data, amenities_list, additional_tags)

    # Step 5: Save the filtered data to a CSV file
    with open(csv_file_name, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["type", "lat", "lon", "node_id", "name", "amenity"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()

        for element in filtered_data:
            lat, lon = "", ""

            if element["type"] == "way" and "nodes" in element:
                node_id = element["nodes"][0]
                lat, lon = get_node_coordinates(node_id)
                time.sleep(0.5)
            elif element["type"] == "node":
                lat = element.get("lat", "")
                lon = element.get("lon", "")

            name_clean = element["tags"].get("name", "").replace(",", " ")

            writer.writerow({
                "type": element["type"],
                "lat": lat,
                "lon": lon,
                "node_id": element["nodes"][0] if element["type"] == "way" and "nodes" in element else "",
                "name": name_clean,
                "amenity": element["tags"].get("amenity", ""),
            })

    print(f"Amenities saved to {csv_file_name}")

processed_folders = load_processed_folders()

for folder_name in os.listdir(f"{BASE_PATH}"):
    if folder_name in processed_folders:
        print(f"Skipping already processed folder: {folder_name}")
        continue

    folder_path = os.path.join(BASE_PATH, folder_name)
    if not os.path.isdir(folder_path):
        continue

    process_geojson_files_in_folder(f"{folder_path}/data")
    save_processed_folder(folder_name)

print("Done")
exit(0)