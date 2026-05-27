#!/usr/bin/env python3
"""
Generate cities/index.html — a card grid linking to every generated city map.

Reads pipeline_progress.json to know which cities have been processed and what
their status is, then scans cities/*.html for the actual generated files.

Run after batch_all_cities.py completes, or any time you want to refresh the index.

Usage:
  python3 build_index.py
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JURISDICTION_CSV = ROOT / "Jurisdiction Codes.csv"
PROGRESS_FILE = ROOT / "pipeline_progress.json"
CITIES_DIR = ROOT / "cities"
INDEX_OUT = CITIES_DIR / "index.html"

KNOWN_TYPES = {"City", "city", "UI", "County", "Plus"}


def load_highest_version_datasets() -> dict[str, tuple[float, str]]:
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


def parse_wsp_name(wsp_name: str) -> tuple[str, str]:
    name = wsp_name.removeprefix("WSP_")
    tokens = name.split("_")
    if tokens[-1] in KNOWN_TYPES:
        return "_".join(tokens[:-1]), tokens[-1]
    return "_".join(tokens[:-1]), tokens[-1]


def to_display_name(place: str) -> str:
    return place.replace("_", " ")


def to_slug(display: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", display.lower()).strip("-")


def main() -> None:
    CITIES_DIR.mkdir(parents=True, exist_ok=True)

    all_jurisdictions = load_highest_version_datasets()
    progress: dict = {}
    if PROGRESS_FILE.exists():
        try:
            progress = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Build city card data
    cities: list[dict] = []
    for wsp_name in sorted(all_jurisdictions.keys()):
        ver, dataset_id = all_jurisdictions[wsp_name]
        place, type_str = parse_wsp_name(wsp_name)
        display = to_display_name(place)
        slug = to_slug(display)
        html_file = CITIES_DIR / f"{slug}.html"

        status = (progress.get(wsp_name) or {}).get("status", "pending")
        has_file = html_file.is_file()

        cities.append({
            "wsp_name": wsp_name,
            "display": display,
            "slug": slug,
            "type": type_str,
            "status": status,
            "has_file": has_file,
            "version": ver,
        })

    total = len(cities)
    completed = sum(1 for c in cities if c["status"] == "completed")
    no_stops = sum(1 for c in cities if c["status"] == "no_stops")
    pending = sum(1 for c in cities if c["status"] == "pending")
    failed = sum(1 for c in cities if c["status"] == "failed")

    # Generate card HTML for each city
    def card(c: dict) -> str:
        status = c["status"]
        if status == "completed":
            badge = '<span class="badge badge-done">Done</span>'
            link_attr = f'href="/cities/{c["slug"]}.html"'
            link_tag = "a"
            extra_class = "card-done"
        elif status == "no_stops":
            badge = '<span class="badge badge-empty">No data</span>'
            link_attr = f'href="/cities/{c["slug"]}.html"'
            link_tag = "a"
            extra_class = "card-empty"
        elif status == "failed":
            badge = '<span class="badge badge-fail">Failed</span>'
            link_attr = ""
            link_tag = "div"
            extra_class = "card-fail"
        else:
            badge = '<span class="badge badge-pending">Pending</span>'
            link_attr = ""
            link_tag = "div"
            extra_class = "card-pending"

        return (
            f'<{link_tag} class="card {extra_class}" {link_attr}>'
            f'<div class="card-name">{c["display"]}</div>'
            f'<div class="card-meta">{c["type"]} · v{c["version"]}</div>'
            f'{badge}'
            f'</{link_tag}>'
        )

    cards_html = "\n".join(card(c) for c in cities)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>WA Transit Maps — All Cities</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: system-ui, sans-serif; background: #f1f5f9; color: #1e293b; }}
    header {{
      background: #1e3a8a; color: #fff; padding: 20px 28px;
      display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;
    }}
    header h1 {{ margin: 0; font-size: 20px; }}
    header .stats {{ font-size: 13px; opacity: 0.85; }}
    .search-bar {{
      padding: 14px 28px; background: #fff; border-bottom: 1px solid #e2e8f0;
      display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
    }}
    .search-bar input {{
      flex: 1; min-width: 180px; max-width: 340px; padding: 7px 12px;
      border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px;
    }}
    .filter-btns {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .filter-btn {{
      padding: 5px 12px; font-size: 12px; border: 1px solid #cbd5e1;
      border-radius: 20px; background: #fff; cursor: pointer; transition: 0.15s;
    }}
    .filter-btn.active, .filter-btn:hover {{ background: #1e3a8a; color: #fff; border-color: #1e3a8a; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
      gap: 12px; padding: 20px 28px;
    }}
    .card {{
      display: flex; flex-direction: column; gap: 6px;
      padding: 14px 12px; border-radius: 8px; background: #fff;
      border: 1px solid #e2e8f0; text-decoration: none; color: inherit;
      transition: box-shadow 0.15s, border-color 0.15s;
    }}
    a.card:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.1); border-color: #93c5fd; }}
    .card-name {{ font-weight: 600; font-size: 13px; line-height: 1.3; }}
    .card-meta {{ font-size: 11px; color: #64748b; }}
    .badge {{
      display: inline-block; padding: 2px 8px; border-radius: 20px;
      font-size: 11px; font-weight: 600; width: fit-content;
    }}
    .badge-done    {{ background: #dcfce7; color: #166534; }}
    .badge-empty   {{ background: #fef9c3; color: #854d0e; }}
    .badge-fail    {{ background: #fee2e2; color: #991b1b; }}
    .badge-pending {{ background: #f1f5f9; color: #64748b; }}
    .card-pending, .card-fail {{ opacity: 0.6; }}
    .back-link {{ padding: 0 28px 20px; }}
    .back-link a {{ color: #1d4ed8; font-size: 13px; }}
  </style>
</head>
<body>
  <header>
    <h1>WA Transit Accessibility Maps — All Cities</h1>
    <div class="stats">
      {completed} complete &nbsp;·&nbsp;
      {no_stops} no data &nbsp;·&nbsp;
      {pending} pending &nbsp;·&nbsp;
      {failed} failed &nbsp;·&nbsp;
      {total} total
    </div>
  </header>

  <div class="search-bar">
    <input type="text" id="search" placeholder="Search city…" oninput="filterCards()" />
    <div class="filter-btns">
      <button class="filter-btn active" data-filter="all" onclick="setFilter('all',this)">All</button>
      <button class="filter-btn" data-filter="done" onclick="setFilter('done',this)">Done</button>
      <button class="filter-btn" data-filter="pending" onclick="setFilter('pending',this)">Pending</button>
      <button class="filter-btn" data-filter="failed" onclick="setFilter('failed',this)">Failed</button>
    </div>
  </div>

  <div class="back-link">
    <a href="../index.html">← Back to main dashboard</a>
  </div>

  <div class="grid" id="grid">
{cards_html}
  </div>

  <script>
    let activeFilter = 'all';

    function setFilter(filter, btn) {{
      activeFilter = filter;
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      filterCards();
    }}

    function filterCards() {{
      const q = document.getElementById('search').value.toLowerCase();
      document.querySelectorAll('#grid .card').forEach(card => {{
        const name = (card.querySelector('.card-name')?.textContent || '').toLowerCase();
        const statusClass = card.className;
        const matchesSearch = !q || name.includes(q);
        const matchesFilter =
          activeFilter === 'all' ||
          (activeFilter === 'done' && (statusClass.includes('card-done') || statusClass.includes('card-empty'))) ||
          (activeFilter === 'pending' && statusClass.includes('card-pending')) ||
          (activeFilter === 'failed' && statusClass.includes('card-fail'));
        card.style.display = matchesSearch && matchesFilter ? '' : 'none';
      }});
    }}
  </script>
</body>
</html>
"""

    INDEX_OUT.write_text(html, encoding="utf-8")
    print(f"Wrote: {INDEX_OUT}")
    print(f"  {completed} completed, {no_stops} no-stops, {pending} pending, {failed} failed")


if __name__ == "__main__":
    main()
