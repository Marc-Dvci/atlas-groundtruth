"""How far each instrument can be trusted, checked against another instrument on the same reaches.

    .venv/Scripts/python scripts/instruments.py --run bulacan

No official record says which Bulacan contracts were built as declared, so this measures the parts instead of the
whole, each against an independent source, from sealed cases only (no model call):

* Sentinel-2 against sub-metre imagery. Reaches where two-reader sub-metre imagery shows the bank bare and later a
  wall after the completion date: did the 10 m series, from ESA's own pixels, show a change or work on that bank?
  Counted only on banks vegetated enough for an unchanged series to count (the same floor atlas/verdict.py applies),
  since that is where the "bare, then unchanged" rule leans on it. Also: reaches with a wall both before the award and
  after (the series should show no new change), and reaches bare in both (it should not either).
* The two readers (Muse Spark 1.3 and Muse Spark Open) on the same captures: yes / no answers to "is a structure
  there", and Cohen's kappa.
* The two Locators (Muse Spark 1.3, and Muse Spark Open on Fireworks from the contract text alone): same reach.

And, for the run's worklist: the probable ghosts on a confirmed site that no ruling in the answer keys names, what
was paid for them, and the people on low ground around them (High Resolution Settlement Layer cells within 1.5 km of a
reach and at most 3 m above its bank, each cell counted once however many reaches it is near).

Writes data/runs/<run>/instruments.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas.verdict import QUALITY_FLOOR, window_of  # noqa: E402

RUNS = ROOT / "data" / "runs"


def s2_floor_quality(s2: dict) -> float:
    """The quality an unchanged series would get on this reach (atlas/agents/existence.py run_s2)."""
    banks = s2.get("banks_before") or {}
    floor = min(banks.values()) if banks else (s2.get("before") or {}).get("ndvi", 0)
    return round(0.5 + 0.4 * min(1.0, max(0.0, (floor - 0.15) / 0.3)), 2)


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="bulacan")
    a = ap.parse_args(argv)
    rdir = RUNS / a.run
    built, built_all, stable_wall, stable_bare = Counter(), Counter(), Counter(), Counter()
    pairs, sites = Counter(), Counter()
    for p in sorted((rdir / "cases").glob("*/case.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        site = (c.get("triage") or {}).get("site")
        if site in ("confirmed", "disputed"):
            sites[site] += 1
        v, award, done = c.get("verdict") or {}, c.get("award"), c.get("completion")
        for f in c.get("frames") or []:
            r1, r2 = (f.get("reading") or {}).get("structure_visible"), (f.get("cross") or {}).get("structure")
            if r1 in ("yes", "partly", "no") and r2 in ("yes", "partly", "no"):
                pairs[("yes" if r1 != "no" else "no", "yes" if r2 != "no" else "no")] += 1
        if not v or not award or not done:
            continue
        dec = [d["finding"] for d in v.get("decisions", [])]
        vhr = sorted((f for f in dec if f["family"] == "optical_vhr" and f.get("site", "declared") == "declared"
                      and f["quality"] >= QUALITY_FLOOR and f["claim"] in ("present", "absent")), key=lambda f: f["observed"])
        s2f = next((f for f in dec if f["family"] == "optical_hr"), None)
        s2 = c.get("s2") or {}
        if s2f is None or not s2.get("rows"):
            continue
        said = "no change" if s2f["claim"] == "absent" else "change" if s2f["claim"] == "present" else (
            "work, then regrowth" if s2.get("disturbance") else "too few scenes")
        win = {f["observed"]: window_of(f["observed"], award, done) for f in vhr}
        new = any(x["claim"] == "absent" and y["claim"] == "present" and x["observed"] < y["observed"]
                  and win[y["observed"]] == "after_completion" for i, x in enumerate(vhr) for y in vhr[i + 1:])
        before = {f["claim"] for f in vhr if win[f["observed"]] == "before_award"}
        after = {f["claim"] for f in vhr if win[f["observed"]] == "after_completion"}
        if new and "present" not in before:
            built_all[said] += 1
            if s2_floor_quality(s2) >= QUALITY_FLOOR:
                built[said] += 1
        elif "present" in before and "present" in after:
            stable_wall[said] += 1
        elif before == {"absent"} and after == {"absent"}:
            stable_bare[said] += 1
    yy, nn = pairs[("yes", "yes")], pairs[("no", "no")]
    yn, ny = pairs[("yes", "no")], pairs[("no", "yes")]
    n = yy + nn + yn + ny
    po = (yy + nn) / n if n else 0
    pe = (((yy + yn) * (yy + ny)) + ((nn + ny) * (nn + yn))) / (n * n) if n else 0
    kappa = (po - pe) / (1 - pe) if pe < 1 else 0
    ruled = set()
    for k in (ROOT / "data" / "answer_key").glob("*.json"):
        ruled |= {c["id"] for c in json.loads(k.read_text(encoding="utf-8"))["cases"]}
    tri = json.loads((rdir / "triage.json").read_text(encoding="utf-8")) if (rdir / "triage.json").exists() else {"rows": []}
    ghosts = [r for r in tri["rows"] if r["outcome"] == "probable_ghost" and r["tier"] == "lead" and r["id"] not in ruled]
    cells: dict[tuple[float, float], float] = {}
    for r in ghosts:
        im = json.loads((rdir / "cases" / r["id"] / "case.json").read_text(encoding="utf-8")).get("impact") or {}
        if im.get("cells_blob"):
            for lon, lat, pop in json.loads((ROOT / "data" / "evidence" / im["cells_blob"]).read_text(encoding="utf-8")):
                cells[(round(lon, 6), round(lat, 6))] = pop
    out = {
        "run": a.run,
        "ghost_leads_no_ruling": {"contracts": len(ghosts), "php": round(sum(r["cost"] for r in ghosts), 2),
                                  "people_low_ground": round(sum(cells.values())),
                                  "note": "probable ghosts on a site the second Locator confirmed, named by no ruling in "
                                          "the answer keys; people: HRSL cells within 1.5 km and at most 3 m above the "
                                          "bank, each counted once"},
        "s2_vs_submetre": {
            "wall_built": {"reaches": sum(built.values()), **built,
                           "note": "sub-metre: bare, then a wall after completion; banks where an unchanged series counts"},
            "wall_built_all_banks": {"reaches": sum(built_all.values()), **built_all},
            "wall_before_and_after": {"reaches": sum(stable_wall.values()), **stable_wall},
            "bare_before_and_after": {"reaches": sum(stable_bare.values()), **stable_bare},
        },
        "readers": {"pairs": n, "agree": yy + nn, "both_yes": yy, "both_no": nn, "first_yes_second_no": yn,
                    "first_no_second_yes": ny, "kappa": round(kappa, 2)},
        "locators": {"re_located": sites["confirmed"] + sites["disputed"], "same_reach": sites["confirmed"],
                     "note": "second Locator from the contract text alone; same reach = runs along at least half the first"},
    }
    (rdir / "instruments.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
