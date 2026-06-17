# WA Transit Accessibility Dashboard

An interactive map dashboard showing bus route service frequencies and
pedestrian/wheelchair walkshed accessibility for every city in Washington state.

Built with [MapLibre GL JS](https://maplibre.org/). All pages are fully static —
no backend server is required for end users.

The large data files (~13 GB of walkshed GeoJSONs, metrics, and boundaries) are
hosted on **Azure Blob Storage**, not in this repo. The HTML pages fetch them at
runtime, so a fresh clone produces a fully working dashboard with no data download
required. See **[HOSTING.md](HOSTING.md)** for the architecture.

---

## What's in this repo

### Maps

| File / folder | Description |
|---|---|
| `statewide.html` | WA statewide overview — all bus routes colored by service frequency, with processed-city boundaries and stop dots |
| `cities/index.html` | Dashboard index — card grid of all ~250 WA jurisdictions with live pipeline status |
| `cities/<slug>.html` | Per-city map (e.g. `cities/seattle.html`) — routes, stops, pedestrian and wheelchair walkshed edges, and OSM amenity counts |
| `seattle-routes.html` | Master template that all city pages are generated from |
| `yakima-routes.html` | Standalone Yakima map (older prototype, kept for reference) |
| `spokane-routes.html` | Standalone Spokane map (older prototype, kept for reference) |

### Data files (in repo)

| File / folder | Description |
|---|---|
| `WA Bus Routes with score.csv` | All WA bus routes with stop sequences and service-frequency columns |
| `route_subsets/` | Per-city subsets of the routes CSV (one file per processed city) |
| `Jurisdiction Codes.csv` | TDEI dataset IDs and versions for all WA jurisdictions |
| `cities/jurisdictions.json` | Metadata for all jurisdictions (display name, slug, type, version) |
| `cities/processed_cities.json` | Metadata for cities with completed walkshed data; used by the statewide map |
| `pipeline_progress.json` | Per-jurisdiction pipeline status tracking |

### Data files (on Azure Blob Storage, not in repo)

| File / folder | Description |
|---|---|
| `data/<dataset_id>/data/` | Per-city walkshed GeoJSONs, stops, and metrics CSVs (~13 GB) |
| `jurisdiction_bounds/` | City and county boundary GeoJSON files (322 jurisdictions, ~18 MB) |

These are fetched by the HTML at runtime from the `walksheds` container. See
**[HOSTING.md](HOSTING.md)** for upload/download and configuration details.

### Pipeline scripts

| Script | What it does |
|---|---|
| `run_city_pipeline.py` | Runs the full 11-step pipeline for one city |
| `batch_all_cities.py` | Runs `run_city_pipeline.py` for every WA jurisdiction, resumably |
| `regenerate_city_html.py` | Rebuilds all city HTML pages from the template (no pipeline re-run needed) |
| `build_index.py` | Regenerates `cities/index.html` and `cities/jurisdictions.json` |
| `run_walksheds_from_geojson.py` | TDEI Walkshed API — generates reachable network from bus stop points |
| `export_walkshed_edges_per_stop.py` | Splits city-wide combined walkshed into one file per stop |
| `query_osm_pois.py` | Downloads OSM amenity data within the city's walkshed bounding box |
| `count_amenities_in_walksheds.py` | Counts reachable amenities per stop via spatial join |
| `upload_to_azure.py` | Uploads `data/` and `jurisdiction_bounds/` to Azure Blob Storage |
| `download_from_azure.py` | Downloads data from Azure to local `data/` (optional, for offline work) |

### Utility / one-time scripts

These were used to build or augment the `WA Bus Routes with score.csv` file and
are not part of the regular pipeline run:

`add_access_score.py`, `add_essentials_columns.py`, `add_population_served.py`,
`add_route_score.py`, `add_transit_score.py`, `build_jurisdiction_geojson.py`,
`create_simplified_routes.py`, `fix_king_county_names.py`, `route_score_to_labels.py`

---

## Running locally

Browsers block `fetch()` of local files, so serve the repo over HTTP:

```bash
cd "path/to/HTML transit map"
npx serve .
```

Then open **http://localhost:3000/cities** for the dashboard,
or **http://localhost:3000/statewide.html** for the statewide map.

> Everything works out of the box — walkshed edges (shown when you click a stop),
> amenity counts, and city boundaries are all fetched from Azure Blob Storage. You
> do **not** need the `data/` folder locally just to view the dashboard.

---

## Hosting & data storage

The static site (this repo) and the large data (Azure Blob Storage) are
deployed separately. See **[HOSTING.md](HOSTING.md)** for the full architecture,
the upload/download scripts, CORS configuration, and deployment options.

Quick reference:

```bash
cp .env.example .env            # then paste your Azure connection string
pip install -r requirements.txt

python3 upload_to_azure.py      # push local data/ + bounds to Azure
python3 download_from_azure.py --city seattle   # pull one city back down
```

---

## Generating walkshed data

See **[QUICKSTART.md](QUICKSTART.md)** for full step-by-step instructions
covering:

- Running the pipeline for a single city
- Running the pipeline for all ~250 WA jurisdictions
- Regenerating HTML pages after template changes
- Required environment variables (TDEI credentials)

See **[DATA_FOLDER_GUIDE.md](DATA_FOLDER_GUIDE.md)** for a detailed description
of every file and subfolder produced under `data/<dataset_id>/`.

---

## Map features (per-city pages)

- **Route lines** — colored by each route's GTFS identity color
- **Stop dots** — green when the stop meets all selected frequency standards, grey otherwise
- **Service-frequency filter** — multi-select checkboxes: Weekday peak, Weekday midday, Weeknight, Weekend (AND logic)
- **Pedestrian / wheelchair toggle** — switches walkshed edges and amenity counts between profiles
- **Click a stop** — draws the walkshed network, shows reachable amenity counts by type, displays the stop's full 4-period service profile
- **Click a route** — shows per-period frequency bars (how many stops on that route meet each standard)
- **City boundary overlay** — low-opacity fill showing the jurisdiction extent

## Map features (statewide page)

- All WA bus routes; same service-frequency filter (routes turn green when meeting all checked standards)
- Processed-city boundary overlays with clickable cards linking to full city maps
