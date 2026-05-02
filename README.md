# WA Transit & Amenities Dashboard

A MapLibre-based replica of the Tableau dashboard: transit routes and census-tract amenities for Washington state, with linked maps and filters.

## Run locally

Browsers block `fetch()` of local files, so serve the folder over HTTP:

```bash
cd "/Users/anyuhang/12th Internship/HTML transit map"
npx serve .
```

Then open **http://localhost:3000** (or the URL shown by `serve`).

## Yakima city subset map

- **`yakima-routes.html`** — simple map of **routes (lines)** and **stops (dots)** for the Yakima-area subset only; **Yakima city limits** as a low-opacity backdrop (`jurisdiction_bounds/Yakima_city_limits.geojson`). Click a stop for **purple walkshed network lines** (per-stop GeoJSON from `export_walkshed_edges_per_stop.py` → `walkshed_edges_by_stop/`), **walkshed amenity counts** in the sidebar, and **teal pins** from `…_amenity_locations.csv` (URLs in the HTML).
- Uses **`WA Bus Routes with score - Yakima city subset.csv`** in the same folder (serve via HTTP as above; open `/yakima-routes.html`).

## Data files

- **WA Bus Routes.csv** – stop-by-stop sequences (used to build route polylines)
- **WA Bus Routes with score - Yakima city subset.csv** – Yakima-area agencies/paths for `yakima-routes.html`
- **WA amenities.csv** – amenity counts and population per census tract
- **WA Census Tracts.geojson** – tract boundaries (~51MB; first load may take a few seconds)

## Features

- **Top map:** Transit routes (lines) and stops (visible on route hover; click route or stop to select)
- **Bottom map:** Census tracts colored by total amenities; click a tract to select
- **Selection:** Selecting a stop shows only that route path and the tract containing it; selecting a tract shows stops and route segments inside that tract
- **Detail panel:** Summary (county, geoid, population, amenities, stop counts) plus expandable amenity breakdown
- **Filters:** Transit agency, county, amenity ranges (sliders), and service frequency (15-min weekday, peak, night, weekend)
- **Viewport:** Both maps stay in sync; fitting to selection uses the larger of the two extents
