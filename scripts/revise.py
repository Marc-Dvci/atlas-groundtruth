"""Audit sealed cases again under a corrected rule, keeping the record.

    .venv/Scripts/python scripts/revise.py --run eval [--only ID ...] [--dry-run]

The rule (28 Oct 2026): a reading that can decide a verdict counts only when the second reader explicitly agrees.
Before it, a missing or "cannot tell" second reading left the first reading standing, captures before the award other
than the last one were never read twice, and street photos and relocation candidates had one reader.

Picks the cases that rule can change: a sub-metre present/absent claim before the award or after completion without
an agreeing second reading, a street photo's present/absent claim, or a relocation candidate. Each is audited again at
its original depth with the same models and the same site. Model requests are cached on disk by body, so every step
the rule does not touch returns its sealed answer, and only the new readings are billed. The earlier case file is kept
as case.r<n>.json, every earlier ledger entry stays, and the new entries append to the same ledger. Anchor the run
again afterwards (scripts/anchor.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas.agents.existence import DECISIVE  # noqa: E402
from atlas.audit import audit, declarations, make_client, open_run  # noqa: E402
from atlas.case import DATA, Event  # noqa: E402
from atlas.verdict import window_of  # noqa: E402

RULE = "SECOND_READER_MUST_AGREE"
RULE_TEXT = "a reading that can decide a verdict counts only when the second reader explicitly agrees"


def unconfirmed(c: dict) -> list[str]:
    """The claims in a sealed case that the corrected rule would not have let stand as they are."""
    frames = {f["captured"]: f for f in c.get("frames") or []}
    out = []
    for f in c.get("findings") or []:
        if f["claim"] not in ("present", "absent"):
            continue
        if f["family"] == "street":
            out.append(f"street photo {f['observed']}: {f['claim']}, one reader")
        elif f["family"] == "optical_vhr" and f.get("site", "declared") != "declared":
            out.append(f"relocation candidate {f['observed']}: one reader")
        elif f["family"] == "optical_vhr" and window_of(f["observed"], c["award"], c["completion"]) in DECISIVE:
            x = (frames.get(f["observed"]) or {}).get("cross") or {}
            ok = x.get("structure") in (("yes", "partly") if f["claim"] == "present" else ("no",))
            if not ok:
                out.append(f"capture {f['observed']}: {f['claim']}, second reader {x.get('structure') or 'never asked'}")
    return out


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="audit the --only cases again even if every claim is confirmed")
    ap.add_argument("--why", default="audited again on request", help="the reason sealed with a forced audit")
    a = ap.parse_args(argv)
    lg, rdir = open_run(a.run)
    todo = []
    for p in sorted((rdir / "cases").glob("*/case.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        if c.get("error") or not c.get("verdict") or (a.only and c["id"] not in a.only):
            continue
        why = unconfirmed(c) or ([a.why] if a.force and a.only else [])
        if why:
            todo.append((p, c, why))
    print(f"{a.run}: {len(todo)} case(s) to audit again")
    for _, c, why in todo:
        print(f"  {c['id']} {c['verdict']['outcome']}: " + "; ".join(why))
    if a.dry_run or not todo:
        return
    meta = make_client()
    decl = declarations()
    log = open(rdir / "events_revisions.jsonl", "a", encoding="utf-8")

    def emit(ev: Event) -> None:
        log.write(json.dumps(ev.as_dict(), ensure_ascii=False, default=str) + "\n")
        log.flush()

    for p, prev, why in todo:
        cdir = p.parent
        n = len(list(cdir.glob("case.r*.json"))) + 1
        (cdir / f"case.r{n}.json").write_text(json.dumps(prev, ensure_ascii=False), encoding="utf-8")
        e = lg.append(prev["id"], "atlas", "rule_revision", {"rule": RULE, "text": RULE_TEXT, "unconfirmed": why,
                                                            "previous_verdict": prev["verdict"]["outcome"],
                                                            "previous_file": f"case.r{n}.json"})
        for ph in prev.get("photos") or []:  # the sealed photo, since Mapillary's links expire
            kept = DATA / "cache/mapillary/img" / f"{ph['id']}.jpg"
            if not kept.exists() and (DATA / "evidence" / ph["blob"]).exists():
                kept.parent.mkdir(parents=True, exist_ok=True)
                kept.write_bytes((DATA / "evidence" / ph["blob"]).read_bytes())
        m = prev.get("models") or {}
        rev = prev.get("revision") or {}
        site = None
        if rev.get("challenge_entry"):  # a case already moved by a signed challenge stays at the point it names
            st = next(e.payload["statement"] for e in lg.entries() if e.hash == rev["challenge_entry"])
            lon, lat = (float(x) for x in st["site"].split(","))
            site = {"lon": lon, "lat": lat, "challenge_entry": rev["challenge_entry"], "challenge_seq": rev["challenge_seq"]}
        out = audit(prev["record"], lg, meta, emit, rdir, declaration=decl.get(prev["id"]), depth=m.get("depth", "full"),
                    lm=m.get("lm") or "meta", site=site)
        pv = prev["verdict"]
        earlier = [{"kind": "challenge", **x} if "kind" not in x else x for x in rev.get("previous", [])]
        out["revision"] = {"n": n, "kind": "rule", "rule": RULE, "rule_text": RULE_TEXT, "rule_entry": e.hash,
                           "rule_seq": e.seq, **({k: rev[k] for k in ("challenge_entry", "challenge_seq") if k in rev}),
                           "previous": earlier + [{"kind": "rule", "outcome": pv.get("outcome"), "reason": pv.get("reason"),
                                                   "headline": pv.get("headline"), "file": f"case.r{n}.json",
                                                   "ledger_head": prev.get("ledger_head"),
                                                   "reach": (prev.get("locator") or {}).get("reach")}]}
        if prev.get("triage"):  # triage_run.py reseals it against the new verdict
            out["triage"] = prev["triage"]
        p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        v = out.get("verdict") or {}
        same_site = json.loads(json.dumps((out.get("locator") or {}).get("reach"))) == (prev.get("locator") or {}).get("reach")
        print(f"{prev['id']}: {pv['outcome']} -> {v.get('outcome')} ({v.get('reason')}) err={out.get('error')} "
              f"{'' if same_site else 'REACH CHANGED '}"
              f"meta=${meta.meter.spent_usd:.2f} open=${meta.open_meter.spent_usd:.2f}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
