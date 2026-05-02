# Dataset Folder Guide

Each city processed by this pipeline generates a folder under `data/` named after its **TDEI OSW dataset ID**.  
Example for Seattle: `data/05776f25-f0f3-461c-ac34-4fa88a00936c/`

All generated files live inside the `data/` subfolder of that directory:

```
data/<dataset_id>/
└── data/
    ├── stops/
    ├── walkshed_geojson/
    ├── walkshed_edges_by_stop/
    ├── walkshed_edges_by_stop_wheelchair/
    ├── metrics/
    ├── csv_pois/
    └── overpass_tile_cache/
```

---

## `stops/`

**Created by:** `yakima_stops_to_geojson.py`

Contains one file:

| File | Description |
|------|-------------|
| `{city}_bus_stops.geojson` | GeoJSON FeatureCollection of all **unique bus stop locations** for the city. Each Feature is a Point with `stop_id`, `agency`, `name`, `lat`, `lon` properties. This is the primary input to the walkshed pipeline — one walkshed is generated per stop. |

> **Why this exists:** The GTFS/CSV route data lists the same stop many times across many routes. This script deduplicates them into a clean point file, one feature per physical stop location.

---

## `walkshed_geojson/`

**Created by:** `run_walksheds_from_geojson.py`

Contains the **city-wide walkshed edge networks** for each accessibility profile, both as intermediate batch files and final merged files.

| File pattern | Description |
|---|---|
| `{city}_{Profile}_combined_edges.geojson` | **Final merged file.** All walkshed edges for the entire city under a given profile, concatenated into one GeoJSON FeatureCollection. This is the primary file used by `query_osm_pois.py` as the bounding box source. |
| `{city}_{Profile}_combined_edges_batch{NNNN}_{MMMM}.geojson` | **Intermediate batch file.** Covers stops `NNNN` through `MMMM`. Generated when running the walkshed script in batches (e.g. 500 stops at a time for large cities). Safe to delete after the final merged file is confirmed. |

**Profiles present:**
- `Unconstrained_Pedestrian_(Sidewalks_Only)` — unrestricted walking, uses sidewalks
- `Manual_Wheelchair` — restricted by steep grades, missing curb cuts, and obstructions

> **Why this exists:** The TDEI Walkshed API returns the reachable street network from each stop. The combined file for the whole city is used to derive the bounding box for the OSM amenity query, ensuring OSM data is fetched for exactly the area that walkshed coverage covers.

---

## `walkshed_edges_by_stop/`

**Created by:** `run_walksheds_from_geojson.py`

Contains **one GeoJSON file per bus stop** for the **pedestrian** profile.

| File pattern | Description |
|---|---|
| `{Agency}_{stop_id}.geojson` | The reachable walking network (edges/paths) from that single stop, as returned by the TDEI Walkshed API. Contains LineString features representing walkable segments within the travel time budget (~10 minutes). |

Example: `Metro_Transit_22510.geojson`, `City_of_Seattle_1-26645.geojson`

> **Why this exists:** The HTML map loads the individual stop file when a user clicks a stop, drawing only that stop's walkshed on the map rather than loading the entire city-wide file. This keeps the map fast and interactive. There will be roughly one file per unique stop (~2,600+ for Seattle).

---

## `walkshed_edges_by_stop_wheelchair/`

**Created by:** `run_walksheds_from_geojson.py` (when run with the Manual Wheelchair profile)

Identical structure to `walkshed_edges_by_stop/`, but for the **Manual Wheelchair** profile.

| File pattern | Description |
|---|---|
| `{Agency}_{stop_id}.geojson` | The reachable wheelchair-accessible network from that single stop. Edges reflect routes that meet grade, curb cut, and surface requirements for a manual wheelchair user. |

> **Why this exists:** The HTML map's "Wheelchair" toggle loads files from this folder instead of `walkshed_edges_by_stop/`, allowing side-by-side comparison of pedestrian vs. wheelchair accessibility from the same stop.

---

## `metrics/`

**Created by:** `run_walksheds_from_geojson.py` (amenity counts) and `query_osm_pois.py` (amenity locations)

Contains summary statistics used directly by the HTML map.

| File | Columns | Description |
|------|---------|-------------|
| `{city}_ped_amenity_counts.csv` | `stop_id, agency, amenity_count, clinic, college, community_centre, doctors, food_bank, healthcare, hospital, library, nursing_home, place_of_worship, polling_station, school, social_facility, supermarket` | **Pedestrian profile.** One row per stop. Total count of reachable OSM amenities, plus a breakdown by category. Loaded by the HTML map to color-code stops and show bar charts. |
| `{city}_wc_amenity_counts.csv` | same columns | **Wheelchair profile.** Same structure as above but counts only amenities reachable under wheelchair constraints. |
| `{city}_ped_amenity_counts_amenity_locations.csv` | `stop_id, agency, lat, lon, name, amenity, osm_type` | **Pedestrian profile.** One row per (stop, amenity) pair. Lists every individual OSM amenity reachable from each stop. Used by the HTML map to place amenity markers when a stop is selected. |
| `{city}_wc_amenity_counts_amenity_locations.csv` | same columns | **Wheelchair profile.** Same as above for wheelchair-reachable amenities. |
| `{city}_metrics.csv` | `profile, uphill, downhill, avoidCurbs, streetAvoidance, max_cost, reverse, total_length, path_count, crossing_count, curb_count, marked_curbs, lowered_curbs` | **Summary infrastructure metrics** for the city's walkshed network by profile. Captures total path/edge lengths, crossing counts, curb statistics, and the profile parameters used. Useful for high-level accessibility reporting. |

---

## `csv_pois/`

**Created by:** `query_osm_pois.py`

| File | Columns | Description |
|------|---------|-------------|
| `{dataset_id}_filtered_amenities.csv` | `type, lat, lon, node_id, name, amenity` | All OSM amenity nodes/ways found within the city's walkshed bounding box, filtered to the relevant categories (hospitals, schools, supermarkets, parks, etc.). This is the raw OSM query result — it is then spatially joined against each stop's walkshed polygon to produce the per-stop counts in `metrics/`. |

> **Why the name uses the dataset ID:** `query_osm_pois.py` uses the parent folder name (the dataset ID) as the file prefix, since this folder can be reused across cities without naming collisions.

---

## `overpass_tile_cache/`

**Created by:** `query_osm_pois.py`

Contains cached tile responses from the OSM Overpass API. The bounding box of the city is divided into a grid of tiles and each tile's response is saved here as a JSON file so re-running the script doesn't re-fetch data already downloaded.

> Safe to delete if you want to force a fresh OSM query. The script will re-download and re-populate this folder automatically.

---

## Summary: What gets used by the HTML map

| File | Used for |
|------|----------|
| `stops/seattle_bus_stops.geojson` | Not loaded directly — used as input to pipeline scripts only |
| `walkshed_edges_by_stop/{Agency}_{id}.geojson` | Drawn on map when a stop is clicked (pedestrian walkshed) |
| `walkshed_edges_by_stop_wheelchair/{Agency}_{id}.geojson` | Drawn on map when a stop is clicked (wheelchair walkshed) |
| `metrics/seattle_ped_amenity_counts.csv` | Colors stops by amenity count; populates route-level totals |
| `metrics/seattle_wc_amenity_counts.csv` | Same, for wheelchair profile |
| `metrics/seattle_ped_amenity_counts_amenity_locations.csv` | Places individual amenity markers when stop is selected |
| `metrics/seattle_wc_amenity_counts_amenity_locations.csv` | Same, for wheelchair profile |
| `walkshed_geojson/*_combined_edges.geojson` | Not loaded by the map — only used during pipeline (OSM bbox) |
| `csv_pois/*_filtered_amenities.csv` | Not loaded by the map — intermediate pipeline data |
| `overpass_tile_cache/` | Not loaded by the map — pipeline cache only |
