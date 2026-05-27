#!/usr/bin/env python3
"""
Run run_city_pipeline.py for every jurisdiction in Jurisdiction Codes.csv,
using the highest-version dataset ID for each.

Progress is tracked in pipeline_progress.json — already-completed cities are
skipped automatically, so you can safely re-run this script after interruptions.

Usage:
  # Run all 320 jurisdictions sequentially
  python3 batch_all_cities.py

  # Run only cities whose names contain 'Aberdeen' (useful for testing)
  python3 batch_all_cities.py --filter Aberdeen

  # Skip walkshed API calls (e.g. to regenerate HTML from existing data)
  python3 batch_all_cities.py --skip-walksheds

  # Use 300 stops per walkshed batch (default 500)
  python3 batch_all_cities.py --batch-size 300

  # Re-run only cities that previously failed
  python3 batch_all_cities.py --retry-failed

  # Dry run: print the list of cities that would be processed
  python3 batch_all_cities.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JURISDICTION_CSV = ROOT / "Jurisdiction Codes.csv"
PROGRESS_FILE = ROOT / "pipeline_progress.json"


def load_highest_version_datasets() -> dict[str, tuple[float, str]]:
    """Return {wsp_name: (version, dataset_id)} keyed by highest-version entry."""
    best: dict[str, tuple[float, str]] = {}
    with JURISDICTION_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            uid, name, ver_str = row[0].strip(), row[1].strip(), row[2].strip()
            try:
                ver = float(ver_str)
            except ValueError:
                continue
            if name not in best or ver > best[name][0]:
                best[name] = (ver, uid)
    return best


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Batch-run run_city_pipeline.py for all WA jurisdictions."
    )
    ap.add_argument(
        "--filter",
        default=None,
        help="Only process jurisdictions whose WSP name contains this substring (case-insensitive)",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Stops per walkshed API batch (passed to run_city_pipeline.py, default 500)",
    )
    ap.add_argument(
        "--skip-walksheds",
        action="store_true",
        help="Pass --skip-walksheds to each city (skip TDEI API calls)",
    )
    ap.add_argument(
        "--retry-failed",
        action="store_true",
        help="Re-run cities that are recorded as 'failed' in pipeline_progress.json",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the list of cities that would be processed, then exit",
    )
    args = ap.parse_args()

    all_jurisdictions = load_highest_version_datasets()
    progress = load_progress()

    # Build ordered list of WSP names to process
    pending: list[str] = []
    skipped_done: list[str] = []

    for wsp_name in sorted(all_jurisdictions.keys()):
        # Apply --filter if specified
        if args.filter and args.filter.lower() not in wsp_name.lower():
            continue

        status = (progress.get(wsp_name) or {}).get("status")

        if status in ("completed", "no_stops", "no_boundary"):
            skipped_done.append(wsp_name)
            continue
        if status == "failed" and not args.retry_failed:
            skipped_done.append(wsp_name)
            continue

        pending.append(wsp_name)

    print(f"\nJurisdictions to process : {len(pending)}")
    print(f"Already done (skipped)   : {len(skipped_done)}")
    print()

    if args.dry_run:
        print("DRY RUN — cities that would be processed:")
        for name in pending:
            ver, uid = all_jurisdictions[name]
            print(f"  {name}  (v{ver}, {uid})")
        return

    if not pending:
        print("Nothing to do — all jurisdictions already processed.")
        print("Use --retry-failed to re-run failed ones, or delete entries from pipeline_progress.json.")
        return

    success_count = 0
    fail_count = 0
    no_stops_count = 0

    for i, wsp_name in enumerate(pending, 1):
        ver, uid = all_jurisdictions[wsp_name]
        print(f"\n[{i}/{len(pending)}] {wsp_name}  (v{ver})")

        cmd = [
            sys.executable,
            str(ROOT / "run_city_pipeline.py"),
            "--city", wsp_name,
            "--batch-size", str(args.batch_size),
        ]
        if args.skip_walksheds:
            cmd.append("--skip-walksheds")

        result = subprocess.run(cmd, cwd=ROOT)

        # Reload progress (run_city_pipeline.py writes it)
        progress = load_progress()
        status = (progress.get(wsp_name) or {}).get("status", "unknown")

        if result.returncode == 0:
            if status == "no_stops":
                no_stops_count += 1
            else:
                success_count += 1
        else:
            fail_count += 1
            print(f"  [FAILED] {wsp_name} — continuing with next city")

    print(f"\n{'='*60}")
    print(f"  Batch complete")
    print(f"  Completed  : {success_count}")
    print(f"  No stops   : {no_stops_count}")
    print(f"  Failed     : {fail_count}")
    print(f"  Total run  : {success_count + no_stops_count + fail_count}")
    print(f"{'='*60}")

    if fail_count == 0:
        print("\nAll cities processed. Running build_index.py...")
        subprocess.run([sys.executable, str(ROOT / "build_index.py")], cwd=ROOT)
    else:
        print(f"\n{fail_count} cities failed. Fix issues and re-run; "
              "completed cities will be skipped automatically.")
        print("Once all are done, run:  python3 build_index.py")


if __name__ == "__main__":
    main()
