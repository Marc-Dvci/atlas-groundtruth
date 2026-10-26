"""Spatial lookups the Locator's tools run against: barangays, waterways, river areas.

Barangays come from the official PSA/NAMRIA boundaries when present (OSM has
gaps), waterways from OpenStreetMap (named and unnamed ways).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from shapely.geometry import LineString, MultiLineString, Point, shape
from shapely.ops import substring
from shapely.strtree import STRtree

from .geom import to_deg, to_m

ROOT = Path(__file__).resolve().parents[2]


def norm(s: str | None) -> str:
    s = (s or "").lower()
    s = re.sub(r"\bsta\.?\s", "santa ", s)
    s = re.sub(r"\bsto\.?\s", "santo ", s)
    s = re.sub(r"\(.*?\)", "", s)
    s = s.replace("poblacion", "pob")
    return re.sub(r"[^a-z0-9]", "", s)


MUNI_ALIASES = {"baliuag": "baliwag", "cityofbaliwag": "baliwag", "bigaa": "balagtas", "bulakan": "bulacan",
                "cityofmalolos": "malolos", "cityofmeycauayan": "meycauayan", "cityofsanjosedelmonte": "sanjosedelmonte"}


def muni_key(s: str | None) -> str:
    k = norm(s).replace("city", "") if s else ""
    k = MUNI_ALIASES.get(norm(s), k)
    return MUNI_ALIASES.get(k, k)


def _fc(p: Path) -> list[dict]:
    return json.loads(p.read_text(encoding="utf-8"))["features"] if p.exists() else []


class GeoIndex:
    def __init__(self, province: str = "bulacan"):
        osm = ROOT / "data/osm" / province
        adm = ROOT / "data/admin"
        psa_b = adm / f"{province}_barangays.geojson"
        self.barangay_source = "PSA/NAMRIA (HDX COD-AB)" if psa_b.exists() else "OpenStreetMap"
        self.barangays = []
        for i, f in enumerate(_fc(psa_b) or _fc(osm / "barangays.geojson")):
            p = f["properties"]
            self.barangays.append({"id": f"b{i}", "name": p.get("name"), "muni": p.get("muni"), "geom": shape(f["geometry"])})
        if self.barangay_source == "OpenStreetMap":
            munis = [(f["properties"]["name"], shape(f["geometry"])) for f in _fc(osm / "municipalities.geojson")]
            for b in self.barangays:
                rp = b["geom"].representative_point()
                b["muni"] = next((n for n, g in munis if g.contains(rp)), None)
        self.waterways = []
        for f in _fc(osm / "waterways_all.geojson"):
            p = f["properties"]
            self.waterways.append({"id": f"w{p['osm']}", "name": p.get("name"), "kind": p.get("waterway"),
                                   "geom": shape(f["geometry"]), "source": "OpenStreetMap"})
        self.areas = [{"id": f"a{f['properties']['osm']}", "name": f["properties"].get("name"), "geom": shape(f["geometry"])}
                      for f in _fc(osm / "water_areas.geojson")]
        self._wtree = STRtree([w["geom"] for w in self.waterways]) if self.waterways else None
        self._btree = STRtree([b["geom"] for b in self.barangays]) if self.barangays else None
        self.extra: dict[str, dict] = {}  # waterways traced from imagery during a run

    # ---------- barangays ----------
    def barangay_at(self, lon: float, lat: float) -> dict | None:
        if not self._btree:
            return None
        p = Point(lon, lat)
        for i in self._btree.query(p):
            if self.barangays[i]["geom"].contains(p):
                return self.barangays[i]
        return None

    def find_barangays(self, name: str, muni: str | None = None) -> list[dict]:
        n, m = norm(name), muni_key(muni)
        out = []
        for b in self.barangays:
            bn = norm(b["name"])
            if not bn or not (bn == n or (len(n) >= 4 and (bn.startswith(n) or n.startswith(bn)))):
                continue
            bm = muni_key(b.get("muni"))
            if m and bm and not (bm[:6] in m or m[:6] in bm):
                continue
            out.append(b)
        return out

    def barangay(self, bid: str) -> dict:
        return next(b for b in self.barangays if b["id"] == bid)

    # ---------- waterways ----------
    def waterway(self, wid: str) -> dict:
        if wid in self.extra:
            return self.extra[wid]
        return next(w for w in self.waterways if w["id"] == wid)

    def waterways_near(self, lon: float, lat: float, radius_m: float, name: str | None = None) -> list[dict]:
        if not self._wtree:
            return []
        pm = to_m(Point(lon, lat))
        deg = radius_m / 100000 * 1.1
        idx = self._wtree.query(Point(lon, lat).buffer(deg))
        out = []
        cands = [self.waterways[i] for i in idx] + list(self.extra.values())
        for w in cands:
            d = pm.distance(to_m(w["geom"]))
            if d > radius_m:
                continue
            if name and norm(name) not in norm(w["name"]):
                continue
            out.append({**w, "distance_m": d})
        return sorted(out, key=lambda w: w["distance_m"])

    def waterways_in(self, area) -> list[dict]:
        if not self._wtree:
            return []
        out = []
        for i in self._wtree.query(area):
            w = self.waterways[i]
            inter = w["geom"].intersection(area)
            if not inter.is_empty:
                out.append({**w, "inside": inter})
        for w in self.extra.values():
            inter = w["geom"].intersection(area)
            if not inter.is_empty:
                out.append({**w, "inside": inter})
        return out

    def add_traced(self, wid: str, line: LineString, note: str) -> dict:
        w = {"id": wid, "name": None, "kind": "traced", "geom": line, "source": note}
        self.extra[wid] = w
        return w


def longest_line(g) -> LineString:
    if isinstance(g, LineString):
        return g
    if isinstance(g, MultiLineString):
        return max(g.geoms, key=lambda x: to_m(x).length)
    if hasattr(g, "geoms"):
        lines = [x for x in g.geoms if isinstance(x, (LineString, MultiLineString))]
        if lines:
            return longest_line(max(lines, key=lambda x: to_m(x).length))
    raise ValueError("no line geometry")


def reach_on(line_deg: LineString, anchor: tuple[float, float], length_m: float) -> LineString:
    lm = to_m(line_deg)
    s = lm.project(to_m(Point(anchor)))
    half = min(length_m, lm.length) / 2
    a, b = s - half, s + half
    if a < 0:
        a, b = 0, min(lm.length, 2 * half)
    if b > lm.length:
        a, b = max(0, lm.length - 2 * half), lm.length
    return to_deg(substring(lm, a, b))


@lru_cache(maxsize=2)
def get_index(province: str = "bulacan") -> GeoIndex:
    return GeoIndex(province)
