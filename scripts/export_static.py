"""Export recorded runs as static files, so the web app can be served by any static host with no server and no keys.

    cd web && npx vite build --mode static --outDir dist-static --base /atlas-groundtruth/
    cd .. && .venv/Scripts/python scripts/export_static.py --out web/dist-static --runs eval eval-open bulacan

Everything the live API would return for those runs is written under <out>/static/: case files, ledgers (raw, so the
browser can re-verify every hash), the evaluation, a compact event log for the fleet replay, and every evidence file
the exported ledgers reference.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas.case import DATA  # noqa: E402
from atlas.ledger import Ledger, _blob_refs  # noqa: E402
from atlas import server  # noqa: E402

# what the fleet view reads from each event (web/src/mission/fleetState.ts); everything else stays in the case files
KEEP = {
    "fleet:plan": None, "fleet:progress": None, "fleet:finished": None, "fleet:case_end": ["outcome", "seconds"],
    "fleet:case_start": ["record"], "locator:start": [], "locator:tool": ["tool", "args", "refused"],
    "locator:traced": ["captured"], "locator:located": ["waterway", "length_m", "pin_offset_m"],
    "existence:captures": ["captures"], "existence:frame": ["captured", "coverage"], "existence:reading": ["change", "summary"],
    "existence:s2": ["first_change"], "ground:photos": ["found", "after_completion"], "ground:photo": ["date", "reading"],
    "timeline:timeline": ["flags", "events"], "valuation:valuation": ["overlaps", "flags"], "impact:impact": ["people_low_ground"],
    "verdict:verdict": ["outcome", "headline"], "casebuilder:case_file": ["headline"], "casebuilder:illustration": [],
    "relocation:start": ["before", "after"], "relocation:window": ["offset_m", "new_len_m"],
    "relocation:candidate": ["found", "distance_m"], "relocation:none": [],
}


def slim(e: dict) -> dict | None:
    k = f"{e['agent']}:{e['kind']}"
    if k not in KEEP:
        return None
    d = e.get("data") or {}
    keep = KEEP[k]
    if keep is not None:
        d = {f: d[f] for f in keep if f in d}
    if k == "fleet:case_start":
        r = d.get("record") or {}
        d = {"record": {"id": r.get("id"), "cost": r.get("cost")}}
    if k == "existence:captures":
        d = {"captures": [{"captured": c.get("captured")} for c in d.get("captures") or []]}
    if k == "timeline:timeline":
        d = {"flags": d.get("flags"), "events": [{"date": x.get("date")} for x in d.get("events") or []]}
    if k == "valuation:valuation":
        d = {"overlaps": [{"overlap_m": o.get("overlap_m"), "other": o.get("other")} for o in (d.get("overlaps") or [])[:1]],
             "flags": [{"text": f.get("text")} for f in (d.get("flags") or [])[:1]]}
    if k == "ground:photo":
        d = {"date": d.get("date"), "reading": {"structure": (d.get("reading") or {}).get("structure")}}
    return {"t": e["t"], "kind": e["kind"], "case": e["case"], "agent": e["agent"], "data": d}


def export_run(run: str, out: Path, blobs: set[str]) -> None:
    src = DATA / "runs" / run
    dst = out / "runs" / run
    (dst / "cases").mkdir(parents=True, exist_ok=True)
    ids = []
    for p in sorted((src / "cases").glob("*/case.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        ids.append(c["id"])
        (dst / "cases" / f"{c['id']}.json").write_text(json.dumps(c, ensure_ascii=False, default=str), encoding="utf-8")
        blobs.update(_blob_refs(c))
    lg = Ledger(src / "ledger.jsonl", DATA / "evidence")
    rows = [e.as_dict() for e in lg.entries()]
    shutil.copyfile(src / "ledger.jsonl", dst / "ledger.jsonl")
    for e in rows:
        blobs.update(_blob_refs(e["payload"]))
    by_case: dict[str, list] = {}
    for e in rows:
        by_case.setdefault(e["case"], []).append(e)
    for cid in ids:
        (dst / f"ledger_{cid}.json").write_text(json.dumps(by_case.get(cid, []), ensure_ascii=False),
                                                encoding="utf-8")
    if (DATA / "answer_key/cases.json").exists() and any((DATA / "runs" / run / "cases").glob("*")):
        for key in (p.stem for p in (DATA / "answer_key").glob("*.json")):
            ev = server.evaluation(run, key)
            if ev["cases"]:  # only the keys whose contracts this run audited
                name = "evaluation.json" if key == "cases" else f"evaluation_{key}.json"
                (dst / name).write_text(json.dumps(ev, ensure_ascii=False), encoding="utf-8")
    for extra in ("triage.json", "summary.json"):
        if (src / extra).exists():
            shutil.copyfile(src / extra, dst / extra)
    for other in (p.name for p in (DATA / "runs").iterdir() if p.is_dir()):
        if other != run and (DATA / "runs" / other / f"compare_{run}.json").exists():
            shutil.copyfile(DATA / "runs" / other / f"compare_{run}.json", dst / f"compare_{other}.json")
    ev = src / "events.jsonl"
    if ev.exists():
        with ev.open(encoding="utf-8") as f, (dst / "events.jsonl").open("w", encoding="utf-8") as g:
            for line in f:
                if line.strip():
                    s = slim(json.loads(line))
                    if s:
                        g.write(json.dumps(s, ensure_ascii=False, default=str) + "\n")
    print(f"{run}: {len(ids)} cases, {len(rows)} ledger entries")


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "web/dist-static"))
    ap.add_argument("--runs", nargs="+", default=["eval", "eval-open"])
    a = ap.parse_args(argv)
    out = Path(a.out) / "static"
    out.mkdir(parents=True, exist_ok=True)
    blobs: set[str] = set()
    for run in a.runs:
        export_run(run, out, blobs)
    (out / "province_bulacan.json").write_text(json.dumps(server.province("bulacan"), ensure_ascii=False), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(server.summary(), ensure_ascii=False), encoding="utf-8")
    ev = out / "evidence"
    ev.mkdir(exist_ok=True)
    size = 0
    for b in sorted(blobs):
        p = DATA / "evidence" / b
        if p.exists():
            shutil.copyfile(p, ev / b)
            size += p.stat().st_size
    print(f"evidence: {len(blobs)} files, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main(sys.argv[1:])
