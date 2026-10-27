"""Locator: find the real site from the contract text, not from the published pin.

The DPWH told the Senate its own coordinates "take us to the wrong places most
of the time". The contract description is better: it names the barangay, the
river, sometimes the section, the purok and the stations. Muse Spark reads it
and works through spatial tools; code builds the geometry and measures how far
the published pin is from the site the text describes.
"""
from __future__ import annotations

import json
import re
from typing import Any

from shapely.geometry import Point, mapping

from ..case import DATA, Case
from ..geo.geom import buffer_m, chainage_ticks, haversine_m, to_m
from ..geo.index import GeoIndex, longest_line, norm, reach_on
from ..meta import SPARK, Tool, Turn, label

AGENT = "locator"
DEFAULT_LENGTH_M = 250.0
_corpus: list[dict] | None = None

INSTRUCTIONS = """You are the Locator in a public-works audit. A government contract says a flood-control
structure was built. Your job is to find WHERE, from the contract's own words, because the published
map pin is often wrong (officials testified the coordinates "take us to the wrong places most of the time").

Read the description the way a Philippine public-works engineer would:
- "Barangay X" / "Brgy. X" names the village; "Purok N" and "Sitio X" are parts of it.
- "X River", "X Creek", "Bagbag Creek (Tributary)", "X Section" (a named stretch, usually a barangay name) say which water.
- "Sta. 1+200 to Sta. 1+500" or "K003+690" are stations along the river in km+m. Their origin is not published,
  so stations give the LENGTH of the works (here 300 m), not an absolute position.
- Several barangays ("Sta. Elena - San Pedro") mean the works run between them.

Choose the waterway by this order of evidence, and say in the reasoning which step you used:
1. A river or creek the contract names, inside or along the named barangay.
2. If the contract names none, call contracts_in_barangay: the river or creek that other contracts for the same
   barangay name (several phases of one programme usually share a river), inside or along the barangay.
3. If neither names one, the waterway at the published pin, when the pin is inside the named barangay and within
   about 150 m of it.
4. Otherwise the longest mapped waterway inside the named barangay, or a channel traced from satellite imagery when
   the map has none where the text puts the works.
Within the chosen waterway, centre the reach near the pin only if the pin is within about 300 m of it; otherwise
centre it inside the barangay. Confidence: high for step 1 with stations, medium for steps 1-2, low for steps 3-4.
Never invent places. Say the site is not locatable only when no waterway in or near the named barangay could hold
the works, and say why.

Finish by calling propose_reach for your chosen site, then answer with the JSON object requested."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "structure": {"type": "string", "description": "what was supposedly built, in plain words"},
        "river": {"type": ["string", "null"]},
        "barangays": {"type": "array", "items": {"type": "string"}},
        "purok_or_sitio": {"type": ["string", "null"]},
        "section": {"type": ["string", "null"]},
        "stations": {"type": "array", "items": {"type": "string"}},
        "declared_length_m": {"type": ["number", "null"]},
        "reach_id": {"type": ["string", "null"], "description": "id returned by propose_reach, or null if not locatable"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "pin": {"type": "string", "enum": ["consistent", "inconsistent", "unknown"]},
        "reasoning": {"type": "string", "description": "two or three sentences an investigator can check"},
    },
    "required": ["structure", "river", "barangays", "purok_or_sitio", "section", "stations", "declared_length_m",
                 "reach_id", "confidence", "pin", "reasoning"],
}


def _m(x: float) -> int:
    return int(round(x))


class LocatorTools:
    def __init__(self, case: Case, gi: GeoIndex, tracer=None):
        self.case, self.gi, self.tracer = case, gi, tracer
        r = case.record
        self.pin = (r["lon"], r["lat"])
        self.reaches: dict[str, dict] = {}

    def _pin_dist(self, geom) -> int:
        return _m(to_m(Point(self.pin)).distance(to_m(geom)))

    def find_barangay(self, name: str, municipality: str = "") -> list[dict]:
        muni = municipality or self.case.record.get("muni")
        out = []
        for b in self.gi.find_barangays(name, muni)[:6]:
            out.append({"barangay_id": b["id"], "name": b["name"], "municipality": b.get("muni"),
                        "area_km2": round(to_m(b["geom"]).area / 1e6, 2),
                        "contains_official_pin": b["geom"].contains(Point(self.pin)),
                        "distance_from_pin_m": self._pin_dist(b["geom"])})
        return out or [{"note": f"no barangay named {name!r} in {muni} ({self.gi.barangay_source})"}]

    def waterways_in_barangay(self, barangay_id: str) -> list[dict]:
        b = self.gi.barangay(barangay_id)
        out = []
        # rivers are often the barangay's border: look 150 m past it
        for w in self.gi.waterways_in(buffer_m(b["geom"], 150)):
            out.append({"waterway_id": w["id"], "name": w["name"], "kind": w["kind"],
                        "length_inside_m": _m(to_m(w["inside"]).length),
                        "distance_from_pin_m": self._pin_dist(w["inside"])})
        out.sort(key=lambda x: -x["length_inside_m"])
        return out[:12] or [{"note": "no mapped waterway inside this barangay"}]

    def waterways_near(self, lon: float, lat: float, radius_m: float = 1500, name: str = "") -> list[dict]:
        out = []
        for w in self.gi.waterways_near(lon, lat, min(radius_m, 5000), name or None)[:12]:
            out.append({"waterway_id": w["id"], "name": w["name"], "kind": w["kind"],
                        "length_m": _m(to_m(w["geom"]).length), "distance_m": _m(w["distance_m"]),
                        "distance_from_pin_m": self._pin_dist(w["geom"])})
        return out or [{"note": "no mapped waterway in range"}]

    def contracts_in_barangay(self, barangay: str) -> list[dict]:
        """Other public contracts that name the same barangay in the same municipality (the record corpus)."""
        global _corpus
        if _corpus is None:
            _corpus = json.loads((DATA / "portfolio/projects.json").read_text(encoding="utf-8"))
        r = self.case.record
        key, muni = norm(barangay), norm(r.get("muni"))
        out = []
        for o in _corpus:
            if o["id"] == r["id"] or norm(o.get("muni")) != muni or key not in norm(o.get("desc")):
                continue
            out.append({"id": o["id"], "year": o.get("year"), "description": o["desc"][:180],
                        "river_named": o.get("river_text"), "stations": o.get("stations_m"),
                        "pin_distance_from_this_pin_m": _m(haversine_m(self.pin, (o["lon"], o["lat"]))) if o.get("lon") else None})
        out.sort(key=lambda x: (x["river_named"] is None, x["pin_distance_from_this_pin_m"] or 1e9))
        return out[:15] or [{"note": f"no other contract names {barangay!r} in {r.get('muni')}"}]

    def trace_river_from_imagery(self, lon: float, lat: float) -> dict:
        if not self.tracer:
            return {"error": "imagery tracing not available in this run"}
        return self.tracer(lon, lat)

    def propose_reach(self, waterway_id: str, length_m: float, barangay_id: str = "",
                      anchor_lon: float | None = None, anchor_lat: float | None = None) -> dict:
        w = self.gi.waterway(waterway_id)
        line = longest_line(w["geom"])  # the whole mapped way: a river often crosses the barangay line several times
        brgy = self.gi.barangay(barangay_id)["geom"] if barangay_id else None
        inside = longest_line(line.intersection(brgy)) if brgy is not None and line.intersects(brgy) else None
        anchor = (anchor_lon, anchor_lat) if anchor_lon is not None and anchor_lat is not None else None
        if anchor is None:
            near = inside or line
            mid = near.interpolate(0.5, normalized=True)
            anchor = self.pin if self._pin_dist(near) < 400 else (mid.x, mid.y)
        length = float(length_m or DEFAULT_LENGTH_M)
        reach = reach_on(line, anchor, length)
        got = to_m(reach).length
        rid = f"R{len(self.reaches) + 1}"
        mid = reach.interpolate(0.5, normalized=True)
        self.reaches[rid] = {"geom": reach, "waterway": w, "barangay_id": barangay_id or None, "length_req": length}
        b = self.gi.barangay(barangay_id) if barangay_id else self.gi.barangay_at(mid.x, mid.y)
        out = {"reach_id": rid, "length_m": _m(got), "center": [round(mid.x, 6), round(mid.y, 6)],
               "waterway": w["name"] or f"unnamed {w['kind']}", "in_barangay": b["name"] if b else None,
               "distance_from_pin_m": self._pin_dist(reach)}
        if brgy is not None:
            out["share_inside_barangay"] = round(to_m(reach.intersection(brgy)).length / max(got, 1), 2)
        if got < 0.6 * length:
            out["warning"] = (f"this mapped waterway is only {_m(got)} m long here, for {_m(length)} m of works: "
                              "prefer a waterway that can hold the works, or one the text names")
        return out

    def tools(self) -> list[Tool]:
        S = lambda props, req: {"type": "object", "properties": props, "required": req, "additionalProperties": False}  # noqa: E731
        num, st = {"type": "number"}, {"type": "string"}
        return [
            Tool("find_barangay", "Find barangays by name in the project's municipality (official boundaries).",
                 S({"name": st, "municipality": st}, ["name"]), self.find_barangay),
            Tool("waterways_in_barangay", "List mapped rivers, creeks and canals inside a barangay.",
                 S({"barangay_id": st}, ["barangay_id"]), self.waterways_in_barangay),
            Tool("waterways_near", "List mapped waterways near a point, optionally filtered by name.",
                 S({"lon": num, "lat": num, "radius_m": num, "name": st}, ["lon", "lat"]), self.waterways_near),
            Tool("contracts_in_barangay", "Other public contracts naming the same barangay (same municipality), with the "
                 "river or creek each one names and its stations. Use it when this contract names no waterway.",
                 S({"barangay": st}, ["barangay"]), self.contracts_in_barangay),
            Tool("trace_river_from_imagery", "Trace the river channel at a point from recent sub-metre satellite imagery "
                 "(SAM 3.1). Use when the map has no waterway where the text says the works are.",
                 S({"lon": num, "lat": num}, ["lon", "lat"]), self.trace_river_from_imagery),
            Tool("propose_reach", "Cut a reach of the declared length along a waterway (optionally clipped to a barangay, "
                 "optionally centred on an anchor point). Returns a reach_id to cite in the answer.",
                 S({"waterway_id": st, "length_m": num, "barangay_id": st, "anchor_lon": num, "anchor_lat": num},
                   ["waterway_id", "length_m"]), self.propose_reach),
        ]


def hints(case: Case, tools: LocatorTools) -> dict:
    """Cheap deterministic pre-reading, given to the model as a head start (it may disagree)."""
    r = case.record
    out: dict[str, Any] = {"stations_m": r.get("stations_m"), "length_from_stations_m": r.get("length_m")}
    names = re.findall(r"(?:barangay|brgy\.?)\s+([A-Za-zñÑ\.\- ]+?)(?:,|\(|$| purok| sta| and )", r["desc"], re.I)
    out["barangay_mentions"] = [n.strip() for n in names]
    found = []
    for n in out["barangay_mentions"][:3]:
        found += [b for b in tools.find_barangay(n) if "barangay_id" in b]
    out["barangay_candidates"] = found
    at = tools.gi.barangay_at(*tools.pin)
    out["pin_falls_in"] = {"barangay": at["name"], "municipality": at.get("muni")} if at else None
    out["waterways_near_pin"] = tools.waterways_near(*tools.pin, radius_m=600)[:5]
    return out


def run(case: Case, gi: GeoIndex, tracer=None) -> dict:
    r = case.record
    tools = LocatorTools(case, gi, tracer)
    case.say(AGENT, "start", text="Reading the contract")
    h = hints(case, tools)
    case.say(AGENT, "hints", **{k: v for k, v in h.items() if k != "waterways_near_pin"})
    brief = {
        "contract_id": r["id"], "description": r["desc"], "municipality": r.get("muni"), "province": r.get("province"),
        "contractor": r.get("contractor"), "cost_php": r.get("cost"),
        "published_pin": {"lon": r["lon"], "lat": r["lat"]}, "pre_reading": h,
    }

    def on_turn(t: Turn) -> None:
        summary = t.result if isinstance(t.result, dict) else (t.result[:3] if isinstance(t.result, list) else t.result)
        case.say(AGENT, "tool", tool=t.name, args=t.arguments, result=summary, refused=t.refused)
        case.record_entry(AGENT, "tool_call", {"tool": t.name, "args": t.arguments, "refused": t.refused,
                                               "result": json.loads(json.dumps(t.result, default=str))})

    if case.meta is None:
        return finish(case, gi, tools, screen(case, tools, h), None)
    out = case.meta.tool_loop(case.facts.get("spark", SPARK), INSTRUCTIONS, [{"type": "input_text", "text": json.dumps(brief, ensure_ascii=False)}],
                              tools.tools(), schema=SCHEMA, max_turns=8, on_turn=on_turn, effort="medium")
    return finish(case, gi, tools, out["data"] or {}, out)


def norm_words(s: str) -> str:
    return re.sub(r"[^a-z\s\-]", "", s.lower())


def screen(case: Case, tools: LocatorTools, h: dict) -> dict:
    """Screening depth, no model: the same tools driven by fixed rules. Labelled as such everywhere."""
    r = case.record
    length = r.get("length_m") or DEFAULT_LENGTH_M
    cands = h.get("barangay_candidates") or []
    pick = next((b for b in cands if b.get("contains_official_pin")), cands[0] if cands else None)
    tokens = [t for t in re.split(r"[\s\-]+", norm_words(r.get("river_text") or "")) if len(t) >= 5 and t not in ("river", "creek")]
    chosen = None
    if pick:
        ws = [w for w in tools.waterways_in_barangay(pick["barangay_id"]) if "waterway_id" in w]
        named = [w for w in ws if w["name"] and any(t in norm(w["name"]) for t in tokens)]
        pool = named or ws
        if pool:
            chosen = min(pool, key=lambda w: (w["distance_from_pin_m"] > 300, -w["length_inside_m"]))
            res = tools.propose_reach(chosen["waterway_id"], length, pick["barangay_id"])
    if chosen is None:
        allnear = [w for w in tools.waterways_near(*tools.pin, radius_m=400) if "waterway_id" in w]
        near = [w for w in allnear if w["name"] and any(t in norm(w["name"]) for t in tokens)] or allnear
        if near:
            chosen = near[0]
            res = tools.propose_reach(chosen["waterway_id"], length)
    return {
        "structure": r["desc"], "river": r.get("river_text"), "barangays": [b["name"] for b in cands[:2]],
        "purok_or_sitio": None, "section": None, "stations": [str(x) for x in (r.get("stations_m") or [])],
        "declared_length_m": r.get("length_m"), "reach_id": res["reach_id"] if chosen else None,
        "confidence": "low", "pin": "unknown",
        "reasoning": "Screening locator (fixed rules, no model): " + (
            f"waterway nearest the pin inside Barangay {pick['name']}." if pick and chosen else
            "nearest mapped waterway to the published pin." if chosen else "no waterway matched."),
    }


def finish(case: Case, gi: GeoIndex, tools: LocatorTools, ans: dict, out: dict | None) -> dict:
    r = case.record
    # the open model sometimes returns a field as an object: keep the answer's types what the schema says
    for k in ("structure", "reasoning", "river", "purok_or_sitio", "section"):
        if ans.get(k) is not None and not isinstance(ans[k], str):
            ans[k] = json.dumps(ans[k], ensure_ascii=False) if not isinstance(ans[k], (int, float)) else str(ans[k])
    for k in ("barangays", "stations"):
        if not isinstance(ans.get(k), list):
            ans[k] = [str(ans[k])] if ans.get(k) else []
    case.say(AGENT, "answer", **ans)
    rid = ans.get("reach_id")
    if not rid or rid not in tools.reaches:
        if tools.reaches:  # the model cut a reach but forgot to cite it: take the last one, and say so
            rid = list(tools.reaches)[-1]
            ans["reasoning"] = (ans.get("reasoning") or "") + f" [reach {rid} taken from the last propose_reach call]"
        else:
            result = {"located": False, "answer": ans, "note": ans.get("reasoning") or "no reach proposed"}
            case.record_entry(AGENT, "located", {k: v for k, v in result.items()})
            case.facts["locator"] = result
            return result
    reach = tools.reaches[rid]["geom"]
    mid = reach.interpolate(0.5, normalized=True)
    try:  # the waterway around the reach, for the relocation search (it walks 1.5 km each way)
        near = tools.reaches[rid]["waterway"]["geom"].intersection(buffer_m(reach, 2500))
        waterway_geom = mapping(longest_line(near)) if not near.is_empty else None
    except ValueError:
        waterway_geom = None
    pin_offset = _m(to_m(Point(tools.pin)).distance(to_m(reach)))
    length = to_m(reach).length
    result = {
        "located": True,
        "answer": ans,
        "reach": mapping(reach),
        "center": [mid.x, mid.y],
        "length_m": _m(length),
        "declared_length_m": ans.get("declared_length_m") or r.get("length_m"),
        "pin_offset_m": pin_offset,
        "pin_to_center_m": _m(haversine_m(tools.pin, (mid.x, mid.y))),
        "waterway": tools.reaches[rid]["waterway"]["name"] or ("channel traced by SAM 3.1" if tools.reaches[rid]["waterway"]["kind"] == "traced"
                                                         else f"unnamed {tools.reaches[rid]['waterway']['kind']}"),
        "waterway_source": tools.reaches[rid]["waterway"]["source"],
        "waterway_geom": waterway_geom,
        "ticks": chainage_ticks(reach, 50),
        "barangay_source": gi.barangay_source,
        "mode": f"{label(case.facts.get('spark', SPARK))} tool loop" if out else "screening rules (no model)",
        "model": case.facts.get("spark", SPARK) if out else None,
    }
    case.record_entry(AGENT, "located", {k: v for k, v in result.items() if k not in ("ticks", "waterway_geom")})
    case.facts["locator"] = result
    case.say(AGENT, "located", reach=result["reach"], center=result["center"], pin_offset_m=pin_offset,
             length_m=result["length_m"], waterway=result["waterway"], confidence=ans.get("confidence"))
    return result


__all__ = ["run", "LocatorTools", "norm"]
