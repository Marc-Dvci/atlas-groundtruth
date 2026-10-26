"""Code-only agents: Timeline, Valuation, Impact. No model decides anything here."""
from __future__ import annotations

import json
from datetime import date, timedelta

from shapely.geometry import shape

from ..case import DATA, Case
from ..geo.impact import people_behind


def timeline(case: Case, award: str, completion: str, completion_basis: str, frames: list[dict], s2: dict) -> dict:
    r = case.record
    ev = [{"date": award, "kind": "award", "label": "Contract start", "source": "DPWH record"}]
    ev.append({"date": completion, "kind": "complete", "label": "Declared complete", "source": completion_basis})
    for f in frames:
        ev.append({"date": f["captured"], "kind": "capture", "label": f"{f.get('provider') or 'Optical'} capture",
                   "source": f"Esri Wayback release {f['release']}", "coverage": f.get("coverage")})
    fc = (s2 or {}).get("first_change")
    if fc:
        ev.append({"date": fc["date"], "kind": "first_change", "label": "Hard bank first appears (Sentinel-2)",
                   "source": "Sentinel-2 NDVI along the reach"})
    present = [f for f in case.findings if f.claim == "present"]
    first_seen = min((f.observed for f in present), default=None)
    flags = []
    if r.get("days") is not None and r.get("cost") and r["days"] < 120:
        flags.append(f"₱{r['cost'] / 1e6:.1f} million completed in {r['days']} days")
    if first_seen and first_seen < award:
        flags.append(f"structure first seen {first_seen}, before the contract started on {award}")
    if first_seen and first_seen > completion:
        flags.append(f"structure first seen {first_seen}, after it was declared complete on {completion}")
    out = {"events": sorted(ev, key=lambda e: e["date"]), "first_seen": first_seen, "flags": flags}
    case.record_entry("timeline", "timeline", out)
    case.say("timeline", "timeline", **out)
    return out


_overlaps = None
_recs = None


def prior_contracts(case: Case, award: str, radius_m: float = 200) -> list[dict]:
    """Other contracts whose published pins lie within `radius_m` of the located reach and which were
    completed before this contract started: works already paid for on the same bank."""
    global _recs
    from shapely.geometry import Point

    from ..geo.geom import to_m
    loc = case.facts.get("locator") or {}
    if not loc.get("located"):
        return []
    if _recs is None:
        _recs = json.loads((DATA / "portfolio/projects.json").read_text(encoding="utf-8"))
    rm = to_m(shape(loc["reach"]))
    out = []
    for r in _recs:
        if r["id"] == case.id or r.get("lon") is None or not r.get("completion") or r["completion"] >= award:
            continue
        if abs(r["lon"] - case.record["lon"]) > 0.02 or abs(r["lat"] - case.record["lat"]) > 0.02:
            continue
        d = to_m(Point(r["lon"], r["lat"])).distance(rm)
        if d <= radius_m:
            out.append({"id": r["id"], "distance_m": round(d), "completion": r["completion"], "cost": r.get("cost"),
                        "contractor": r.get("contractor"), "desc": r.get("desc")})
    return sorted(out, key=lambda x: x["distance_m"])


def same_barangay(case: Case) -> dict | None:
    """Every contract whose description names the barangay this one names, in the same municipality."""
    import re
    global _recs
    from ..geo.index import muni_key
    names = ((case.facts.get("locator") or {}).get("answer") or {}).get("barangays") or []
    if not names:
        return None
    if _recs is None:
        _recs = json.loads((DATA / "portfolio/projects.json").read_text(encoding="utf-8"))
    words = lambda t: " " + re.sub(r"[^a-z0-9ñ]+", " ", re.sub(r"\bsta\.?\s", "santa ", (t or "").lower())) + " "  # noqa: E731
    name = words(names[0]).strip()
    if len(name) < 3:
        return None
    pat = re.compile(rf"\b{re.escape(name)}\b")
    muni = muni_key(case.record.get("muni"))
    hits = [r for r in _recs if muni_key(r.get("muni")) == muni and pat.search(words(r.get("desc")))]
    if not hits:
        return None
    years = sorted({r.get("year") for r in hits if r.get("year")})
    return {"barangay": names[0], "n": len(hits), "php": round(sum(r.get("cost") or 0 for r in hits)),
            "years": [years[0], years[-1]] if years else None,
            "contractors": len({r.get("contractor") for r in hits}), "ids": [r["id"] for r in hits][:40]}


def valuation(case: Case, award: str | None = None) -> dict:
    global _overlaps
    r = case.record
    if _overlaps is None:
        p = DATA / "portfolio/overlaps.json"
        _overlaps = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    ov = [o for o in _overlaps if r["id"] in (o["a"], o["b"])]
    out = {
        "cost_php": r.get("cost"),
        "abc_php": r.get("abc"),
        "length_m": r.get("length_m"),
        "cost_per_m": r.get("cost_per_m"),
        "cost_per_m_pct": r.get("cost_per_m_pct"),
        "flags": r.get("flags", []),
        "overlaps": [{"other": o["b"] if o["a"] == r["id"] else o["a"], "overlap_m": o["overlap_m"],
                      "other_desc": o["b_desc"] if o["a"] == r["id"] else o["a_desc"],
                      "other_year": o["b_year"] if o["a"] == r["id"] else o["a_year"],
                      "other_cost": o["b_cost"] if o["a"] == r["id"] else o["a_cost"]} for o in ov],
        "same_amount": r.get("same_amount"),
        "prior": prior_contracts(case, award or r.get("start") or "9999"),
        "barangay_total": same_barangay(case),
    }
    case.record_entry("valuation", "valuation", out)
    case.say("valuation", "valuation", **out)
    return out


def impact(case: Case) -> dict:
    loc = case.facts.get("locator") or {}
    if not loc.get("located"):
        return {}
    res = people_behind(loc["reach"])
    cells = res.pop("cells")
    blob = case.blob(json.dumps(cells).encode(), "json")
    out = {**res, "cells_blob": blob, "n_cells": len(cells)}
    case.record_entry("impact", "impact", out)
    case.say("impact", "impact", **res, cells=cells[:4000])
    return out


def dates(record: dict, declaration: dict | None) -> tuple[str, str, str]:
    """Award and completion dates, and what the completion date rests on."""
    award = record.get("start") or f"{record.get('year') or 2024}-01-01"
    if record.get("completion"):
        return award, record["completion"], "DPWH record (completion date)"
    if declaration and declaration.get("declared_complete"):
        return award, declaration["declared_complete"], declaration["basis"]
    # No completion date published: assume a typical 240-day contract and say so.
    exp = (date.fromisoformat(award) + timedelta(days=240)).isoformat()
    return award, exp, "no completion date published; a typical 240-day contract term is assumed"


__all__ = ["timeline", "valuation", "impact", "dates", "shape"]
