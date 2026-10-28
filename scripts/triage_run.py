"""Triage every flagged contract of a sealed run (see atlas/triage.py) and seal the result on the run's ledger.

    .venv/Scripts/python scripts/triage_run.py --run bulacan

Reads the run's case files and the independent site check (`<run>-sitecheck`, scripts/site_check.py). Each flagged
contract gets one "triage" entry naming the verdict entry and the site-check entry it rests on; running it again
seals nothing new unless an input changed. Writes `triage` into each case file and `triage.json` for the worklist.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas.case import DATA  # noqa: E402
from atlas.ledger import Ledger  # noqa: E402
from atlas.triage import FLAGGED, TIER_TEXT, assess  # noqa: E402

HOST_LABEL = {"fireworks": "Muse Spark Open on Fireworks", "baseten": "Muse Spark Open on Baseten"}


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="bulacan")
    a = ap.parse_args(argv)
    rdir = DATA / "runs" / a.run
    lg = Ledger(rdir / "ledger.jsonl", DATA / "evidence")
    verdict_entry, last_triage = {}, {}
    for e in lg.entries():
        if e.kind == "verdict":
            verdict_entry[e.case] = e.hash
        elif e.kind == "triage":
            last_triage[e.case] = e.payload
    checks = {}
    for p in (DATA / "runs" / f"{a.run}-sitecheck" / "cases").glob("*/check.json"):
        r = json.loads(p.read_text(encoding="utf-8"))
        r["model"] = HOST_LABEL.get((r.get("check") or {}).get("host"), "Muse Spark Open")
        checks[r["id"]] = r
    rows, sealed = [], 0
    exists_dated: Counter = Counter()
    for p in sorted((rdir / "cases").glob("*/case.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        oc = (c.get("verdict") or {}).get("outcome")
        prev = ((c.get("revision") or {}).get("previous") or [{}])[0].get("outcome")
        if prev in FLAGGED and oc not in FLAGGED:  # flagged by the mission, then audited again after a signed challenge
            rows.append({"id": c["id"], "outcome": prev, "tier": "revised", "now": oc, "cost": c["record"].get("cost"),
                         "muni": c["record"].get("muni"), "reasons": ["REVISED_AFTER_CHALLENGE"],
                         "depth": (c.get("models") or {}).get("depth")})
            continue
        if oc not in FLAGGED and oc != "exists":
            continue
        sc = checks.get(c["id"])
        t = assess(c, sc)
        if oc == "exists":
            exists_dated[t["exists_dated"]] += 1
        payload = {**t, "verdict_entry": verdict_entry.get(c["id"]),
                   "site_check_entry": (sc or {}).get("entry"), "site_check_ledger": f"{a.run}-sitecheck" if sc else None,
                   "site_check": {k: (sc or {}).get(k) for k in ("agree", "gap_m", "overlap", "why", "model")} if sc else None,
                   "second_reach": (sc or {}).get("check", {}).get("reach") if sc else None}
        sealed_payload = {k: v for k, v in payload.items() if k != "second_reach"}
        if last_triage.get(c["id"]) != sealed_payload:
            e = lg.append(c["id"], "triage", "triage", sealed_payload)
            payload["entry"] = e.hash
            sealed += 1
        else:
            payload["entry"] = (c.get("triage") or {}).get("entry")
        c["triage"] = payload
        p.write_text(json.dumps(c, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        if oc == "exists":
            continue
        rows.append({"id": c["id"], "outcome": c["verdict"]["outcome"], "tier": t["tier"], "cost": c["record"].get("cost"),
                     "muni": c["record"].get("muni"), "reasons": [r["code"] for r in t["reasons"]],
                     "depth": (c.get("models") or {}).get("depth")})
    tiers = Counter(r["tier"] for r in rows)
    out = {"run": a.run, "flagged": len(rows), "tiers": dict(tiers), "tier_text": TIER_TEXT,
           "php": {k: round(sum(r["cost"] or 0 for r in rows if r["tier"] == k)) for k in tiers},
           "by_outcome": {oc: dict(Counter(r["tier"] for r in rows if r["outcome"] == oc)) for oc in FLAGGED},
           "reasons": dict(Counter(code for r in rows for code in r["reasons"])),
           "site_checked": sum(1 for r in rows if "SITE_UNCHECKED" not in r["reasons"]),
           "exists": {"dated_to_contract": exists_dated[True], "not_dated": exists_dated[False]},
           "rows": sorted(rows, key=lambda r: (r["tier"] != "lead", -(r["cost"] or 0)))}
    (rdir / "triage.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in ("rows", "tier_text")}, indent=1, ensure_ascii=False))
    print(f"sealed {sealed} triage entries on {a.run}")


if __name__ == "__main__":
    main(sys.argv[1:])
