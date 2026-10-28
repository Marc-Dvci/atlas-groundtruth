"""Independent site check: a second Locator, on another model and another host, re-locates every flagged contract.

    .venv/Scripts/python scripts/site_check.py --run bulacan [--host fireworks] [--workers 4] [--only ID ...]

A verdict is only as good as the reach it was read on. For each contract the run flagged, Muse Spark Open (served by
Fireworks) reads the contract text and works through the same map tools, without seeing where the run looked. Its
reach is then compared with the one the verdict was based on. Every tool call and the comparison are sealed in the
ledger of `<run>-sitecheck`. Resumable: contracts already checked are skipped.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from atlas.agents import existence, locator  # noqa: E402
from atlas.audit import make_client, open_run  # noqa: E402
from atlas.case import DATA, Case, Event  # noqa: E402
from atlas.triage import SAME_REACH, SAME_SITE_M, reach_overlap  # noqa: E402
from atlas.geo.index import get_index  # noqa: E402
from atlas.meta import OPEN  # noqa: E402

FLAGS = ("probable_ghost", "relocated", "built_late", "exists_before_contract")


def compare(a: dict | None, b: dict | None) -> dict:
    """How far apart two located reaches are, and how much of each runs along the other."""
    if not (a and a.get("reach")) or not (b and b.get("reach")):
        return {"agree": False, "gap_m": None, "overlap": 0.0,
                "why": "only one locator found a site" if (a or {}).get("reach") or (b or {}).get("reach")
                else "neither locator found a site"}
    gap, ov = reach_overlap(a["reach"], b["reach"])
    agree = gap < SAME_SITE_M and ov >= SAME_REACH
    why = (f"the reaches overlap along {ov:.0%} of their length" if ov > 0 else f"the reaches are {gap:.0f} m apart")
    return {"agree": agree, "gap_m": round(gap), "overlap": round(ov, 2), "why": why}


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="bulacan")
    ap.add_argument("--host", default="fireworks", choices=["fireworks", "baseten"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--all", action="store_true", help="check every located contract, not only the flagged ones")
    ap.add_argument("--summary", action="store_true", help="only rebuild summary.json from the sealed checks")
    a = ap.parse_args(argv)

    src = DATA / "runs" / a.run / "cases"
    cases = {}
    for p in sorted(src.glob("*/case.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        oc = (c.get("verdict") or {}).get("outcome")
        if (a.only and c["id"] in a.only) or (not a.only and (a.all or oc in FLAGS)):
            cases[c["id"]] = c
    out_run = f"{a.run}-sitecheck"
    ledger, rdir = open_run(out_run)
    done = {p.parent.name for p in (rdir / "cases").glob("*/check.json")} if (rdir / "cases").exists() else set()
    todo = [] if a.summary else [cid for cid in cases if cid not in done]
    print(f"{len(cases)} to check, {len(done & set(cases))} already sealed, {len(todo)} now", flush=True)
    meta = make_client(open_host=a.host)
    gi = get_index()
    log = open(rdir / "events.jsonl", "a", encoding="utf-8")
    lock = threading.Lock()

    def emit(e: Event) -> None:
        with lock:
            log.write(json.dumps(e.as_dict(), ensure_ascii=False, default=str) + "\n")
            log.flush()

    def one(cid: str) -> dict:
        c = cases[cid]
        case = Case(c["record"], ledger, meta, emit, rdir / "cases" / cid)
        case.facts["spark"] = OPEN
        t0 = time.time()
        try:
            loc = locator.run(case, gi, tracer=lambda lon, lat: existence.trace_river(case, lon, lat))
            err = None
        except Exception as e:  # a failed check is recorded, and the case counts as unchecked
            loc, err = {}, f"{type(e).__name__}: {e}"[:300]
        first = c.get("locator") or {}
        cmp = compare(first, loc) if err is None else {"agree": None, "gap_m": None, "overlap": None, "why": err}
        res = {"id": cid, "verdict": (c.get("verdict") or {}).get("outcome"),
               "first": {"mode": first.get("mode"), "waterway": first.get("waterway"), "center": first.get("center")},
               "check": {"mode": loc.get("mode"), "host": a.host, "waterway": loc.get("waterway"),
                         "center": loc.get("center"), "confidence": (loc.get("answer") or {}).get("confidence"),
                         "reasoning": (loc.get("answer") or {}).get("reasoning"), "reach": loc.get("reach")},
               **cmp, "error": err, "first_head": c.get("ledger_head"), "seconds": round(time.time() - t0, 1)}
        res["entry"] = case.record_entry("sitecheck", "site_check", {k: v for k, v in res.items() if k != "check"}
                                         | {"check": {k: v for k, v in res["check"].items() if k != "reach"}})
        case.save_json("check.json", res)
        return res

    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as ex:
        for i, r in enumerate(ex.map(one, todo), 1):
            print(f"{i}/{len(todo)} {r['id']} {r['verdict']:<24} agree={r['agree']} gap={r['gap_m']} m "
                  f"ov={r['overlap']} {r['seconds']} s  fireworks=${meta.open_meter.spent_usd:.3f} "
                  f"meta=${meta.meter.spent_usd:.3f}", flush=True)
    allres = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((rdir / "cases").glob("*/check.json"))
              if p.parent.name in cases]
    for r in allres:  # checks sealed before the overlap rule: apply it here, the sealed entries stay as written
        if r["agree"]:
            r["agree"] = (r.get("overlap") or 0) >= SAME_REACH
    summary = {"run": a.run, "host": a.host, "checked": len(allres),
               "agree": sum(1 for r in allres if r["agree"]), "disagree": sum(1 for r in allres if r["agree"] is False),
               "failed": sum(1 for r in allres if r["agree"] is None), "minutes": round((time.time() - t0) / 60, 1),
               "by_verdict": {}}
    for oc in FLAGS:
        rs = [r for r in allres if r["verdict"] == oc]
        summary["by_verdict"][oc] = {"checked": len(rs), "agree": sum(1 for r in rs if r["agree"])}
    (rdir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
