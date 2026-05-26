#!/usr/bin/env bash
# Upload map-serving data to a Cloudflare R2 bucket.
#
# SETUP (one time):
#   1. In Cloudflare dashboard → R2 → Create bucket (e.g. "tdei-transit-data")
#   2. On the bucket → Settings → Public access → Allow Access → copy the public URL
#      It looks like: https://pub-<hash>.r2.dev
#      Paste that URL into DATA_BASE in the HTML maps (already marked with TODO).
#   3. Create an R2 API token: Cloudflare dashboard → R2 → Manage R2 API tokens
#      → Create API token → give it "Object Read & Write" on your bucket.
#   4. Configure the AWS CLI with those credentials:
#        aws configure --profile r2
#      Enter your R2 Access Key ID and Secret Access Key when prompted.
#      Leave region as "auto" and output as "json".
#
# USAGE:
#   bash upload_to_r2.sh
#
# Only the files the HTML map actually needs are uploaded (~326 MB for Seattle,
# much less for Yakima/Spokane). The 5.9 GB walkshed_geojson/ folder is excluded.

set -euo pipefail

# ── CONFIGURE THESE ──────────────────────────────────────────────────────────
ACCOUNT_ID="REPLACE_WITH_YOUR_CLOUDFLARE_ACCOUNT_ID"   # found in Cloudflare dashboard → right sidebar
BUCKET="tdei-transit-data"                              # your R2 bucket name
AWS_PROFILE="r2"                                        # profile name from `aws configure --profile r2`
# ─────────────────────────────────────────────────────────────────────────────

ENDPOINT="https://${ACCOUNT_ID}.r2.cloudflarestorage.com"
DATA_DIR="$(cd "$(dirname "$0")" && pwd)/data"

sync_folder() {
  local src="$1"
  local dest="s3://${BUCKET}/$2"
  if [ ! -d "$src" ]; then
    echo "  SKIPPED (folder not found): $src"
    return
  fi
  echo "  Uploading $src → $dest"
  aws s3 sync "$src" "$dest" \
    --endpoint-url "$ENDPOINT" \
    --profile "$AWS_PROFILE" \
    --no-progress
}

echo "=== Seattle (05776f25-f0f3-461c-ac34-4fa88a00936c) ==="
sync_folder "$DATA_DIR/05776f25-f0f3-461c-ac34-4fa88a00936c/data/metrics"                       "seattle/data/metrics"
sync_folder "$DATA_DIR/05776f25-f0f3-461c-ac34-4fa88a00936c/data/walkshed_edges_by_stop"        "seattle/data/walkshed_edges_by_stop"
sync_folder "$DATA_DIR/05776f25-f0f3-461c-ac34-4fa88a00936c/data/walkshed_edges_by_stop_wheelchair" "seattle/data/walkshed_edges_by_stop_wheelchair"

echo ""
echo "=== Yakima (95b532a7-cd6f-451b-8c5f-f78577427480) ==="
sync_folder "$DATA_DIR/95b532a7-cd6f-451b-8c5f-f78577427480/data/metrics"                "yakima/data/metrics"
sync_folder "$DATA_DIR/95b532a7-cd6f-451b-8c5f-f78577427480/data/walkshed_edges_by_stop" "yakima/data/walkshed_edges_by_stop"

echo ""
echo "=== Spokane (cbb2ed42-c77f-4218-96de-1b13eafa939f) ==="
sync_folder "$DATA_DIR/cbb2ed42-c77f-4218-96de-1b13eafa939f/data/metrics"                "spokane/data/metrics"
sync_folder "$DATA_DIR/cbb2ed42-c77f-4218-96de-1b13eafa939f/data/walkshed_edges_by_stop" "spokane/data/walkshed_edges_by_stop"

echo ""
echo "Done. Verify at: https://pub-<hash>.r2.dev/seattle/data/metrics/seattle_ped_amenity_counts.csv"
