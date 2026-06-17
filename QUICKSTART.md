# Quickstart — From Git Clone to Working Dashboard

This guide walks a new contributor through everything needed to go from a fresh
clone of this repository (no large data files) to a fully working local dashboard,
and explains what to do if you also want to generate walkshed data for new cities.

> **The big picture:** the large data files live on **Azure Blob Storage**, and
> the HTML pages fetch them at runtime. So a fresh clone gives you a *fully
> working* dashboard — walksheds and amenities included — without downloading
> any data. See **[HOSTING.md](HOSTING.md)** for the hosting architecture.

---

## What's already in the repo

After cloning you will have:

| Present in repo | Description |
|---|---|
| `cities/*.html` | Pre-generated city map pages (~180 cities) |
| `cities/index.html` | Dynamic dashboard/index |
| `cities/jurisdictions.json` | Metadata for all WSP jurisdictions |
| `cities/processed_cities.json` | Metadata for cities with completed walkshed data |
| `statewide.html` | WA statewide overview map |
| `route_subsets/*.csv` | Route data for every processed city |
| `WA Bus Routes with score.csv` | All WA bus routes (used by statewide map) |
| `Jurisdiction Codes.csv` | TDEI dataset IDs and versions for all WA jurisdictions |
| `seattle-routes.html` | Template used to generate all city pages |
| All `*.py` scripts | Pipeline and utility scripts |

**Not in the repo (hosted on Azure Blob Storage instead):**

| Absent from repo | Where it lives | Why |
|---|---|---|
| `data/` | Azure `walksheds` container | Per-city walkshed GeoJSON, stops, metrics CSVs (~13 GB) |
| `jurisdiction_bounds/` | Azure `walksheds` container | City/county boundary files (~18 MB) |

The HTML fetches both from Azure at runtime, so you don't need them locally to
view the dashboard.

---

## Part 1 — View the existing dashboard (no pipeline needed)

The city pages and statewide map are already generated and committed, and they
read all data from Azure. You only need a local HTTP server because browsers
block `fetch()` of local files.

### 1. Serve the repo over HTTP

```bash
cd "path/to/HTML transit map"
npx serve .
```

> `npx` comes with Node.js — install from https://nodejs.org if you don't have it.
> No Python or pip install is needed just to view the dashboard.

Open **http://localhost:3000/cities** in your browser.

### 2. Navigate the dashboard

| URL | What you see |
|---|---|
| `http://localhost:3000/cities` | Index of all city maps with pipeline status |
| `http://localhost:3000/statewide.html` | Statewide WA route overview |
| `http://localhost:3000/cities/seattle.html` | Seattle city map (example) |

> Everything loads from Azure: click a stop and its walkshed edges + amenity
> markers appear; the blue city-boundary tint and stop dots are all live. If the
> map loads but data is missing, check the browser's Network tab for failed
> requests to `transitamenities.blob.core.windows.net` (usually a CORS or
> connectivity issue — see [HOSTING.md](HOSTING.md)).

---

## Part 2 — Run the pipeline for one city

This generates all walkshed and amenity data for a single city and adds it to
`cities/processed_cities.json`.

### Prerequisites

**Python dependencies:**

```bash
pip install -r requirements.txt
```

**TDEI credentials** — the walkshed API requires a TDEI account.
Export your credentials before running any pipeline command:

```bash
export TDEI_USERNAME='your_tdei_username'
export TDEI_PASSWORD='your_tdei_password'
```

You can add these to your shell profile (`~/.zshrc` or `~/.bashrc`) so you
don't need to re-export them every session. (You can also put them in `.env` —
see `.env.example`.)

### Run a single city

```bash
# Small city (< 200 stops) — runs in one shot
python3 run_city_pipeline.py --city WSP_Aberdeen_City

# Large city — use batches to avoid memory issues
python3 run_city_pipeline.py --city WSP_Seattle_City --batch-size 500

# Skip walkshed API calls (regenerate HTML/metrics from existing data only)
python3 run_city_pipeline.py --city WSP_Aberdeen_City --skip-walksheds
```

The script skips any step whose output already exists, so it is safe to re-run
after interruptions. Step completion is tracked in `pipeline_progress.json`.

**What the pipeline does (in order):**

1. Subsets `WA Bus Routes with score.csv` to stops inside the city boundary
2. Builds `data/<dataset_id>/data/stops/<city>_bus_stops.geojson`
3. Calls the TDEI Walkshed API — pedestrian profile (batched)
4. Splits combined walkshed into one file per stop → `walkshed_edges_by_stop/`
5. Calls the TDEI Walkshed API — wheelchair profile (batched)
6. Splits combined walkshed into one file per stop → `walkshed_edges_by_stop_wheelchair/`
7. Queries OSM Overpass API for amenities in the city's bbox
8. Counts amenities reachable from each stop — pedestrian
9. Counts amenities reachable from each stop — wheelchair
10. Generates `cities/<slug>.html` from the `seattle-routes.html` template
11. Updates `cities/processed_cities.json` and `pipeline_progress.json`

---

## Part 3 — Run the pipeline for all cities

> ⚠️ Full runtime is **24+ hours**. Run on a server or leave a machine
> running unattended. Progress is saved after each city so you can safely
> interrupt and resume.

```bash
# Run all ~250 jurisdictions (skips _UI urban-interface entries by default)
python3 batch_all_cities.py

# Retry only previously failed cities
python3 batch_all_cities.py --retry-failed

# Dry run — print what would be processed without doing anything
python3 batch_all_cities.py --dry-run

# Test with a single city before committing to a full run
python3 batch_all_cities.py --filter Aberdeen
```

`pipeline_progress.json` records the status of every city
(`completed`, `failed`, `skipped`, `no_stops`, etc.). Cities with a terminal
status are not reprocessed unless you edit that file or use `--retry-failed`.

---

## Part 4 — Publish data to Azure

The pipeline writes data to your local `data/` folder, but the live dashboard
reads from Azure Blob Storage. After a pipeline run, push the new data up.

### One-time setup

```bash
cp .env.example .env
# Edit .env and paste your AZURE_STORAGE_CONNECTION_STRING
pip install -r requirements.txt
```

### Upload

```bash
python3 upload_to_azure.py                  # data/ + jurisdiction_bounds/
python3 upload_to_azure.py --dataset <uuid> # one city's dataset only
python3 upload_to_azure.py --bounds-only    # boundary files only
python3 upload_to_azure.py --dry-run        # preview without uploading
```

The blob layout mirrors the local layout, so the URLs the HTML builds resolve
automatically. New uploads overwrite existing blobs of the same name.

### Pulling data back down (optional)

You don't need data locally to view the dashboard, but if you want it for
offline pipeline work:

```bash
python3 download_from_azure.py --city seattle   # one city (+ its boundary)
python3 download_from_azure.py --bounds         # all boundary files
python3 download_from_azure.py --all            # everything (5-10 GB)
```

See **[HOSTING.md](HOSTING.md)** for the full architecture, CORS setup, and how
to point the dashboard at a different storage account.

---

## Part 5 — Regenerate city HTML pages

If you change `seattle-routes.html` (the template) and want all 180+ city
pages to pick up the change without re-running the full pipeline:

```bash
python3 regenerate_city_html.py          # all processed cities
python3 regenerate_city_html.py auburn   # one city only
```

This reads `cities/processed_cities.json` and rewrites `cities/<slug>.html`
for each entry. Takes a few seconds.

> **Tip:** if you change the Azure storage location, update `DATA_BASE` in
> `seattle-routes.html` and `statewide.html`, then run this to roll the change
> out to every city page.

---

## Part 6 — Rebuild the index

If you add or rename jurisdictions in `Jurisdiction Codes.csv`:

```bash
python3 build_index.py
```

This rewrites `cities/index.html` and `cities/jurisdictions.json`. The index
page fetches status from `pipeline_progress.json` at runtime (auto-refreshes
every 15 seconds), so you don't need to re-run `build_index.py` just because
more cities were processed.

---

## Quick reference — key files

| File | Purpose |
|---|---|
| `run_city_pipeline.py` | Full pipeline for one city — main orchestration script |
| `batch_all_cities.py` | Runs `run_city_pipeline.py` for every WA jurisdiction |
| `regenerate_city_html.py` | Rebuilds city HTML pages from the template without re-running the pipeline |
| `build_index.py` | Regenerates `cities/index.html` and `cities/jurisdictions.json` |
| `upload_to_azure.py` | Uploads `data/` + `jurisdiction_bounds/` to Azure Blob Storage |
| `download_from_azure.py` | Downloads data from Azure to local `data/` (optional) |
| `seattle-routes.html` | Master template for all city map pages |
| `run_walksheds_from_geojson.py` | Called by the pipeline — TDEI API walkshed generation |
| `export_walkshed_edges_per_stop.py` | Called by the pipeline — splits combined walkshed into per-stop files |
| `query_osm_pois.py` | Called by the pipeline — downloads OSM amenity data |
| `count_amenities_in_walksheds.py` | Called by the pipeline — counts reachable amenities per stop |
| `pipeline_progress.json` | Tracks processing status for every jurisdiction |
| `cities/processed_cities.json` | Metadata for cities with completed walkshed data (used by statewide map) |
| `Jurisdiction Codes.csv` | TDEI dataset IDs and versions for all WA jurisdictions |
| `jurisdiction_bounds/*.geojson` | City/county boundary polygons (322 files; hosted on Azure, not in repo) |
| `HOSTING.md` | Azure Blob Storage architecture, upload/download, CORS, deployment |
| `DATA_FOLDER_GUIDE.md` | Explains the structure of each `data/<dataset_id>/` folder |

---

## Environment variables

Set these in your shell or in a `.env` file (copy `.env.example` to `.env`).
The `.env` file is gitignored — never commit it.

| Variable | Required | Description |
|---|---|---|
| `AZURE_STORAGE_CONNECTION_STRING` | Yes (upload) | Connection string for the storage account holding the data |
| `AZURE_CONTAINER_NAME` | Optional | Blob container name (default `walksheds`) |
| `AZURE_ACCOUNT_URL` | Optional | For anonymous download instead of a connection string |
| `TDEI_USERNAME` | Yes (pipeline only) | Your TDEI portal username |
| `TDEI_PASSWORD` | Yes (pipeline only) | Your TDEI portal password |
| `TDEI_AUTH_TOKEN` | Optional | Pre-fetched auth token (skips login step) |
| `TDEI_BASE_URL` | Optional | Override TDEI API base URL (default is the production endpoint) |
| `OVERPASS_TARGET_TILE_AREA_KM2` | Optional | Target tile size for OSM queries (default 25 km²) |
| `OVERPASS_TILE_DELAY` | Optional | Seconds to wait between Overpass tile requests (default 2) |
