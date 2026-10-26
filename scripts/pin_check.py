"""How far is each published pin from the barangay its own contract names?

For every Bulacan contract whose description names an official barangay of its municipality, measure the distance
from the published pin to that barangay's boundary (0 when the pin is inside). Writes data/portfolio/pins.json.

    .venv/Scripts/python scripts/pin_check.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas.geo.geom import to_m  # noqa: E402
from atlas.geo.index import muni_key  # noqa: E402


def words(s: str) -> str:
    s = re.sub(r"\bsta\.?\s", "santa ", (s or "").lower())
    s = re.sub(r"\bsto\.?\s", "santo ", s)
    return " " + re.sub(r"[^a-z0-9ñ]+", " ", s) + " "


def main() -> None:
    recs = [r for r in json.loads((ROOT / "data/portfolio/projects.json").read_text(encoding="utf-8"))
            if (r.get("province") or "").lower() == "bulacan" and r.get("lon") is not None]
    fc = json.loads((ROOT / "data/admin/bulacan_barangays.geojson").read_text(encoding="utf-8"))
    by_muni: dict[str, list] = {}
    for f in fc["features"]:
        p = f["properties"]
        by_muni.setdefault(muni_key(p["muni"]), []).append((words(p["name"]).strip(), p["name"], shape(f["geometry"])))
    rows = []
    for r in recs:
        text = words(r["desc"])
        named = [(n, g) for key, n, g in by_muni.get(muni_key(r.get("muni")), []) if len(key) >= 3 and f" {key} " in text]
        if not named:
            continue
        pin = Point(r["lon"], r["lat"])
        d, name = min((to_m(pin).distance(to_m(g)), n) for n, g in named)
        rows.append({"id": r["id"], "barangay": name, "distance_m": round(d), "desc": r["desc"][:160], "cost": r.get("cost")})
    rows.sort(key=lambda x: -x["distance_m"])
    out = {"matched": len(rows), "over_200m": sum(x["distance_m"] > 200 for x in rows),
           "over_1km": sum(x["distance_m"] > 1000 for x in rows), "worst": rows[:10]}
    (ROOT / "data/portfolio/pins.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print({k: v for k, v in out.items() if k != "worst"})
    for x in rows[:5]:
        print(f"  {x['id']} {x['distance_m']:>6} m from {x['barangay']}: {x['desc'][:90]}")


if __name__ == "__main__":
    main()
