"""The fleet: plan a mission against a deadline and a budget, then run it.

Projects are ordered by money at stake times red flags (published, computed
signals only). The highest-priority projects get the full depth (the whole
sub-metre history, a case file for every flagged outcome); the rest get
screening depth (the captures around the contract window, a case file only
when the evidence decides). When the remaining budget can no longer cover a
project, the fleet stops calling models and says so in the plan and in every
case it touches.
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .audit import audit, declarations, make_client, open_run, portfolio
from .case import Event

# Measured averages per project (26-27 Oct runs): full depth with a case file about $0.15, screening about $0.03.
COST_USD = {"full": 0.15, "screening": 0.03}


def plan(ids: list[str], recs: dict, budget_usd: float, deadline: str | None, full_top: int = 0) -> dict:
    items = sorted((recs[i] for i in ids), key=lambda r: -(r.get("priority") or 0))
    order, left = [], budget_usd
    for k, r in enumerate(items):
        depth = "full" if k < full_top else "screening"
        if COST_USD[depth] > left:
            depth = "screening" if COST_USD["screening"] <= left else "rules"
        left -= COST_USD.get(depth, 0.0)
        order.append({"id": r["id"], "priority": r.get("priority"), "cost": r.get("cost"),
                      "flags": [f["code"] for f in r.get("flags", [])], "depth": depth})
    n = {d: sum(o["depth"] == d for o in order) for d in ("full", "screening", "rules")}
    return {"projects": len(order), "full_depth": n["full"], "screening_depth": n["screening"], "rules_only": n["rules"],
            "budget_usd": budget_usd, "deadline": deadline, "php_total": sum((r.get("cost") or 0) for r in items),
            "order": order}


class Fleet:
    def __init__(self, run: str, workers: int = 4):
        self.run = run
        self.workers = workers
        self.ledger, self.rdir = open_run(run)
        self.events = open(self.rdir / "events.jsonl", "a", encoding="utf-8")
        self._lock = threading.Lock()
        self.stop = threading.Event()

    def emit(self, e: Event) -> None:
        with self._lock:
            self.events.write(json.dumps(e.as_dict(), ensure_ascii=False, default=str) + "\n")
            self.events.flush()

    def say(self, kind: str, **data) -> None:
        self.emit(Event(time.time(), kind, "*", "fleet", data))

    def launch(self, ids: list[str], *, mission: str, budget_usd: float, deadline: str | None = None,
               lm: str = "meta", full_top: int = 0, skip_done: bool = True) -> dict:
        recs, decl = portfolio(), declarations()
        meta = make_client()
        p = plan(ids, recs, budget_usd, deadline, full_top)
        p["mission"] = mission
        p["started"] = datetime.now(timezone.utc).isoformat()
        p["model_access"] = meta is not None
        p["lm"] = lm
        self.ledger.append("*", "fleet", "mission", {k: v for k, v in p.items() if k != "order"} | {
            "order": [o["id"] for o in p["order"]]})
        self.say("plan", **{k: v for k, v in p.items() if k != "order"}, order=[o["id"] for o in p["order"]])
        meter = (meta.open_meter if lm == "open" else meta.meter) if meta else None
        start = meter.spent_usd if meter else 0.0
        done = {"n": 0, "php": 0.0, "outcomes": {}}

        def tally(r: dict, oc: str) -> dict:
            with self._lock:
                done["n"] += 1
                done["php"] += r.get("cost") or 0
                done["outcomes"][oc] = done["outcomes"].get(oc, 0) + 1
                return dict(done, outcomes=dict(done["outcomes"]))

        def one(item: dict) -> None:
            if self.stop.is_set():
                return
            r = recs[item["id"]]
            prev = self.rdir / "cases" / r["id"] / "case.json"
            if skip_done and prev.exists():  # a resumed mission keeps what it already sealed
                c = json.loads(prev.read_text(encoding="utf-8"))
                if not c.get("error"):
                    tally(r, (c.get("verdict") or {}).get("outcome") or "error")
                    return
            m = meta if item["depth"] != "rules" else None
            if m is not None and meter.spent_usd - start + COST_USD[item["depth"]] > budget_usd:
                m, item["depth"] = None, "rules"
            self.say("dispatch", id=r["id"], depth=item["depth"])
            out = audit(r, self.ledger, m, self.emit, self.rdir, declaration=decl.get(r["id"]),
                        depth="full" if item["depth"] == "full" else "screening", casefile=m is not None, lm=lm)
            snap = tally(r, (out.get("verdict") or {}).get("outcome") or "error")
            self.say("progress", **snap, total=p["projects"],
                     spent_usd=round(meter.spent_usd - start, 3) if meter else 0.0)

        with ThreadPoolExecutor(self.workers) as ex:
            list(ex.map(one, p["order"]))
        self.say("finished", **done)
        return p
