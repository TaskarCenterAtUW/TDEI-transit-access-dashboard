"""
Upload pipeline output files to Azure Blob Storage.

The "walksheds" container is publicly readable, so the dashboard HTML pages
can fetch GeoJSON and CSV files directly from the browser.

Usage:
    python3 upload_to_azure.py                        # upload data/ + jurisdiction_bounds/
    python3 upload_to_azure.py --dataset <uuid>       # one dataset folder only
    python3 upload_to_azure.py --bounds-only          # only jurisdiction_bounds/
    python3 upload_to_azure.py --dry-run              # list what would be uploaded

Reads credentials from .env (AZURE_STORAGE_CONNECTION_STRING, AZURE_CONTAINER_NAME).
"""

import argparse
import os
import sys
from pathlib import Path

from azure.storage.blob import BlobServiceClient, ContentSettings
from dotenv import load_dotenv

load_dotenv()

CONN_STR   = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER  = os.environ.get("AZURE_CONTAINER_NAME", "walksheds")
REPO_ROOT  = Path(__file__).parent

# Subfolders inside each data/<uuid>/data/ that we want to upload.
# overpass_tile_cache and walkshed_geojson (combined files) are skipped —
# the dashboard only needs the per-stop split files.
UPLOAD_SUBDIRS = [
    "stops",
    "walkshed_edges_by_stop",
    "walkshed_edges_by_stop_wheelchair",
    "metrics",
]

CONTENT_TYPES = {
    ".geojson": "application/geo+json",
    ".json":    "application/json",
    ".csv":     "text/csv",
}


def get_content_settings(path: Path) -> ContentSettings:
    ct = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return ContentSettings(content_type=ct)


def upload_file(container_client, local_path: Path, blob_name: str, dry_run: bool):
    if dry_run:
        print(f"  [dry-run] {blob_name}")
        return
    with open(local_path, "rb") as f:
        container_client.upload_blob(
            name=blob_name,
            data=f,
            overwrite=True,
            content_settings=get_content_settings(local_path),
        )
    print(f"  uploaded: {blob_name}")


def upload_dataset(container_client, dataset_id: str, dry_run: bool):
    dataset_root = REPO_ROOT / "data" / dataset_id / "data"
    if not dataset_root.exists():
        print(f"  [skip] data/{dataset_id}/data/ not found")
        return 0
    count = 0
    for subdir in UPLOAD_SUBDIRS:
        folder = dataset_root / subdir
        if not folder.exists():
            continue
        for f in sorted(folder.iterdir()):
            if f.is_file():
                # Blob path mirrors local layout: data/<uuid>/data/<subdir>/<file>
                blob_name = f"data/{dataset_id}/data/{subdir}/{f.name}"
                upload_file(container_client, f, blob_name, dry_run)
                count += 1
    return count


def upload_bounds(container_client, dry_run: bool):
    """Upload jurisdiction_bounds/ (city boundary GeoJSONs) to the blob container."""
    bounds_root = REPO_ROOT / "jurisdiction_bounds"
    if not bounds_root.exists():
        print("  [skip] jurisdiction_bounds/ not found")
        return 0
    count = 0
    for f in sorted(bounds_root.iterdir()):
        if f.is_file():
            blob_name = f"jurisdiction_bounds/{f.name}"
            upload_file(container_client, f, blob_name, dry_run)
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="Upload pipeline output to Azure Blob Storage")
    parser.add_argument("--dataset", metavar="UUID", help="Upload a single dataset folder only")
    parser.add_argument("--bounds-only", action="store_true", help="Only upload jurisdiction_bounds/")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be uploaded without uploading")
    args = parser.parse_args()

    if not CONN_STR:
        sys.exit("ERROR: AZURE_STORAGE_CONNECTION_STRING not set. Add it to your .env file.")

    client = BlobServiceClient.from_connection_string(CONN_STR)
    container_client = client.get_container_client(CONTAINER)

    # Verify the container exists
    if not container_client.exists():
        sys.exit(f"ERROR: Container '{CONTAINER}' does not exist in the storage account.")

    total = 0

    if args.bounds_only:
        print("\n[jurisdiction_bounds]")
        total += upload_bounds(container_client, dry_run=args.dry_run)
        print(f"\n{'[dry-run] Would upload' if args.dry_run else 'Uploaded'} {total} files to {CONTAINER}.")
        return

    if args.dataset:
        dataset_ids = [args.dataset]
    else:
        data_root = REPO_ROOT / "data"
        if not data_root.exists():
            sys.exit("ERROR: No data/ folder found. Run the pipeline first.")
        dataset_ids = sorted(d.name for d in data_root.iterdir() if d.is_dir())

    for dataset_id in dataset_ids:
        print(f"\n[{dataset_id}]")
        total += upload_dataset(container_client, dataset_id, dry_run=args.dry_run)

    # Always include boundaries on a full run (unless targeting one dataset)
    if not args.dataset:
        print("\n[jurisdiction_bounds]")
        total += upload_bounds(container_client, dry_run=args.dry_run)

    print(f"\n{'[dry-run] Would upload' if args.dry_run else 'Uploaded'} {total} files to {CONTAINER}.")


if __name__ == "__main__":
    main()
