"""Audit every answer-key contract, then compare Atlas with the official findings.

    .venv/Scripts/python scripts/evaluate.py [--run eval] [--lm meta|open] [--only ID ...] [--score-only]
    .venv/Scripts/python scripts/evaluate.py --compare eval eval-open

The audit never reads the answer key; only this script does, after the verdicts are sealed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas.audit import audit, declarations, make_client, open_run, portfolio  # noqa: E402
from atlas.case import DATA, Event  # noqa: E402


def _cases(run: str) -> dict[str, dict]:
    out = {}
    for p in sorted((DATA / "runs" / run / "cases").glob("*/case.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        out[c["id"]] = c
    return out


def score(run: str, key_name: str = "cases") -> dict:
    """key_name: an answer key in data/answer_key/. "blind_2026-10" holds rulings matched after the province run was
    sealed, so it scores that run blind."""
    key = json.loads((DATA / "answer_key" / f"{key_name}.json").read_text(encoding="utf-8"))["cases"]
    got = _cases(run)
    rows = []
    for k in key:
        c = got.get(k["id"])
        if c is None:
            continue
        v = c.get("verdict") or {}
        oc = v.get("outcome")
        tri = c.get("triage") or {}
        agree = oc in k["expected"]
        # Every official finding here says the contract's works are not what it declared. Atlas is
        # - compatible when it flags the contract another way (older structure, bare when certified, built elsewhere);
        # - unresolved when it sends the contract to an investigator without a flag: "can't verify", or "exists" that does
        #   not clear the contract (not dated to it, a reach other concurrent contracts also claim, or a site the second
        #   Locator disputes; atlas/triage.py);
        # - in disagreement only when it clears the contract.
        # Until 28 Oct an "exists" counted as compatible with an older structure; it no longer does: Atlas had dated those
        # structures to the contract window, which says the opposite.
        flags = {"probable_ghost", "relocated", "built_late", "exists_before_contract"}
        cleared = oc == "exists" and bool(tri.get("cleared"))
        partial = (not agree) and oc in flags
        abstain = oc == "cant_verify" or (oc == "exists" and not cleared)
        rows.append({"id": k["id"], "match": k["match"], "official": k["finding"], "who": k["who"],
                     "atlas": oc, "reason": v.get("reason"), "agree": agree, "partial": partial, "abstain": abstain,
                     "contradict": (not agree) and (not partial) and (not abstain), "cleared": cleared,
                     "not_cleared": [r["code"] for r in tri.get("reasons", []) if r["code"] in (
                         "NOT_DATED_TO_CONTRACT", "SHARED_REACH", "SITE_DISPUTED", "SITE_UNCHECKED")] if oc == "exists" else [],
                     "headline": v.get("headline"), "error": c.get("error"), "model": (c.get("locator") or {}).get("model")})
    n = len(rows)
    decided = [r for r in rows if not r["abstain"]]

    def tally(rs: list[dict]) -> dict:
        return {"cases": len(rs), "agree": sum(r["agree"] for r in rs), "partial": sum(r["partial"] for r in rs),
                "abstain": sum(r["abstain"] for r in rs), "contradict": sum(r["contradict"] for r in rs)}

    out = {
        "run": run, "key": key_name, "cases": n,
        "agree": sum(r["agree"] for r in rows),
        "partial": sum(r["partial"] for r in rows),
        "abstain": sum(r["abstain"] for r in rows),
        "contradict": sum(r["contradict"] for r in rows),
        "agree_when_decided": round(sum(r["agree"] for r in decided) / len(decided), 3) if decided else None,
        "by_match": {"exact_or_strong": tally([r for r in rows if r["match"] in ("exact", "strong")]),
                     "candidate": tally([r for r in rows if r["match"] == "candidate"])},
        "rows": rows,
    }
    name = "evaluation.json" if key_name == "cases" else f"evaluation_{key_name}.json"
    (DATA / "runs" / run / name).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def compare(run_a: str, run_b: str) -> dict:
    """Same contracts, two model hosts: how often do the verdicts, the located sites and the readings agree?"""
    from shapely.geometry import shape

    from atlas.geo.geom import to_m
    a, b = _cases(run_a), _cases(run_b)
    rows, same_site_reads, reads_agree = [], 0, 0
    for cid in sorted(set(a) & set(b)):
        ca, cb = a[cid], b[cid]
        va, vb = (ca.get("verdict") or {}).get("outcome"), (cb.get("verdict") or {}).get("outcome")
        la, lb = ca.get("locator") or {}, cb.get("locator") or {}
        gap = None
        if la.get("reach") and lb.get("reach"):
            gap = round(to_m(shape(la["reach"])).distance(to_m(shape(lb["reach"]))))
        # capture readings, compared only where both looked at the same site
        claims = []
        if gap is not None and gap < 50:
            ra = {f["captured"]: (f.get("reading") or {}).get("structure_visible") for f in ca.get("frames") or []}
            rb = {f["captured"]: (f.get("reading") or {}).get("structure_visible") for f in cb.get("frames") or []}
            for d in sorted(set(ra) & set(rb)):
                if ra[d] and rb[d]:
                    yes = lambda x: x in ("yes", "partly")  # noqa: E731
                    claims.append(yes(ra[d]) == yes(rb[d]))
        same_site_reads += len(claims)
        reads_agree += sum(claims)
        rows.append({"id": cid, run_a: va, run_b: vb, "same_verdict": va == vb, "site_gap_m": gap,
                     "readings_compared": len(claims), "readings_agree": sum(claims)})
    out = {"a": run_a, "b": run_b, "cases": len(rows), "same_verdict": sum(r["same_verdict"] for r in rows),
           "same_site": sum(1 for r in rows if r["site_gap_m"] is not None and r["site_gap_m"] < 50),
           "readings_compared": same_site_reads, "readings_agree": reads_agree, "rows": rows}
    (DATA / "runs" / run_b / f"compare_{run_a}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="eval")
    ap.add_argument("--lm", default="meta", choices=["meta", "open"])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--score-only", action="store_true")
    ap.add_argument("--compare", nargs=2, metavar=("RUN_A", "RUN_B"))
    ap.add_argument("--key", default="cases", help="answer key in data/answer_key/ (cases, blind_2026-10)")
    a = ap.parse_args(argv)
    if a.compare:
        c = compare(*a.compare)
        print(json.dumps({k: v for k, v in c.items() if k != "rows"}, indent=1))
        for r in c["rows"]:
            print(f"  {r['id']} {str(r[a.compare[0]]):<22} {str(r[a.compare[1]]):<22} site gap {r['site_gap_m']} m, "
                  f"readings {r['readings_agree']}/{r['readings_compared']}")
        return
    if not a.score_only:
        key = json.loads((DATA / "answer_key" / f"{a.key}.json").read_text(encoding="utf-8"))["cases"]
        ids = a.only or [k["id"] for k in key]
        recs, decl = portfolio(), declarations()
        meta = make_client()
        ledger, rdir = open_run(a.run)
        log = open(rdir / "events.jsonl", "a", encoding="utf-8")

        def emit(e: Event) -> None:
            log.write(json.dumps(e.as_dict(), ensure_ascii=False, default=str) + "\n")
            log.flush()

        for cid in ids:
            out = audit(recs[cid], ledger, meta, emit, rdir, declaration=decl.get(cid), depth="full", lm=a.lm)
            v = out.get("verdict") or {}
            print(f"{cid}: {v.get('outcome')} ({v.get('reason')}) {out['seconds']} s err={out.get('error')} "
                  f"meta=${meta.meter.spent_usd:.3f} open=${meta.open_meter.spent_usd:.3f}", flush=True)
    s = score(a.run, a.key)
    print(json.dumps({k: v for k, v in s.items() if k != "rows"}, indent=1))
    for r in s["rows"]:
        print(f"  {r['id']} [{r['match']:>9}] official={r['official']:<24} atlas={str(r['atlas']):<22} "
              f"{'AGREE' if r['agree'] else 'partial' if r['partial'] else 'abstain' if r['abstain'] else 'CONTRADICT'}")


if __name__ == "__main__":
    main(sys.argv[1:])
