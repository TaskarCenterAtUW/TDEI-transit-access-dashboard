#!/usr/bin/env python3
"""
Regenerate every processed city's HTML map from the seattle-routes.html template
without re-running any pipeline data steps.

Reads cities/processed_cities.json and rewrites cities/<slug>.html for each entry
using run_city_pipeline.generate_city_html. Use this after editing the template
(e.g. legend / styling / map logic changes) to roll the change out to all cities.

Usage:
  python3 regenerate_city_html.py            # all processed cities
  python3 regenerate_city_html.py auburn     # only the given slug(s)
"""
from __future__ import annotations

import json
import sys

from run_city_pipeline import (
    CITIES_DIR,
    PROCESSED_CITIES_MANIFEST,
    generate_city_html,
)


def main() -> None:
    only = set(sys.argv[1:])
    manifest = json.loads(PROCESSED_CITIES_MANIFEST.read_text(encoding="utf-8"))

    written, skipped = 0, 0
    for slug, meta in sorted(manifest.items()):
        if only and slug not in only:
            continue
        center = meta.get("center") or [None, None]
        try:
            html = generate_city_html(
                city_display=meta["name"],
                city_slug=slug,
                dataset_id=meta["dataset_id"],
                center_lon=center[0],
                center_lat=center[1],
                zoom=meta.get("zoom", 12),
                boundary_filename=meta.get("boundary", ""),
            )
        except Exception as exc:
            print(f"[SKIP] {slug}: {exc}")
            skipped += 1
            continue
        out = CITIES_DIR / f"{slug}.html"
        out.write_text(html, encoding="utf-8")
        written += 1
        print(f"[OK] {out.relative_to(CITIES_DIR.parent)}")

    print(f"\nRegenerated {written} city page(s); {skipped} skipped.")


if __name__ == "__main__":
    main()
