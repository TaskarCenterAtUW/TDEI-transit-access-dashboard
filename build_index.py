#!/usr/bin/env python3
"""
Generate cities/index.html — a dynamic card grid linking to every city map.

This script writes two files:
- cities/jurisdictions.json — static metadata for every WSP jurisdiction
  (display name, slug, type, latest version). Regenerate when the source CSV changes.
- cities/index.html — a thin client shell that fetches the jurisdictions
  manifest plus pipeline_progress.json at page load and renders cards dynamically.
  The page auto-refreshes status every 15 seconds, so any new completions/failures
  appear without needing to re-run this script.

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
CITIES_DIR = ROOT / "cities"
INDEX_OUT = CITIES_DIR / "index.html"
MANIFEST_OUT = CITIES_DIR / "jurisdictions.json"

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


def build_manifest(all_jurisdictions: dict[str, tuple[float, str]]) -> dict:
    manifest: dict = {}
    for wsp_name in sorted(all_jurisdictions.keys()):
        ver, _ = all_jurisdictions[wsp_name]
        place, type_str = parse_wsp_name(wsp_name)
        display = to_display_name(place)
        slug = to_slug(display)
        manifest[wsp_name] = {
            "display": display,
            "slug": slug,
            "type": type_str,
            "version": ver,
        }
    return manifest


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>WA Transit Maps — All Cities</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, sans-serif; background: #f1f5f9; color: #1e293b; }
    header {
      background: #1e3a8a; color: #fff; padding: 20px 28px;
      display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;
    }
    header h1 { margin: 0; font-size: 20px; }
    header .stats { font-size: 13px; opacity: 0.9; }
    header .stats .pulse {
      display: inline-block; width: 8px; height: 8px; border-radius: 50%;
      background: #4ade80; margin-right: 6px; vertical-align: 1px;
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 0.4; } 50% { opacity: 1; }
    }
    .search-bar {
      padding: 14px 28px; background: #fff; border-bottom: 1px solid #e2e8f0;
      display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
    }
    .search-bar input {
      flex: 1; min-width: 180px; max-width: 340px; padding: 7px 12px;
      border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px;
    }
    .filter-btns { display: flex; gap: 8px; flex-wrap: wrap; }
    .filter-btn {
      padding: 5px 12px; font-size: 12px; border: 1px solid #cbd5e1;
      border-radius: 20px; background: #fff; cursor: pointer; transition: 0.15s;
    }
    .filter-btn.active, .filter-btn:hover { background: #1e3a8a; color: #fff; border-color: #1e3a8a; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
      gap: 12px; padding: 20px 28px;
    }
    .card {
      display: flex; flex-direction: column; gap: 6px;
      padding: 14px 12px; border-radius: 8px; background: #fff;
      border: 1px solid #e2e8f0; text-decoration: none; color: inherit;
      transition: box-shadow 0.15s, border-color 0.15s;
    }
    a.card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); border-color: #93c5fd; }
    .card-name { font-weight: 600; font-size: 13px; line-height: 1.3; }
    .card-meta { font-size: 11px; color: #64748b; }
    .badge {
      display: inline-block; padding: 2px 8px; border-radius: 20px;
      font-size: 11px; font-weight: 600; width: fit-content;
    }
    .badge-done    { background: #dcfce7; color: #166534; }
    .badge-empty   { background: #fef9c3; color: #854d0e; }
    .badge-fail    { background: #fee2e2; color: #991b1b; }
    .badge-pending { background: #f1f5f9; color: #64748b; }
    .card-pending, .card-fail { opacity: 0.6; }
    .loading { text-align: center; padding: 40px; color: #64748b; }
  </style>
</head>
<body>
  <header>
    <h1>WA Transit Accessibility Maps — All Cities</h1>
    <a href="../statewide.html" style="color:#93c5fd; font-size:13px; text-decoration:none; white-space:nowrap;">← Statewide map</a>
    <div class="stats" id="stats"><span class="pulse"></span>Loading…</div>
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

  <div class="grid" id="grid">
    <div class="loading">Loading jurisdictions…</div>
  </div>

  <script>
    let activeFilter = 'all';
    let jurisdictions = null;

    function setFilter(filter, btn) {
      activeFilter = filter;
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      filterCards();
    }

    function filterCards() {
      const q = document.getElementById('search').value.toLowerCase();
      document.querySelectorAll('#grid .card').forEach(card => {
        const name = (card.querySelector('.card-name')?.textContent || '').toLowerCase();
        const statusClass = card.className;
        const matchesSearch = !q || name.includes(q);
        const matchesFilter =
          activeFilter === 'all' ||
          (activeFilter === 'done' && (statusClass.includes('card-done') || statusClass.includes('card-empty'))) ||
          (activeFilter === 'pending' && statusClass.includes('card-pending')) ||
          (activeFilter === 'failed' && statusClass.includes('card-fail'));
        card.style.display = matchesSearch && matchesFilter ? '' : 'none';
      });
    }

    function statusInfo(status) {
      switch (status) {
        case 'completed': return { badge: 'Done',    cls: 'card-done',    badgeCls: 'badge-done',    isLink: true };
        case 'no_stops': return { badge: 'No data', cls: 'card-empty',   badgeCls: 'badge-empty',   isLink: true };
        case 'no_osw_data': return { badge: 'No OSW data', cls: 'card-empty', badgeCls: 'badge-empty', isLink: false };
        case 'no_boundary': return { badge: 'No boundary', cls: 'card-empty', badgeCls: 'badge-empty', isLink: false };
        case 'failed':    return { badge: 'Failed',  cls: 'card-fail',    badgeCls: 'badge-fail',    isLink: false };
        default:          return { badge: 'Pending', cls: 'card-pending', badgeCls: 'badge-pending', isLink: false };
      }
    }

    function renderCards(progress) {
      const counts = { total: 0, done: 0, empty: 0, pending: 0, failed: 0 };
      const grid = document.getElementById('grid');
      const parts = [];
      const sortedNames = Object.keys(jurisdictions).sort((a, b) => {
        return jurisdictions[a].display.localeCompare(jurisdictions[b].display);
      });
      for (const wsp of sortedNames) {
        const j = jurisdictions[wsp];
        const status = (progress[wsp] || {}).status || 'pending';
        const info = statusInfo(status);
        counts.total++;
        if (status === 'completed') counts.done++;
        else if (status === 'no_stops' || status === 'no_osw_data' || status === 'no_boundary') counts.empty++;
        else if (status === 'failed') counts.failed++;
        else counts.pending++;

        const tag = info.isLink ? 'a' : 'div';
        const href = info.isLink ? ` href="/cities/${j.slug}.html"` : '';
        parts.push(
          `<${tag} class="card ${info.cls}"${href}>` +
            `<div class="card-name">${escapeHtml(j.display)}</div>` +
            `<div class="card-meta">${escapeHtml(j.type)} · v${j.version}</div>` +
            `<span class="badge ${info.badgeCls}">${info.badge}</span>` +
          `</${tag}>`
        );
      }
      grid.innerHTML = parts.join('\\n');

      document.getElementById('stats').innerHTML =
        `<span class="pulse"></span>` +
        `${counts.done} complete &nbsp;·&nbsp; ` +
        `${counts.empty} no data &nbsp;·&nbsp; ` +
        `${counts.pending} pending &nbsp;·&nbsp; ` +
        `${counts.failed} failed &nbsp;·&nbsp; ` +
        `${counts.total} total`;

      filterCards();
    }

    function escapeHtml(s) {
      const d = document.createElement('div');
      d.textContent = s;
      return d.innerHTML;
    }

    async function loadProgress() {
      try {
        const resp = await fetch('/pipeline_progress.json?t=' + Date.now());
        if (!resp.ok) return {};
        return await resp.json();
      } catch (err) {
        console.warn('progress fetch failed', err);
        return {};
      }
    }

    async function init() {
      try {
        const j = await fetch('/cities/jurisdictions.json').then(r => r.json());
        jurisdictions = j;
      } catch (err) {
        document.getElementById('grid').innerHTML =
          '<div class="loading">Failed to load jurisdictions.json — run <code>python3 build_index.py</code></div>';
        return;
      }
      const progress = await loadProgress();
      renderCards(progress);
      // Auto-refresh status every 15 seconds (pipeline_progress.json updates as cities finish)
      setInterval(async () => {
        const p = await loadProgress();
        renderCards(p);
      }, 15000);
    }

    init();
  </script>
</body>
</html>
"""


def main() -> None:
    CITIES_DIR.mkdir(parents=True, exist_ok=True)

    all_jurisdictions = load_highest_version_datasets()
    manifest = build_manifest(all_jurisdictions)

    MANIFEST_OUT.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote: {MANIFEST_OUT}  ({len(manifest)} jurisdictions)")

    INDEX_OUT.write_text(INDEX_HTML, encoding="utf-8")
    print(f"Wrote: {INDEX_OUT}")
    print("  Cards render dynamically from pipeline_progress.json; refreshes every 15s.")


if __name__ == "__main__":
    main()
