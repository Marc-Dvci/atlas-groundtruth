"""Money per barangay, from the words of the contracts (never from their pins).

For every official barangay, count the contracts in its municipality whose description names it, and add up
their cost. Writes the counts into web/public/data/bulacan/barangays.geojson for the province view.

    .venv/Scripts/python scripts/hotspots.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas.geo.index import muni_key, norm  # noqa: E402


def words(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\bsta\.?\s", "santa ", s)
    s = re.sub(r"\bsto\.?\s", "santo ", s)
    return " " + re.sub(r"[^a-z0-9ñ]+", " ", s) + " "


def main() -> None:
    recs = json.loads((ROOT / "data/portfolio/projects.json").read_text(encoding="utf-8"))
    bul = [r for r in recs if (r.get("province") or "").lower() == "bulacan"]
    path = ROOT / "web/public/data/bulacan/barangays.geojson"
    fc = json.loads(path.read_text(encoding="utf-8"))
    by_muni: dict[str, list[dict]] = {}
    for r in bul:
        by_muni.setdefault(muni_key(r.get("muni")), []).append(r)
    rows = []
    for f in fc["features"]:
        p = f["properties"]
        name = words(p["name"]).strip()
        if len(name) < 3:
            continue
        pat = re.compile(rf"\b{re.escape(name)}\b")
        hits = [r for r in by_muni.get(muni_key(p.get("muni")), []) if pat.search(words(r["desc"]))]
        p["n"] = len(hits)
        p["php"] = round(sum(r.get("cost") or 0 for r in hits))
        p["ids"] = [r["id"] for r in sorted(hits, key=lambda r: -(r.get("cost") or 0))][:40]
        rows.append((p["php"], p["n"], p["name"], p["muni"]))
    path.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    rows.sort(reverse=True)
    for php, n, name, muni in rows[:12]:
        print(f"{name:<22} {muni:<14} {n:>3} contracts  PHP {php / 1e9:.2f} billion")
    print("barangays with any contract:", sum(1 for r in rows if r[1]), "of", len(rows))
    _ = norm


if __name__ == "__main__":
    main()
