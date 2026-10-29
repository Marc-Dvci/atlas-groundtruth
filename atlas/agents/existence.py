"""Existence: is the structure there, and since when?

Two independent capture chains look at the located reach:

* Sub-metre optical history (Esri Wayback; Maxar, Airbus and other providers):
  SAM 3.1 segments walls in every distinct capture, code measures how much of
  the reach the masks cover, and Muse Spark compares the capture before the
  award with the capture after completion, looking along the reach line.
* Sentinel-2 (ESA, 10 m, every 5 days): NDVI along a narrow corridor of the
  reach, to date the first appearance of a hard bank and to testify about
  absence when a wall would have been resolvable.

Every chip, mask and model answer is sealed in the ledger.
"""
from __future__ import annotations

import io
import json
import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from PIL import Image
from shapely.geometry import LineString, Point, mapping, shape

from ..case import DATA, Case
from ..geo import s2series
from ..geo.geom import bbox_around, buffer_m, to_deg, to_m
from ..geo.raster import Chip, full_mask, longest_skeleton_path, zhang_suen
from ..geo.wayback import Wayback, metres_per_px
from ..meta import SPARK, segment_image
from ..verdict import Finding, window_of

AGENT = "existence"
# Calibrated on Bulacan captures (26 Oct): SAM 3.1 needs a plain concept. "riverbank" segments hard,
# engineered banks (dikes, revetments, paved edges) and leaves vegetated banks alone; "wall", "levee",
# "dike", "revetment" and "flood wall" return nothing; "concrete" returns roads. "river" gives the water.
WALL_PROMPTS = ["riverbank"]
WATER_PROMPT = "river"
COVER_PRESENT, COVER_ABSENT = 0.30, 0.10
# The mission's as-of date: the Sentinel-2 series ends here, so a replay reads the same cached series.
AS_OF = os.environ.get("ATLAS_AS_OF") or date.today().isoformat()
Z = 18

JUDGE = """You are an imagery analyst in a public-works audit. You get satellite images of one riverbank
site, each with a cyan line marking the reach where a contract says a flood-control structure
(a concrete wall, revetment or dike) was built. Captures from different dates can be misaligned by
up to 30-50 m, so judge the banks near the line, not the exact pixels under it.

The contract does not say which bank, so read BOTH banks beside the line, one at a time, and name each
by its compass side (for example west and east). For each bank say what its edge is: natural or
vegetated, bare earth, concrete or masonry (a hard, smooth, light-grey edge, often with a road or fence
on top), under construction (equipment, cleared strips, stockpiles), or not visible (cloud, shadow,
blur); whether a structure like the one described runs along it; and along what share of the line.
Compare each bank with the same bank in the other captures. At this resolution a new concrete wall is often
thin: one continuous, smooth, light-grey line along the water's edge, frequently with a freshly cleared or
backfilled strip of bare earth behind it where trees, shacks or debris stood in earlier captures. Count that as
the structure. A road set back from the water, or houses built up to the water, is not one.

Then summarise each image over both banks: structure_visible is "yes" if either bank has the structure
along most of the line, "partly" if along part of it; "bank" is the edge type of the bank that has it
(or of the more built-up bank). Be literal. Do not assume the contract is true or false."""

JUDGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "images": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "date": {"type": "string"},
                    "banks": {"type": "array", "minItems": 2, "maxItems": 2, "items": {
                        "type": "object", "additionalProperties": False,
                        "properties": {"side": {"type": "string"},
                                       "edge": {"type": "string", "enum": ["natural or vegetated", "bare earth",
                                                                          "concrete or masonry", "under construction",
                                                                          "not visible"]},
                                       "structure": {"type": "string", "enum": ["yes", "partly", "no", "cannot tell"]},
                                       "extent_fraction": {"type": "number"}},
                        "required": ["side", "edge", "structure", "extent_fraction"]}},
                    "bank": {"type": "string", "enum": ["natural or vegetated", "bare earth", "concrete or masonry",
                                                        "under construction", "not visible"]},
                    "structure_visible": {"type": "string", "enum": ["yes", "partly", "no", "cannot tell"]},
                    "extent_fraction": {"type": "number", "description": "share of the line with a structure on either bank, 0 to 1"},
                    "quality": {"type": "string", "enum": ["good", "fair", "poor"]},
                    "what_i_see": {"type": "string"},
                },
                "required": ["date", "banks", "bank", "structure_visible", "extent_fraction", "quality", "what_i_see"],
            },
        },
        "change": {"type": "string", "enum": ["structure built between captures", "no change", "structure removed",
                                               "cannot tell"]},
        "summary": {"type": "string"},
    },
    "required": ["images", "change", "summary"],
}

# The second reader: a different model, one decisive capture at a time beside a reference from before the award,
# a narrower question. A decisive reading counts only when both readers agree on it.
CROSS = """You are checking a satellite image for a public-works audit. A cyan line marks a river reach where a
contract says a flood-control structure (a concrete wall, revetment or dike along the bank) was built. Images can be
misaligned by 30-50 m, and the contract does not say which bank, so look at both banks beside the line{ref_look}. At
this resolution a concrete wall is often thin: one continuous, smooth, light-grey line along the water's edge, often
with a road, path or cleared strip behind it. A road set back from the water, or houses built up to the water, is not
one. In the capture to judge{last}, is such a structure present along most of the line, on either bank{whether}? Answer
literally; say "cannot tell" when cloud, haze or blur hides the banks."""
# With a reference (an earlier capture from before the award) the second reader can compare, as the first one does.
CROSS_REF = {"ref_look": ", and compare each bank with the same bank in the reference", "last": " (the last image)",
             "whether": ", whether or not it was already in the reference"}
CROSS_ALONE = {"ref_look": "", "last": "", "whether": ""}

CROSS_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"structure": {"type": "string", "enum": ["yes", "partly", "no", "cannot tell"]},
                   "what_i_see": {"type": "string"}},
    "required": ["structure", "what_i_see"],
}

_wb: Wayback | None = None


def wayback() -> Wayback:
    global _wb
    _wb = _wb or Wayback(DATA / "cache/wayback")
    return _wb


def captures(lon: float, lat: float) -> list[dict]:
    """Distinct acquisitions (by capture date) under a point, oldest first."""
    wb = wayback()
    seen: dict[str, dict] = {}
    for rel in wb.distinct_releases(lon, lat, Z):
        c = wb.capture(rel, lon, lat, Z)
        key = c.captured or f"release {c.release_date}"
        # the newest release holding a capture renders it best; keep the first seen (newest first)
        seen.setdefault(key, {"release": c.release, "captured": c.captured, "release_date": c.release_date,
                              "sensor": c.sensor, "resolution_m": c.resolution_m, "provider": c.provider})
    return sorted(seen.values(), key=lambda c: c["captured"] or c["release_date"])


def site_bbox(reach: LineString, margin_m: float = 90) -> tuple[float, float, float, float]:
    rm = to_m(reach)
    minx, miny, maxx, maxy = rm.bounds
    half = max(maxx - minx, maxy - miny) / 2 + margin_m
    c = to_deg(Point((minx + maxx) / 2, (miny + maxy) / 2))
    return bbox_around((c.x, c.y), half)


# A new wall can be one pixel wide at z18 (0.58 m), so a chip keeps native pixels for a reach up to about 1 km;
# a 1,024 px cap halved them on long reaches and hid thin walls.
MAX_CHIP_PX = 2048


def chip_for(release: int, bbox) -> Chip:
    img = wayback().mosaic(release, bbox, Z)
    if max(img.size) > MAX_CHIP_PX:
        s = MAX_CHIP_PX / max(img.size)
        img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    return Chip(img, bbox)


def wall_masks(case: Case, chip: Chip, reach: LineString) -> dict:
    """SAM 3.1 on one chip: hard-bank masks (structures) and the water itself; bank coverage per side."""
    polys, raw, water = [], [], []
    img = chip.jpeg()
    for prompt in WALL_PROMPTS + [WATER_PROMPT]:
        for o in segment_image(case.meta, img, prompt):
            m = o.mask()
            g = chip.mask_to_geo(m, o.box) if m is not None else chip.box_to_geo(o.box)
            if g is None or g.is_empty:
                continue
            rec = {"prompt": prompt, "object": o.object_id, "confidence": o.confidence, "decoded": m is not None, "geom": g}
            (water if prompt == WATER_PROMPT else polys).append(rec)
            raw.append({"prompt": prompt, "object": o.object_id, "box": o.box, "confidence": o.confidence,
                        "mask_hw": o.mask_hw, "decoded": m is not None})
    sides = bank_coverage(reach, [p["geom"] for p in polys])
    return {"polys": polys, "water": water, "raw": raw, "coverage": max(sides.values()) if sides else 0.0, "sides": sides}


def bank_coverage(reach: LineString, polys: list, reach_m: float = 70, step_m: float = 10) -> dict:
    """Share of the reach with a hard-bank mask within `reach_m` on each side (left/right of travel)."""
    import math
    from shapely.ops import unary_union
    if not polys:
        return {"left": 0.0, "right": 0.0}
    hard = to_m(unary_union(polys))
    rm = to_m(reach)
    n = max(2, int(rm.length // step_m))
    hit = {"left": 0, "right": 0}
    for i in range(n):
        d = rm.length * (i + 0.5) / n
        p, q = rm.interpolate(max(0, d - 2)), rm.interpolate(min(rm.length, d + 2))
        dx, dy = q.x - p.x, q.y - p.y
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L  # left normal
        c = rm.interpolate(d)
        for side, sgn in (("left", 1), ("right", -1)):
            ray = LineString([(c.x, c.y), (c.x + sgn * nx * reach_m, c.y + sgn * ny * reach_m)])
            if ray.intersects(hard):
                hit[side] += 1
    return {k: round(v / n, 3) for k, v in hit.items()}


def trace_river(case: Case, lon: float, lat: float) -> dict:
    """Locator tool: river centreline from the newest capture, via SAM 3.1 'river'."""
    from ..geo.index import get_index
    caps = captures(lon, lat)
    if not caps:
        return {"error": "no imagery at this point"}
    cap = caps[-1]
    bbox = bbox_around((lon, lat), 300)
    chip = chip_for(cap["release"], bbox)
    objs = segment_image(case.meta, chip.jpeg(), "river")
    best = None
    for o in objs:
        m = o.mask()
        if m is None:
            continue
        fm = full_mask(m, o.box, (chip.w, chip.h))
        if best is None or fm.sum() > best.sum():
            best = fm
    if best is None:
        return {"error": "SAM 3.1 found no river channel here"}
    path = longest_skeleton_path(zhang_suen(best))
    if len(path) < 10:
        return {"error": "river mask too small to trace"}
    pts = [chip.to_lonlat(x + 0.5, y + 0.5) for x, y in path[:: max(1, len(path) // 60)]]
    line = to_deg(to_m(LineString(pts)).simplify(4))
    wid = f"img{len(get_index().extra) + 1}"
    get_index().add_traced(wid, line, f"traced by SAM 3.1 on {cap['captured']} imagery")
    blob = case.blob(chip.with_line(line, (255, 241, 220), 3, f"traced {cap['captured']}"), "jpg")
    case.record_entry(AGENT, "river_traced", {"waterway_id": wid, "capture": cap, "line": mapping(line), "blob": blob})
    case.say("locator", "traced", line=mapping(line), blob=blob, captured=cap["captured"])
    return {"waterway_id": wid, "length_m": round(to_m(line).length), "captured": cap["captured"],
            "distance_from_pin_m": round(to_m(Point(case.record["lon"], case.record["lat"])).distance(to_m(line)))}


def _quality(q: str, res: float | None) -> float:
    base = {"good": 0.9, "fair": 0.7, "poor": 0.4}.get(q, 0.5)
    return round(base * (1.0 if (res or 0.6) <= 1.0 else 0.7), 2)


def run_optical(case: Case, award: str, completion: str) -> list[dict]:
    loc = case.facts["locator"]
    reach = shape(loc["reach"])
    c = reach.interpolate(0.5, normalized=True)
    caps = [k for k in captures(c.x, c.y) if k["captured"]]
    if case.facts.get("depth") == "full":
        caps = caps[-12:]  # the whole history the film shows (sub-metre captures since ~2010), seven distinct at most
    else:  # screening: the last capture before the award and everything after it
        before = [k for k in caps if k["captured"] < award]
        caps = before[-1:] + [k for k in caps if k["captured"] >= award]
    bbox = site_bbox(reach)
    # Wayback can list one area under several capture dates while serving the same pixels. Identical pixels are one
    # capture: keep it under its earliest date and record the other dates, so no frame carries a date its pixels lack.
    chips, same = [], {}
    for cap in caps:
        if not cap["captured"]:
            continue
        chip = chip_for(cap["release"], bbox)
        blob = case.blob(chip.jpeg(), "jpg")
        if blob in same:
            same[blob].append(cap["captured"])
            continue
        same[blob] = []
        chips.append((cap, chip, blob))
    if case.facts.get("depth") == "full":
        chips = chips[-7:]
    case.say(AGENT, "captures", captures=[c for c, _, _ in chips])
    frames = []
    for cap, chip, blob in chips:
        win = window_of(cap["captured"], award, completion)
        sam = wall_masks(case, chip, reach) if case.meta else {"polys": [], "raw": [], "coverage": None}
        masks = [{"prompt": p["prompt"], "object": p["object"], "confidence": p["confidence"],
                  "geometry": mapping(p["geom"])} for p in sam["polys"] + sam.get("water", [])]
        h = case.record_entry(AGENT, "capture", {"capture": cap, "window": win, "bbox": bbox, "blob": blob,
                                                 "same_pixels_listed_as": same[blob],
                                                 "sam": sam["raw"], "coverage": sam["coverage"], "sides": sam.get("sides")})
        fr = {**cap, "window": win, "bbox": bbox, "blob": blob, "masks": masks, "coverage": sam["coverage"],
              "sides": sam.get("sides"), "same_pixels_listed_as": same[blob],
              "entry": h, "chip": chip, "mpp": metres_per_px(c.y, Z)}
        frames.append(fr)
        case.say(AGENT, "frame", **{k: v for k, v in fr.items() if k != "chip"})
    # Muse Spark reads every capture in one pass, oldest first, the reach drawn on each.
    verdicts = {}
    if case.meta and frames:
        content = [{"type": "input_text", "text": json.dumps({
            "contract": case.record["desc"], "declared_length_m": loc.get("declared_length_m"),
            "award_date": award, "completion_date": completion,
            "images_in_order": [f["captured"] for f in frames]})}]
        for f in frames:
            content.append({"type": "input_text", "text": f"Capture {f['captured']} ({f['sensor'] or 'unknown sensor'}, "
                                                          f"{f['resolution_m'] or '?'} m)"})
            content.append({"type": "input_image", "image_url": "data:image/jpeg;base64," + __import__("base64").b64encode(
                f["chip"].with_line(reach)).decode()})
        res = case.meta.structured(case.facts.get("spark", SPARK), JUDGE, content, JUDGE_SCHEMA, schema_name="bank_reading", effort="medium",
                                   est_usd=0.05)
        ans = res["data"]
        case.record_entry(AGENT, "imagery_reading", {"model": case.facts.get("spark", SPARK), "answer": ans})
        case.say(AGENT, "reading", **ans)
        for im in ans.get("images", []):
            verdicts[im["date"][:10]] = im
    # One claim per capture. The reading (Muse Spark) says WHAT is on the bank; the SAM 3.1 masks say
    # WHERE, and their agreement is recorded. SAM's "riverbank" also fires on some natural banks, so a mask
    # alone never makes a claim.
    first = {}
    for f in frames:
        v = verdicts.get(f["captured"][:10])
        cov = f["coverage"]
        cov_txt = f"hard-bank masks on {cov:.0%} of the reach" if cov is not None else "no masks"
        if v is None:
            claim, why, q = "inconclusive", "no model reading for this capture", 0.0
        elif v["bank"] == "not visible" or v["structure_visible"] == "cannot tell":
            claim, why, q = "inconclusive", f"reading: {v['bank']}", 0.0
        elif v["structure_visible"] in ("yes", "partly") and v["extent_fraction"] >= 0.3:
            claim, q = "present", _quality(v["quality"], f["resolution_m"])
            why = f"reading: {v['bank']}, structure along {v['extent_fraction']:.0%} of the reach; {cov_txt}"
            if cov is not None and cov < COVER_ABSENT:
                q = round(q * 0.8, 2)
                why += " (masks disagree)"
        elif v["structure_visible"] == "no":
            claim, q = "absent", _quality(v["quality"], f["resolution_m"])
            why = f"reading: {v['bank']}, no structure along the reach; {cov_txt}"
            if cov is not None and cov >= COVER_PRESENT:
                q = round(q * 0.8, 2)
                why += " (masks disagree)"
        else:
            claim, why, q = "inconclusive", f"reading: structure {v['structure_visible']} on {v['extent_fraction']:.0%}", 0.4
        first[f["captured"]] = (v, claim, why, q)
    # Every claim that can decide a verdict (any capture before the award, any after completion) goes to a second
    # reader, and counts only when that reader explicitly agrees.
    from ..meta import label
    primary = case.facts.get("spark", SPARK)
    second = second_reader(case)
    todo = [f for f in frames if (f["window"] in DECISIVE and first[f["captured"]][1] in ("present", "absent"))
            or (f["window"] == "during_contract" and first[f["captured"]][1] == "absent")]
    cross, missing = cross_read(case, second, frames, todo, reach)
    checked = {id(f) for f in todo}
    for f in frames:
        v, claim, why, q = first[f["captured"]]
        x = cross.get(f["captured"])
        if id(f) in checked:
            claim, why, q = confirm(claim, why, q, x, missing.get(f["captured"]), label(primary))
        f["reading"] = v
        f["cross"] = x
        case.file(Finding(
            agent=AGENT,
            source=f"{f['provider'] or 'Wayback'} {f['captured']} ({f['sensor'] or 'optical'}, {f['resolution_m'] or '?'} m)",
            family="optical_vhr", capture_root=_root(f), observed=f["captured"], claim=claim, quality=q,
            note=why, entry=f["entry"]))
    for f in frames:
        f.pop("chip", None)
    return frames


# Windows whose readings can decide a verdict. Inside the contract only a bare capture can: verdict.py counts it when
# Sentinel-2 shows nothing built on the bank from then until after the completion ("bare, then unchanged").
DECISIVE = ("before_award", "after_completion")


def second_reader(case: Case) -> str | None:
    """The model that re-reads every decisive claim, or None when no host for it is configured."""
    from ..meta import OPEN
    return OPEN if case.meta is not None and case.meta.open_key else None


def cross_read(case: Case, second: str | None, frames: list[dict], todo: list[dict],
               reach: LineString) -> tuple[dict[str, dict], dict[str, str]]:
    """Second readings of `todo`, each beside the capture before it from before the award. Returns the readings by
    capture date, and why a reading is missing for the others."""
    from concurrent.futures import ThreadPoolExecutor

    from ..meta import label
    if not todo:
        return {}, {}
    if second is None:
        return {}, {f["captured"]: "no second reader is configured" for f in todo}
    b64 = lambda fr: "data:image/jpeg;base64," + __import__("base64").b64encode(fr["chip"].with_line(reach)).decode()  # noqa: E731

    def ask(f: dict) -> tuple[dict | None, dict | None, str]:
        ref = [r for r in frames if r["window"] == "before_award" and r["captured"] < f["captured"]][-1:]
        content = [{"type": "input_text", "text": f"Contract: {case.record['desc']}."}]
        for r in ref:
            content += [{"type": "input_text", "text": f"Reference: capture of {r['captured']}, before the contract."},
                        {"type": "input_image", "image_url": b64(r)}]
        content += [{"type": "input_text", "text": f"The capture to judge: {f['captured']}."},
                    {"type": "input_image", "image_url": b64(f)}]
        try:
            res = case.meta.structured(second, CROSS.format(**(CROSS_REF if ref else CROSS_ALONE)), content,
                                       CROSS_SCHEMA, schema_name="cross_reading", effort="low", est_usd=0.01)
        except Exception as e:
            return None, ref[0] if ref else None, f"the second reading failed ({type(e).__name__})"
        return res["data"] or {}, ref[0] if ref else None, ""

    with ThreadPoolExecutor(4) as ex:
        answers = list(ex.map(ask, todo))
    cross, missing = {}, {}
    for f, (x, ref, err) in zip(todo, answers):  # sealed in capture order, whatever order the answers came back in
        if x is None:
            case.record_entry(AGENT, "cross_reading_failed", {"capture": f["captured"], "error": err})
            missing[f["captured"]] = err
        elif x.get("structure") in ("yes", "partly", "no", "cannot tell"):
            cross[f["captured"]] = {**x, "model": label(second), "reference": ref["captured"] if ref else None}
            case.record_entry(AGENT, "cross_reading", {"model": second, "capture": f["captured"], "answer": x})
        else:
            missing[f["captured"]] = "the second reading gave no answer"
    return cross, missing


def confirm(claim: str, why: str, q: float, x: dict | None, missing: str | None, primary: str) -> tuple[str, str, float]:
    """A decisive claim stands only when the second reader says the same thing. A second reader that contradicts it,
    cannot tell, gave no answer or is not configured leaves the capture inconclusive, with the reason."""
    if x is None:
        return "inconclusive", f"{why}; not confirmed: {missing or 'no second reading'}", 0.0
    other_yes, other_no = x["structure"] in ("yes", "partly"), x["structure"] == "no"
    if (claim == "present" and other_yes) or (claim == "absent" and other_no):
        return claim, f"{why}; {x['model']} agrees", q
    if other_yes or other_no:
        return "inconclusive", (f"readers disagree: {primary} reads {claim}, {x['model']} reads "
                                f"'{x['structure']}' ({x['what_i_see'][:120]})"), 0.0
    return "inconclusive", f"{why}; not confirmed: {x['model']} cannot tell ({x['what_i_see'][:120]})", 0.0


def _root(f: dict) -> str:
    """Capture chain for the independence rule. DigitalGlobe, Maxar and Vantor are one company's
    constellation (WorldView, GeoEye, Legion): every capture from it counts as one source."""
    prov = (f.get("provider") or "").lower()
    s = (f.get("sensor") or "").upper()
    if any(k in prov for k in ("maxar", "digitalglobe", "vantor")) or s.startswith(("WV", "GE", "QB", "IK", "LG")):
        return "maxar"
    if "airbus" in prov or s.startswith(("PL", "PNEO", "SPOT")):
        return "airbus"
    return f"vhr:{prov or s or f.get('release')}"


def run_s2(case: Case, award: str, completion: str) -> dict:
    loc = case.facts["locator"]
    reach = shape(loc["reach"])
    # full depth: four years before the award; screening: two and a half, still two seasons of each kind for the baseline
    years = 4 if case.facts.get("depth") == "full" else 2.5
    start = max("2019-01-01", (date.fromisoformat(award) - timedelta(days=int(years * 365))).isoformat())
    # screening reads the clearest scene of each month, full depth the two clearest
    full = case.facts.get("depth") == "full"
    rows = s2series.series(mapping(reach), start, AS_OF, DATA / "cache/s2", workers=12 if full else 24,
                           per_month=2 if full else 1)
    rows = [r for r in rows if r.get("ndvi") is not None]
    before = s2series.window_stats(rows, None, award)
    after = s2series.window_stats(rows, (date.fromisoformat(completion) + timedelta(days=30)).isoformat(), None)
    change = s2series.first_change_any_bank(rows)
    stir = None if change else s2series.disturbance_any_bank(rows, after=award)
    banks = s2series.side_stats(rows, None, award)
    out = {"rows": rows, "before": before, "after": after, "first_change": change, "disturbance": stir, "banks_before": banks}
    h = case.record_entry(AGENT, "s2_series", {"before": before, "after": after, "first_change": change, "disturbance": stir,
                                               "banks_before": banks, "n": len(rows)})
    case.say(AGENT, "s2", before=before, after=after, first_change=change, disturbance=stir, banks_before=banks,
             rows=[{k: r[k] for k in ("date", "ndvi", "bright")} for r in rows])
    if not before or not after or after["n"] < 4:
        case.file(Finding(AGENT, "Sentinel-2 (ESA), 10 m", "optical_hr", "s2", completion, "inconclusive", 0.0,
                          "too few clear scenes along the reach", h))
        return out
    # Detectability: a wall on a vegetated bank drops NDVI; on a bank already bare it barely shows. The wall may be on
    # either bank, so the barer bank sets how much an unchanged series can say.
    floor = min(banks.values()) if banks else before["ndvi"]
    detect = min(1.0, max(0.0, (floor - 0.15) / 0.3))
    # a change is dated to a season (first to last clear scene of it); it is "before the award" only if the whole
    # season ended before it, and a season that straddles the award is dated to the contract window
    clear_before = (date.fromisoformat(award) - timedelta(days=60)).isoformat()
    straddles = bool(change) and change["date"] < award and change["last"] >= clear_before
    if change and change["last"] < clear_before:
        claim, note = "present", (f"bank changed between {change['date']} and {change['last']} on the {change['bank']}, "
                                  f"before the award")
    elif change:
        claim, note = "present", (f"bank changed between {change['date']} and {change['last']} on the {change['bank']} "
                                  f"(NDVI {change['ndvi_before']} to {change['ndvi_after']})")
    elif stir:
        claim, note = "inconclusive", (f"work-like disturbance on the {stir['bank']} from {stir['date']} (NDVI {stir['ndvi_before']} "
                                       f"to {stir['ndvi_after']}), then regrowth; 10 m pixels cannot tell whether a wall stands")
    else:
        claim, note = "absent", (f"no lasting change on either bank: NDVI {before['ndvi']} before the award, "
                                 f"{after['ndvi']} after completion ({after['n']} clear scenes)")
    # a change is dated by its first scene; an unchanged bank testifies as of the last scene
    when = ((date.fromisoformat(award) + timedelta(days=1)).isoformat() if straddles else change["date"]) if change else         stir["date"] if stir else after["to"]
    q = round(0.5 + 0.4 * detect, 2) if claim == "absent" else 0.8 if claim == "present" else 0.0
    # a change is a season below the same season in earlier years, so the series can show one only from its second year
    since = (date.fromisoformat(rows[0]["date"]) + timedelta(days=365)).isoformat() if claim == "absent" else ""
    case.file(Finding(AGENT, f"Sentinel-2 (ESA) {when[:7]}, 10 m", "optical_hr", "s2", when, claim, q, note, h, since=since))
    return out
