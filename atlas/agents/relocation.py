"""Relocation search: the wall isn't where the contract says. Was it built somewhere else?

Triggered when sub-metre imagery shows the declared reach bare after completion.
Atlas walks the same waterway 1.5 km each way, compares SAM 3.1 hard-bank masks
in the last capture before the award with the first after completion, keeps
banks that turned hard in between, and asks Muse Spark to confirm the best
candidate. The DPWH itself said 337 of 416 flagged projects "exist but at a
different location": this is how to find them.
"""
from __future__ import annotations

import base64
import json

from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import substring, unary_union

from ..case import Case
from ..geo.geom import bbox_around, buffer_m, to_deg, to_m
from ..meta import SPARK, segment_image
from ..verdict import Finding
from .existence import Z, _root, captures, chip_for

AGENT = "relocation"
SPAN_M, STEP_M, WIN_M = 1500, 380, 260

CONFIRM = """Two satellite images of the same riverbank window, before a flood-control contract was awarded and
after it was declared complete. Captures can be misaligned by tens of metres. Was a new concrete wall, revetment
or dike built along the river between the two dates? Answer literally."""
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "new_structure": {"type": "string", "enum": ["yes", "no", "cannot tell"]},
        "where": {"type": "string", "description": "which bank and which part of the image"},
        "what_i_see": {"type": "string"},
    },
    "required": ["new_structure", "where", "what_i_see"],
}


def _hard(case: Case, chip) -> list:
    out = []
    for o in segment_image(case.meta, chip.jpeg(), "riverbank"):
        m = o.mask()
        g = chip.mask_to_geo(m, o.box) if m is not None else None
        if g is not None and not g.is_empty:
            out.append(g)
    return out


def run(case: Case, award: str, completion: str, waterway_geo: dict) -> dict | None:
    loc = case.facts["locator"]
    reach = shape(loc["reach"])
    line = to_m(shape(waterway_geo) if waterway_geo else reach)
    if line.geom_type != "LineString":
        line = max(getattr(line, "geoms", [line]), key=lambda g: g.length)
    c = line.project(to_m(reach.interpolate(0.5, normalized=True)))
    a, b = max(0.0, c - SPAN_M), min(line.length, c + SPAN_M)
    corridor = substring(line, a, b)
    declared = buffer_m(reach, 60)
    caps = [k for k in captures(*reach.interpolate(0.5, normalized=True).coords[0]) if k["captured"]]
    before = [k for k in caps if k["captured"] < award][-1:]
    after = [k for k in caps if k["captured"] > completion][:1]
    if not before or not after:
        return None
    b_rel, a_rel = before[0], after[0]
    case.say(AGENT, "start", text=f"walking {round((b - a) / 1000, 1)} km of the waterway", before=b_rel["captured"],
             after=a_rel["captured"])
    windows, new_polys = [], []
    d = 0.0
    while d <= corridor.length:
        p = to_deg(corridor.interpolate(d))
        bb = bbox_around((p.x, p.y), WIN_M)
        cb, ca = chip_for(b_rel["release"], bb), chip_for(a_rel["release"], bb)
        hb, ha = _hard(case, cb), _hard(case, ca)
        old = buffer_m(unary_union(hb), 15) if hb else None
        # new hard bank = hard after, not hard before, and not on the declared reach (that is the other agents' job)
        fresh = [g.difference(old) if old is not None else g for g in ha]
        fresh = [g.difference(declared) for g in fresh if not g.is_empty]
        fresh = [g for g in fresh if not g.is_empty and to_m(g).area > 400]
        length = sum(max(to_m(g).bounds[2] - to_m(g).bounds[0], to_m(g).bounds[3] - to_m(g).bounds[1]) for g in fresh)
        windows.append({"center": [p.x, p.y], "bbox": bb, "new_len_m": round(length), "d_m": round(d - (c - a))})
        for g in fresh:
            new_polys.append({"geom": g, "window": len(windows) - 1})
        case.say(AGENT, "window", center=[p.x, p.y], bbox=bb, new_len_m=round(length), offset_m=round(d - (c - a)))
        d += STEP_M
    if not windows:
        return None
    best = max(windows, key=lambda w: w["new_len_m"])
    declared_len = loc.get("declared_length_m") or loc.get("length_m") or 150
    result = {"windows": windows, "best": best, "before": b_rel["captured"], "after": a_rel["captured"],
              "new_hard_banks": [mapping(x["geom"]) for x in new_polys]}
    if best["new_len_m"] < 0.4 * declared_len:
        case.record_entry(AGENT, "relocation_search", {k: v for k, v in result.items() if k != "new_hard_banks"} | {"found": False})
        case.say(AGENT, "none", text="no new hard bank of comparable length along the waterway")
        result["found"] = False
        return result
    cb, ca = chip_for(b_rel["release"], best["bbox"]), chip_for(a_rel["release"], best["bbox"])
    blob_b, blob_a = case.blob(cb.jpeg(), "jpg"), case.blob(ca.jpeg(), "jpg")
    res = case.meta.structured(case.facts.get("spark", SPARK), CONFIRM, [
        {"type": "input_text", "text": f"Before: {b_rel['captured']}"},
        {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(cb.jpeg()).decode()},
        {"type": "input_text", "text": f"After: {a_rel['captured']}"},
        {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(ca.jpeg()).decode()}],
        SCHEMA, schema_name="relocation", effort="medium", est_usd=0.02)
    ans = res["data"]
    dist = round(to_m(Point(best["center"])).distance(to_m(reach)))
    found = ans["new_structure"] == "yes"
    result.update({"found": found, "confirm": ans, "distance_m": dist, "blob_before": blob_b, "blob_after": blob_a})
    h = case.record_entry(AGENT, "relocation_search", {k: v for k, v in result.items() if k != "new_hard_banks"})
    case.say(AGENT, "candidate", center=best["center"], distance_m=dist, found=found, reading=ans,
             new_hard_banks=result["new_hard_banks"][:40])
    if found:
        case.file(Finding(AGENT, f"{a_rel['provider'] or 'Wayback'} {a_rel['captured']} ({a_rel['sensor']}, {a_rel['resolution_m']} m), "
                                 f"{dist} m along the waterway", "optical_vhr", _root(a_rel), a_rel["captured"], "present", 0.85,
                          f"new hard bank built between {b_rel['captured']} and {a_rel['captured']}: {ans['what_i_see'][:160]}",
                          h, site=f"elsewhere:{dist} m from the declared reach, on the same waterway"))
    return result


__all__ = ["run", "Z", "LineString", "bbox_around", "buffer_m"]
