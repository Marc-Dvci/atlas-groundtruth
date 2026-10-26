"""Audit one contract end to end.

    python -m atlas.audit 25CC0252 [--run demo] [--offline] [--no-casefile]

Order: Locator -> Existence (optical history and Sentinel-2, in parallel) ->
Timeline, Valuation, Impact -> Verdict (code) -> Case builder (Muse Wonder) and,
for missing structures, the Muse Image illustration.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .agents import casebuilder, existence, ground, ledgerwork, locator, relocation
from .case import DATA, ROOT, Case, Event
from .geo.index import get_index
from .ledger import Ledger
from .meta import MetaClient, Meter, load_env
from .verdict import QUALITY_FLOOR, decide

FLAGGED = {"probable_ghost", "relocated", "exists_before_contract", "cant_verify"}


def portfolio() -> dict[str, dict]:
    recs = json.loads((DATA / "portfolio/projects.json").read_text(encoding="utf-8"))
    return {r["id"]: r for r in recs}


def declarations(province: str = "bulacan") -> dict:
    p = DATA / "declarations" / f"{province}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def open_run(run: str) -> tuple[Ledger, Path]:
    rdir = DATA / "runs" / run
    rdir.mkdir(parents=True, exist_ok=True)
    return Ledger(rdir / "ledger.jsonl", DATA / "evidence"), rdir


def make_client(offline: bool = False, cap_usd: float | None = None) -> MetaClient | None:
    load_env(ROOT / ".env")
    import os
    cap = cap_usd if cap_usd is not None else float(os.environ.get("ATLAS_BUDGET_USD", "120"))
    meter = Meter(DATA / "meter.json", cap)
    open_meter = Meter(DATA / "meter_open.json", float(os.environ.get("ATLAS_OPEN_BUDGET_USD", "90")))
    if not offline and not os.environ.get("MODEL_API_KEY"):
        return None
    return MetaClient(DATA / "cache/meta", meter, offline=offline, open_meter=open_meter)


def audit(record: dict, ledger: Ledger, meta: MetaClient | None, emit: Callable[[Event], None], rdir: Path,
          *, casefile: bool = True, declaration: dict | None = None, depth: str = "full", lm: str = "meta") -> dict:
    """lm="meta": Muse Spark 1.3 and Muse Wonder on the Meta Model API. lm="open": every language call
    (Locator, readings, case file) goes to Muse Spark Open, the open-weights model."""
    case = Case(record, ledger, meta, emit, rdir / "cases" / record["id"])
    case.facts["depth"] = depth
    from .meta import BULK, OPEN, SPARK, WONDER
    if lm == "open":
        case.facts["spark"] = case.facts["writer"] = OPEN
    else:
        case.facts["spark"] = SPARK if depth == "full" else BULK
        case.facts["writer"] = WONDER
    case.facts["lm"] = lm
    t0 = time.time()
    case.say("fleet", "case_start", record={k: record.get(k) for k in (
        "id", "desc", "muni", "province", "contractor", "cost", "start", "completion", "lon", "lat", "flags", "status")})
    case.record_entry("fleet", "record", {"record": record, "declaration": declaration})
    award, completion, basis = ledgerwork.dates(record, declaration)
    from .meta import label
    out: dict = {"id": record["id"], "record": record, "award": award, "completion": completion, "completion_basis": basis,
                 "models": {"lm": lm, "depth": depth, "spark": label(case.facts["spark"]), "writer": label(case.facts["writer"])}
                 if meta else {"lm": None, "depth": depth}}
    try:
        loc = locator.run(case, get_index(), tracer=(lambda lon, lat: existence.trace_river(case, lon, lat)) if meta else None)
        out["locator"] = {k: v for k, v in loc.items()}
        frames, s2, photos = [], {}, []
        if loc.get("located"):
            with ThreadPoolExecutor(3) as ex:
                f_opt = ex.submit(existence.run_optical, case, award, completion)
                f_s2 = ex.submit(existence.run_s2, case, award, completion)
                f_gr = ex.submit(ground.run, case, award, completion)
                frames, s2 = f_opt.result(), f_s2.result()
                try:
                    photos = f_gr.result()
                except Exception as e:  # street imagery is optional; its failure is recorded
                    case.record_entry("ground", "error", {"error": str(e)[:300]})
            # Bare at the declared reach after completion: walk the same waterway and look for a wall built elsewhere.
            bare = [f for f in case.findings if f.family == "optical_vhr" and f.claim == "absent" and f.site == "declared"
                    and f.quality >= QUALITY_FLOOR and f.observed > completion]
            if bare and meta:
                try:
                    out["relocation"] = relocation.run(case, award, completion, loc.get("waterway_geom"))
                except Exception as e:  # the search is an extra; its failure is recorded, not hidden
                    case.record_entry("relocation", "error", {"error": f"{type(e).__name__}: {e}"[:300]})
        out["frames"] = frames
        out["photos"] = photos
        out["s2"] = {k: v for k, v in s2.items() if k != "rows"} | {"rows": [
            {k: r[k] for k in ("date", "ndvi", "bright")} for r in s2.get("rows", [])]}
        out["timeline"] = ledgerwork.timeline(case, award, completion, basis, frames, s2)
        out["valuation"] = ledgerwork.valuation(case, award)
        out["impact"] = ledgerwork.impact(case)
        v = decide(case.findings, award=award, completion=completion,
                   length_m=loc.get("declared_length_m") or loc.get("length_m"), located=bool(loc.get("located")),
                   locate_note=(loc.get("note") or ""))
        prior = out["valuation"].get("prior") or []
        if v.outcome == "exists" and prior:
            tot = sum(p["cost"] or 0 for p in prior)
            v.explanation.append(f"{len(prior)} earlier contract(s), ₱{tot / 1e6:,.1f} million, paid for works within 200 m of "
                                 f"this reach and were completed before this one started; the imagery cannot tell which "
                                 f"contract built what is there.")
        case.record_entry("verdict", "verdict", v.as_dict())
        case.say("verdict", "verdict", **v.as_dict())
        out["verdict"] = v.as_dict()
        out["findings"] = [f.__dict__ for f in case.findings]
        if casefile and meta and v.outcome in FLAGGED and not (depth == "screening" and v.outcome == "cant_verify"):
            out["case_file"] = casebuilder.build(case, v, frames)
            if v.outcome in ("probable_ghost", "relocated") and frames:
                try:
                    out["illustration"] = casebuilder.illustrate(case, frames, loc["answer"].get("structure") or record["desc"],
                                                                 loc.get("declared_length_m"))
                except Exception as e:  # an illustration is optional; its failure is recorded, not hidden
                    case.record_entry("casebuilder", "illustration_failed", {"error": str(e)[:300]})
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        case.record_entry("fleet", "error", {"error": out["error"], "trace": traceback.format_exc()[-2000:]})
        case.say("fleet", "error", error=out["error"])
    out["seconds"] = round(time.time() - t0, 1)
    out["ledger_head"] = ledger.head
    case.save_json("case.json", out)
    case.say("fleet", "case_end", outcome=(out.get("verdict") or {}).get("outcome"), seconds=out["seconds"])
    return out


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--run", default="dev")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--no-casefile", action="store_true")
    ap.add_argument("--depth", default="full", choices=["full", "screening"])
    ap.add_argument("--lm", default="meta", choices=["meta", "open"])
    a = ap.parse_args(argv)
    meta = make_client(a.offline)
    if meta is None:
        print("MODEL_API_KEY missing: set it in atlas/.env", file=sys.stderr)
    recs, decl = portfolio(), declarations()
    ledger, rdir = open_run(a.run)
    log = open(rdir / "events.jsonl", "a", encoding="utf-8")

    def emit(e: Event) -> None:
        log.write(json.dumps(e.as_dict(), ensure_ascii=False, default=str) + "\n")
        log.flush()
        d = e.data
        brief = d.get("text") or d.get("tool") or d.get("outcome") or d.get("headline") or ""
        print(f"[{e.agent:>11}] {e.kind:<12} {str(brief)[:90]}")

    for cid in a.ids:
        out = audit(recs[cid], ledger, meta, emit, rdir, casefile=not a.no_casefile, declaration=decl.get(cid),
                    depth=a.depth, lm=a.lm)
        v = out.get("verdict") or {}
        print(f"\n{cid}: {v.get('outcome')} ({v.get('reason')}) in {out['seconds']} s; error={out.get('error')}")
    if meta:
        print(f"spent ${meta.meter.spent_usd:.3f} of ${meta.meter.cap_usd:.0f} ({meta.meter.calls} billed calls); "
              f"open model ${meta.open_meter.spent_usd:.3f} of ${meta.open_meter.cap_usd:.0f}")


if __name__ == "__main__":
    main(sys.argv[1:])
