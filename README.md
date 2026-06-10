# WA Transit Accessibility Dashboard

An interactive map dashboard showing bus route service frequencies and
pedestrian/wheelchair walkshed accessibility for every city in Washington state.

Built with [MapLibre GL JS](https://maplibre.org/). All pages are fully static —
no backend server is required for end users.

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
| `jurisdiction_bounds/` | City and county boundary GeoJSON files (322 jurisdictions) |
| `Jurisdiction Codes.csv` | TDEI dataset IDs and versions for all WA jurisdictions |
| `cities/jurisdictions.json` | Metadata for all jurisdictions (display name, slug, type, version) |
| `cities/processed_cities.json` | Metadata for cities with completed walkshed data; used by the statewide map |
| `pipeline_progress.json` | Per-jurisdiction pipeline status tracking |

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

> City map pages load routes and stop dots immediately. The walkshed edges
> (shown when you click a stop) and amenity counts require the `data/` folder,
> which is not in the repo — see **QUICKSTART.md** for how to generate it.

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
