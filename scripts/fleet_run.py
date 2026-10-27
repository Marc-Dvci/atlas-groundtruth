"""Run a fleet mission over a province from the command line (the web app's launch button does the same).

    .venv/Scripts/python scripts/fleet_run.py --run bulacan --lm open --budget 40 --full-top 40 [--limit N] [--workers 4]

Resumable: contracts already sealed in the run are counted, not audited again.
"""
from __future__ import annotations

import argparse
import faulthandler
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas.audit import portfolio  # noqa: E402
from atlas.fleet import Fleet  # noqa: E402


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="bulacan")
    ap.add_argument("--province", default="Bulacan")
    ap.add_argument("--lm", default="open", choices=["meta", "open"])
    ap.add_argument("--budget", type=float, default=40.0, help="model budget for this mission, USD")
    ap.add_argument("--full-top", type=int, default=40, help="highest-priority contracts audited at full depth")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--deadline", default="2026-11-06")
    a = ap.parse_args(argv)
    recs = portfolio()
    ids = sorted((r["id"] for r in recs.values() if (r.get("province") or "").lower() == a.province.lower()),
                 key=lambda i: -(recs[i].get("priority") or 0))
    if a.limit:
        ids = ids[: a.limit]
    # every thread's stack every 5 minutes, so a stalled mission says where it is waiting
    stacks = open(ROOT / "data" / f"fleet_{a.run}_stacks.log", "w", encoding="utf-8")
    faulthandler.dump_traceback_later(300, repeat=True, file=stacks)
    fl = Fleet(a.run, workers=a.workers)
    p = fl.launch(ids, mission=f"Every flood-control contract in {a.province}, before the deadline",
                  budget_usd=a.budget, deadline=a.deadline, lm=a.lm, full_top=a.full_top)
    print(json.dumps({k: v for k, v in p.items() if k != "order"}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
