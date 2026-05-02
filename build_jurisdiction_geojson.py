#!/usr/bin/env python3
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "jurisdiction_bounds"
OUT_FILE = ROOT / "jurisdiction_bounds_combined.geojson"


def main() -> None:
    features = []
    files = sorted(SRC_DIR.glob("*.geojson"))
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Skipping {path.name}: {exc}")
            continue

        src_features = data.get("features", [])
        for feature in src_features:
            props = feature.setdefault("properties", {})
            props.setdefault("source_file", path.name)
            features.append(feature)

    out = {"type": "FeatureCollection", "features": features}
    OUT_FILE.write_text(json.dumps(out), encoding="utf-8")
    print(f"Wrote {len(features)} features to {OUT_FILE}")


if __name__ == "__main__":
    main()
