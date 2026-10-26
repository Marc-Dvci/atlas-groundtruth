"""Same stretch of riverbank, paid more than once.

DPWH contracts state their reach as stations ("Sta. 1+000 to Sta. 1+400").
Two contracts in the same barangay, on the same river, from the same district
office, whose station intervals overlap, describe the same metres of bank.
That is a red flag for the fleet to examine, not a verdict.
"""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def norm(s: str | None) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


SECTION = re.compile(r"([A-Za-z\.\- ]+?)\s+Section", re.I)
BRGYS = re.compile(r"(?:barangay|brgy\.?)\s+([a-z\.\- ]+?)(?:,|\(|$| purok| sta)", re.I)


def section(desc: str) -> str:
    m = SECTION.search(desc or "")
    return norm(m.group(1).split()[-1]) if m else ""


def brgys(desc: str) -> set[str]:
    return {norm(x) for x in BRGYS.findall(desc or "")}


def same_place(r1: dict, r2: dict) -> bool:
    s1, s2 = section(r1["desc"]), section(r2["desc"])
    if s1 and s2 and s1 != s2:
        return False
    b1, b2 = brgys(r1["desc"]), brgys(r2["desc"])
    if b1 and b2 and not (b1 & b2):
        return False
    return True


def main() -> None:
    recs = json.loads((ROOT / "data/portfolio/projects.json").read_text(encoding="utf-8"))
    groups = collections.defaultdict(list)
    for r in recs:
        st = r.get("stations_m") or []
        if len(st) < 2 or not r.get("cost"):
            continue
        a, b = sorted((st[0], st[-1]))
        if b - a < 20:
            continue
        place = norm(r.get("brgy_text")) or norm(r.get("river_text"))
        if not place:
            continue
        groups[(r.get("deo"), norm(r.get("muni")), place)].append((a, b, r))
    pairs = []
    for key, items in groups.items():
        items.sort(key=lambda x: x[0])
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a1, b1, r1 = items[i]
                a2, b2, r2 = items[j]
                ov = min(b1, b2) - max(a1, a2)
                if ov <= 10 or not same_place(r1, r2):
                    continue
                pairs.append({
                    "a": r1["id"], "b": r2["id"], "overlap_m": round(ov),
                    "a_range": [a1, b1], "b_range": [a2, b2],
                    "a_year": r1.get("year"), "b_year": r2.get("year"),
                    "a_cost": r1["cost"], "b_cost": r2["cost"],
                    "province": r1.get("province"), "muni": r1.get("muni"), "place": key[2],
                    "a_desc": r1["desc"], "b_desc": r2["desc"],
                    "a_contractor": r1["contractor"], "b_contractor": r2["contractor"],
                })
    pairs.sort(key=lambda p: -p["overlap_m"])
    out = ROOT / "data/portfolio/overlaps.json"
    out.write_text(json.dumps(pairs, ensure_ascii=False, indent=1), encoding="utf-8")
    ids = {p["a"] for p in pairs} | {p["b"] for p in pairs}
    bul = [p for p in pairs if p["province"] == "Bulacan"]
    print(f"{len(pairs)} overlapping pairs, {len(ids)} contracts; Bulacan {len(bul)} pairs")
    for p in bul[:12]:
        print(f"  {p['a']} {p['a_range']} ({p['a_year']}) x {p['b']} {p['b_range']} ({p['b_year']}): {p['overlap_m']} m | {p['muni']} {p['place']}")


if __name__ == "__main__":
    main()
