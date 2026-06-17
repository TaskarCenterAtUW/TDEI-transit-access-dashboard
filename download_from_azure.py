"""
Download pipeline data from Azure Blob Storage to the local data/ folder.

The dashboard HTML reads data directly from Azure, so you do NOT need to run
this just to view the maps. Use it only when you want the large data files
locally — e.g. to re-run pipeline steps offline or develop without internet.

Usage:
    python3 download_from_azure.py --city seattle           # one city by slug
    python3 download_from_azure.py --dataset <uuid>         # one dataset by id
    python3 download_from_azure.py --bounds                 # jurisdiction_bounds/ only
    python3 download_from_azure.py --all                    # everything (5-10 GB!)
    python3 download_from_azure.py --city seattle --dry-run # preview only

Reads credentials from .env (AZURE_STORAGE_CONNECTION_STRING, AZURE_CONTAINER_NAME).
The container is publicly readable, so anonymous download also works if you set
AZURE_ACCOUNT_URL instead of a connection string.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

CONN_STR    = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
ACCOUNT_URL = os.environ.get("AZURE_ACCOUNT_URL")  # e.g. https://transitamenities.blob.core.windows.net
CONTAINER   = os.environ.get("AZURE_CONTAINER_NAME", "walksheds")
REPO_ROOT   = Path(__file__).parent
MANIFEST    = REPO_ROOT / "cities" / "processed_cities.json"


def get_container_client():
    if CONN_STR:
        client = BlobServiceClient.from_connection_string(CONN_STR)
    elif ACCOUNT_URL:
        # Anonymous access (container is public)
        client = BlobServiceClient(account_url=ACCOUNT_URL)
    else:
        sys.exit("ERROR: Set AZURE_STORAGE_CONNECTION_STRING or AZURE_ACCOUNT_URL in your .env file.")
    return client.get_container_client(CONTAINER)


def resolve_dataset_id(city_slug: str) -> str:
    if not MANIFEST.exists():
        sys.exit("ERROR: cities/processed_cities.json not found — cannot resolve city slug.")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entry = manifest.get(city_slug)
    if not entry:
        sys.exit(f"ERROR: '{city_slug}' not found in processed_cities.json.")
    return entry["dataset_id"]


def download_prefix(container_client, prefix: str, dry_run: bool) -> int:
    count = 0
    for blob in container_client.list_blobs(name_starts_with=prefix):
        dest = REPO_ROOT / blob.name
        if dry_run:
            print(f"  [dry-run] {blob.name}")
            count += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            f.write(container_client.download_blob(blob.name).readall())
        print(f"  downloaded: {blob.name}")
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="Download pipeline data from Azure Blob Storage")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--city", metavar="SLUG", help="Download one city's data by slug (e.g. seattle)")
    group.add_argument("--dataset", metavar="UUID", help="Download one dataset folder by id")
    group.add_argument("--bounds", action="store_true", help="Download jurisdiction_bounds/ only")
    group.add_argument("--all", action="store_true", help="Download EVERYTHING (5-10 GB)")
    parser.add_argument("--dry-run", action="store_true", help="List what would be downloaded without downloading")
    args = parser.parse_args()

    container_client = get_container_client()

    total = 0
    if args.bounds:
        print("[jurisdiction_bounds]")
        total += download_prefix(container_client, "jurisdiction_bounds/", args.dry_run)
    elif args.all:
        print("[all blobs]")
        total += download_prefix(container_client, "", args.dry_run)
    else:
        dataset_id = args.dataset or resolve_dataset_id(args.city)
        print(f"[{dataset_id}]")
        total += download_prefix(container_client, f"data/{dataset_id}/", args.dry_run)
        # Also grab the city boundary if we know the city
        if args.city:
            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
            boundary = manifest[args.city].get("boundary")
            if boundary:
                total += download_prefix(container_client, f"jurisdiction_bounds/{boundary}", args.dry_run)

    print(f"\n{'[dry-run] Would download' if args.dry_run else 'Downloaded'} {total} files from {CONTAINER}.")


if __name__ == "__main__":
    main()
