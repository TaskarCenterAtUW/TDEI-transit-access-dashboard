# Hosting & Data Storage

This dashboard is split into two parts:

1. **Static site** — the HTML/CSS/JS pages (plus small CSV/JSON files). These live
   in this Git repository and can be served by any static web host.
2. **Large data** — per-stop walkshed GeoJSONs, metrics CSVs, and city boundary
   files (~13 GB). These live in **Azure Blob Storage**, not in Git.

The HTML pages fetch the large data directly from Azure at runtime, so a fresh
clone of this repo produces a fully working dashboard **without** downloading any
of the big data files.

---

## Architecture

```
   ┌─────────────────────────────┐        ┌──────────────────────────────────┐
   │  Static site (this repo)     │        │  Azure Blob Storage              │
   │                              │        │  account: transitamenities       │
   │  statewide.html              │        │  container: walksheds (public)   │
   │  cities/*.html               │ fetch  │                                  │
   │  cities/index.html           │ ─────► │  data/<uuid>/data/stops/         │
   │  route_subsets/*.csv         │  (GET, │  data/<uuid>/data/walkshed_*/    │
   │  WA Bus Routes with score.csv│   CORS)│  data/<uuid>/data/metrics/       │
   │  cities/processed_cities.json│        │  jurisdiction_bounds/*.geojson   │
   └─────────────────────────────┘        └──────────────────────────────────┘
        served by VM / nginx /                  uploaded by the pipeline
        Azure $web / GitHub Pages               operator via upload_to_azure.py
```

### What lives where

| Data | Size | Location | Referenced by |
|---|---|---|---|
| `data/<uuid>/data/...` (walksheds, stops, metrics) | ~13 GB | Azure | `DATA_BASE` in HTML |
| `jurisdiction_bounds/*.geojson` (city boundaries) | ~18 MB | Azure | `DATA_BASE` in HTML |
| `route_subsets/*.csv` | ~4 MB | Git (served with site) | relative path |
| `WA Bus Routes with score.csv` | ~4 MB | Git (served with site) | relative path |
| `cities/processed_cities.json` | ~50 KB | Git (served with site) | relative path |

The HTML references the Azure data through a single constant:

```js
const DATA_BASE = 'https://transitamenities.blob.core.windows.net/walksheds';
```

This constant appears in `seattle-routes.html` (the template, which propagates to
every `cities/*.html` via `run_city_pipeline.py`) and in `statewide.html`. To
point the dashboard at a different storage account/container, change `DATA_BASE`
in those two places and re-run `python3 regenerate_city_html.py`.

---

## How data gets to Azure (pipeline operator)

The pipeline runs locally (or on a VM) and writes output to the local `data/`
folder. After a run, push the output to Azure:

```bash
# One-time setup: copy .env.example to .env and add the connection string
cp .env.example .env
# (edit .env — paste AZURE_STORAGE_CONNECTION_STRING)

pip install -r requirements.txt

# Upload everything (data/ + jurisdiction_bounds/)
python3 upload_to_azure.py

# Or just one city's dataset
python3 upload_to_azure.py --dataset <uuid>

# Or just the boundary files
python3 upload_to_azure.py --bounds-only

# Preview without uploading
python3 upload_to_azure.py --dry-run
```

The blob layout mirrors the local layout exactly (`data/<uuid>/data/...` and
`jurisdiction_bounds/...`), so the URLs the HTML builds always resolve.

### End-to-end flow

```
run_city_pipeline.py        →  writes data/<uuid>/data/... locally
upload_to_azure.py          →  pushes data/ + jurisdiction_bounds/ to Azure
git commit / deploy site    →  publishes HTML that reads from Azure
```

---

## Pulling data back down (optional)

You normally never need the data locally. But if you want to re-run pipeline
steps offline or develop without internet, pull it from Azure:

```bash
python3 download_from_azure.py --city seattle      # one city (+ its boundary)
python3 download_from_azure.py --bounds            # all boundary files
python3 download_from_azure.py --all               # everything (5-10 GB)
```

Because the container is public, you can download anonymously by setting
`AZURE_ACCOUNT_URL` in `.env` instead of the connection string.

---

## CORS

Because the HTML is served from a different origin than `*.blob.core.windows.net`,
the storage account must allow cross-origin GET requests. This is configured once
on the storage account (already done for `transitamenities`):

```python
from azure.storage.blob import BlobServiceClient, CorsRule
client = BlobServiceClient.from_connection_string(CONN_STR)
client.set_service_properties(cors=[CorsRule(
    allowed_origins=['*'],
    allowed_methods=['GET', 'HEAD', 'OPTIONS'],
    allowed_headers=['*'],
    exposed_headers=['*'],
    max_age_in_seconds=3600,
)])
```

To restrict access to a specific dashboard origin later, replace `['*']` in
`allowed_origins` with the deployed site's URL (e.g. `['https://transit.example.org']`).

---

## Deploying the static site

The site is plain static files, so any of these work:

- **VM + nginx** — clone the repo, point nginx at it. Simplest with the current setup.
- **Azure Blob static website** (`$web` container) — upload the HTML + small CSV/JSON
  files. If you go this route, the `route_subsets/`, `WA Bus Routes with score.csv`,
  and `cities/processed_cities.json` files must be uploaded alongside the HTML (they
  are currently served via relative paths).
- **GitHub Pages / any static host** — works the same way.

The large data does not move — it stays in the `walksheds` blob container and is
fetched cross-origin by the browser.
