"""OpenStreetMap: rivers, barangays and the province outline, via Overpass.

Fetched once per province and cached as GeoJSON; the Locator agent's tools
query these files, never the live API, so a run is reproducible.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
from shapely.geometry import LineString, MultiPolygon, Polygon, mapping, shape
from shapely.ops import linemerge, polygonize, unary_union

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
UA = {"User-Agent": "Atlas-Groundtruth/0.1 (hackathon research; contact via github.com/Marc-Dvci)"}


def overpass(query: str, cache: Path) -> dict:
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    last = None
    for url in OVERPASS:
        for attempt in range(3):
            try:
                r = httpx.post(url, data={"data": query}, headers=UA, timeout=300)
                if r.status_code == 200:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_text(r.text, encoding="utf-8")
                    return r.json()
                last = f"HTTP {r.status_code}: {r.text[:200]}"
            except httpx.HTTPError as e:
                last = str(e)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Overpass failed: {last}")


def _way_line(el: dict) -> LineString | None:
    g = el.get("geometry") or []
    if len(g) < 2:
        return None
    return LineString([(p["lon"], p["lat"]) for p in g])


def _relation_polygon(el: dict):
    lines = []
    for m in el.get("members", []):
        if m.get("type") == "way" and m.get("geometry") and m.get("role") in ("outer", ""):
            lines.append(LineString([(p["lon"], p["lat"]) for p in m["geometry"]]))
    if not lines:
        return None
    u = unary_union(lines)
    polys = list(polygonize(u if u.geom_type == "LineString" else linemerge(u)))
    if not polys:
        return None
    return unary_union(polys) if len(polys) > 1 else polys[0]


def build_province(name: str, out_dir: Path) -> dict:
    """Province outline, municipalities, barangays and named waterways, as GeoJSON files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "raw"
    area = f'area["name"="{name}"]["admin_level"="4"]["boundary"="administrative"]->.p;'
    prov = overpass(f'[out:json][timeout:240];relation["name"="{name}"]["admin_level"="4"]["boundary"="administrative"];out geom;',
                    raw / "province.json")
    admins = overpass(f'[out:json][timeout:280];{area}relation(area.p)["boundary"="administrative"]["admin_level"~"^(6|7|10)$"];out geom;',
                      raw / "admin.json")
    water = overpass(f'[out:json][timeout:280];{area}way(area.p)["waterway"~"^(river|stream|canal)$"]["name"];out geom tags;',
                     raw / "waterways.json")

    feats = []
    for el in prov.get("elements", []):
        poly = _relation_polygon(el)
        if poly is not None:
            feats.append({"type": "Feature", "geometry": mapping(poly), "properties": {"name": el["tags"].get("name")}})
    (out_dir / "province.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))

    munis, brgys = [], []
    for el in admins.get("elements", []):
        poly = _relation_polygon(el)
        if poly is None:
            continue
        t = el.get("tags", {})
        f = {"type": "Feature", "geometry": mapping(poly),
             "properties": {"name": t.get("name"), "level": t.get("admin_level"), "osm": el["id"]}}
        (brgys if t.get("admin_level") == "10" else munis).append(f)
    (out_dir / "municipalities.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": munis}))
    (out_dir / "barangays.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": brgys}))

    by_name: dict[str, list[LineString]] = {}
    kind: dict[str, str] = {}
    for el in water.get("elements", []):
        ln = _way_line(el)
        if ln is None:
            continue
        nm = el["tags"]["name"]
        by_name.setdefault(nm, []).append(ln)
        kind[nm] = el["tags"].get("waterway", "")
    wfeats = []
    for nm, lines in by_name.items():
        u = unary_union(lines)
        merged = u if u.geom_type == "LineString" else linemerge(u)
        wfeats.append({"type": "Feature", "geometry": mapping(merged),
                       "properties": {"name": nm, "waterway": kind[nm], "segments": len(lines)}})
    (out_dir / "waterways.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": wfeats}))
    return {"province": len(feats), "municipalities": len(munis), "barangays": len(brgys), "waterways": len(wfeats)}


def load(out_dir: Path, kind: str) -> list[dict]:
    return json.loads((out_dir / f"{kind}.geojson").read_text())["features"]


def as_shape(feature: dict):
    return shape(feature["geometry"])


__all__ = ["build_province", "load", "as_shape", "Polygon", "MultiPolygon"]


def build_all_waterways(name: str, out_dir: Path) -> dict:
    """Every waterway way (named or not) and river-area polygons, one feature per OSM way."""
    raw = out_dir / "raw"
    area = f'area["name"="{name}"]["admin_level"="4"]["boundary"="administrative"]->.p;'
    lines = overpass(f'[out:json][timeout:280];{area}way(area.p)["waterway"~"^(river|stream|canal|drain|ditch)$"];out geom tags;',
                     raw / "waterways_all.json")
    areas = overpass(f'[out:json][timeout:280];{area}(way(area.p)["natural"="water"]["water"~"^(river|canal|oxbow|stream)$"];'
                     f'relation(area.p)["natural"="water"]["water"~"^(river|canal)$"];way(area.p)["waterway"="riverbank"];);out geom tags;',
                     raw / "water_areas.json")
    feats = []
    for el in lines.get("elements", []):
        ln = _way_line(el)
        if ln is None:
            continue
        t = el.get("tags", {})
        feats.append({"type": "Feature", "geometry": mapping(ln),
                      "properties": {"osm": el["id"], "name": t.get("name"), "waterway": t.get("waterway")}})
    (out_dir / "waterways_all.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    afeats = []
    for el in areas.get("elements", []):
        if el["type"] == "way" and el.get("geometry") and len(el["geometry"]) >= 4:
            poly = Polygon([(p["lon"], p["lat"]) for p in el["geometry"]])
        elif el["type"] == "relation":
            poly = _relation_polygon(el)
        else:
            poly = None
        if poly is None or poly.is_empty:
            continue
        afeats.append({"type": "Feature", "geometry": mapping(poly.buffer(0)),
                       "properties": {"osm": el["id"], "name": el.get("tags", {}).get("name")}})
    (out_dir / "water_areas.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": afeats}))
    return {"waterways_all": len(feats), "water_areas": len(afeats)}
