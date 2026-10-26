"""Geometry in metres: chainage along rivers, reach extraction, distances.

Bulacan sits in UTM zone 51N, so every measurement is done in EPSG:32651 and
converted back to WGS84 for display.
"""
from __future__ import annotations

import math
import re

from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, Point, mapping
from shapely.ops import linemerge, substring, transform

UTM = "EPSG:32651"
_fwd = Transformer.from_crs("EPSG:4326", UTM, always_xy=True).transform
_inv = Transformer.from_crs(UTM, "EPSG:4326", always_xy=True).transform

_STA = re.compile(r"(?:sta\.?|station|km)\s*(\d+)\s*\+\s*(\d{1,3}(?:\.\d+)?)", re.I)


def to_m(geom):
    return transform(_fwd, geom)


def to_deg(geom):
    return transform(_inv, geom)


def parse_stations(text: str) -> list[float]:
    """'Sta. 1+200 to Sta. 1+500' -> [1200.0, 1500.0] (metres)."""
    return [int(a) * 1000 + float(b) for a, b in _STA.findall(text or "")]


def merge_lines(lines: list[LineString]) -> LineString:
    merged = linemerge(MultiLineString(lines)) if len(lines) > 1 else lines[0]
    if isinstance(merged, MultiLineString):
        merged = max(merged.geoms, key=lambda g: g.length)
    return merged


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    (lon1, lat1), (lon2, lat2) = a, b
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def distance_to_line_m(lonlat: tuple[float, float], line_deg: LineString) -> float:
    return to_m(Point(lonlat)).distance(to_m(line_deg))


def reach_between(line_deg: LineString, start_m: float, end_m: float) -> LineString:
    lm = to_m(line_deg)
    a, b = sorted((max(0.0, start_m), min(lm.length, end_m)))
    return to_deg(substring(lm, a, b))


def clip_reach_near(line_deg: LineString, center: tuple[float, float], length_m: float) -> LineString:
    """A reach of `length_m` centred on the river point closest to `center`."""
    lm = to_m(line_deg)
    s = lm.project(to_m(Point(center)))
    return to_deg(substring(lm, max(0.0, s - length_m / 2), min(lm.length, s + length_m / 2)))


def chainage_ticks(line_deg: LineString, every_m: float = 100.0, start_m: float = 0.0) -> list[dict]:
    lm = to_m(line_deg)
    out = []
    d = 0.0
    while d <= lm.length + 1e-6:
        p = to_deg(lm.interpolate(d))
        km, rest = divmod(int(round(start_m + d)), 1000)
        out.append({"lonlat": [p.x, p.y], "label": f"{km}+{rest:03d}", "m": start_m + d})
        d += every_m
    return out


def buffer_m(geom_deg, metres: float):
    return to_deg(to_m(geom_deg).buffer(metres))


def bbox_around(lonlat: tuple[float, float], half_m: float) -> tuple[float, float, float, float]:
    p = to_m(Point(lonlat))
    sw = to_deg(Point(p.x - half_m, p.y - half_m))
    ne = to_deg(Point(p.x + half_m, p.y + half_m))
    return (sw.x, sw.y, ne.x, ne.y)


def geojson(geom) -> dict:
    return mapping(geom)
