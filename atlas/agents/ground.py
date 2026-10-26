"""Ground: street-level photos from Mapillary (Meta), dated, near the located reach.

A photo taken from the bank by a passer-by is a capture chain of its own: a
different camera, a different day, a different person. Muse Spark reads what
it shows; the photo's creator is its capture root.
"""
from __future__ import annotations

import base64
import json
import math
import os
from datetime import datetime, timezone

import httpx
from shapely.geometry import Point, shape

from ..case import DATA, Case
from ..geo.geom import buffer_m, to_m
from ..meta import SPARK
from ..verdict import Finding, window_of

AGENT = "ground"
API = "https://graph.mapillary.com/images"

READ = """You are reading a street-level photo for a public-works audit. A contract says a flood-control
structure (concrete river wall, revetment, slope protection or dike) was built on a riverbank near where this
photo was taken. Say literally what the photo shows. If no river or bank is visible, say so."""

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "river_visible": {"type": "boolean"},
        "bank_visible": {"type": "boolean"},
        "structure": {"type": "string", "enum": ["concrete or masonry wall", "earth dike", "no structure",
                                                 "under construction", "cannot tell"]},
        "what_i_see": {"type": "string"},
    },
    "required": ["river_visible", "bank_visible", "structure", "what_i_see"],
}


def _bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def run(case: Case, award: str, completion: str, max_photos: int = 3) -> list[dict]:
    tok = os.environ.get("MAPILLARY_TOKEN")
    loc = case.facts.get("locator") or {}
    if not tok or not loc.get("located"):
        return []
    reach = shape(loc["reach"])
    area = buffer_m(reach, 120)
    w, s, e, n = area.bounds
    cache = DATA / "cache/mapillary" / f"{case.id}.json"
    if cache.exists():
        items = json.loads(cache.read_text())
    else:
        r = httpx.get(API, params={"access_token": tok, "bbox": f"{w:.6f},{s:.6f},{e:.6f},{n:.6f}", "limit": 500,
                                   "fields": "id,captured_at,creator,compass_angle,computed_geometry,geometry,thumb_1024_url,is_pano"},
                      timeout=60)
        r.raise_for_status()
        items = r.json().get("data", [])
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(items))
    rm = to_m(reach)
    cands = []
    for it in items:
        g = it.get("computed_geometry") or it.get("geometry")
        if not g:
            continue
        p = Point(g["coordinates"])
        d = to_m(p).distance(rm)
        if d > 90:
            continue
        when = datetime.fromtimestamp(it["captured_at"] / 1000, tz=timezone.utc).date().isoformat()
        foot = rm.interpolate(rm.project(to_m(p)))
        from ..geo.geom import to_deg
        fd = to_deg(foot)
        facing = abs(((it.get("compass_angle") or 0) - _bearing((p.x, p.y), (fd.x, fd.y)) + 180) % 360 - 180)
        cands.append({"id": it["id"], "date": when, "distance_m": round(d), "facing_off_deg": round(facing),
                      "pano": bool(it.get("is_pano")), "lonlat": [p.x, p.y], "url": it.get("thumb_1024_url"),
                      "creator": (it.get("creator") or {}).get("username") or (it.get("creator") or {}).get("id")})
    after = [c for c in cands if c["date"] > completion]
    after.sort(key=lambda c: (not c["pano"] and c["facing_off_deg"] > 70, c["distance_m"]))
    picked = after[:max_photos]
    case.say(AGENT, "photos", found=len(cands), after_completion=len(after), picked=[c["id"] for c in picked])
    out = []
    for c in picked:
        img = httpx.get(c["url"], timeout=60).content
        blob = case.blob(img, "jpg")
        h = case.record_entry(AGENT, "photo", {k: v for k, v in c.items() if k != "url"} | {"blob": blob,
                                                                                           "licence": "CC BY-SA 4.0 (Mapillary)"})
        reading = None
        if case.meta:
            res = case.meta.structured(case.facts.get("spark", SPARK), READ, [
                {"type": "input_text", "text": f"Contract: {case.record['desc']}. Photo taken {c['date']}, "
                                               f"{c['distance_m']} m from the located reach."},
                {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(img).decode()}],
                SCHEMA, schema_name="street_reading", effort="low", est_usd=0.01)
            reading = res["data"]
            case.record_entry(AGENT, "photo_reading", {"model": case.facts.get("spark", SPARK), "photo": c["id"], "answer": reading})
        c = {**c, "blob": blob, "reading": reading, "entry": h, "window": window_of(c["date"], award, completion)}
        out.append(c)
        case.say(AGENT, "photo", **{k: v for k, v in c.items() if k != "url"})
        if reading and reading["bank_visible"]:
            claim = {"concrete or masonry wall": "present", "earth dike": "present", "no structure": "absent"}.get(
                reading["structure"], "inconclusive")
            q = 0.8 if c["distance_m"] < 40 else 0.65
            case.file(Finding(AGENT, f"Mapillary {c['date']} (street photo, {c['distance_m']} m away)", "street",
                              f"mapillary:{c['creator']}", c["date"], claim, q, reading["what_i_see"][:200], h))
        elif reading:
            case.file(Finding(AGENT, f"Mapillary {c['date']} (street photo)", "street", f"mapillary:{c['creator']}",
                              c["date"], "inconclusive", 0.0, "the bank is not visible in the photo", h))
    return out
