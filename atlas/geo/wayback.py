"""Esri World Imagery Wayback: the sub-metre history of a site.

Wayback publishes ~200 releases of the World Imagery basemap since 2014, but a
given tile only changes when a new capture lands there. The `tilemap` endpoint
says which release last changed a tile, so walking back through it yields the
distinct captures of a site in ~10-20 requests instead of 200. The metadata
service then gives each capture's acquisition date, sensor and resolution.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
import mercantile
from PIL import Image

CONFIG = "https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json"
BASE = "https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer"
UA = {"User-Agent": "Atlas-Groundtruth/0.1 (public-works audit research)"}


@dataclass
class Release:
    num: int
    date: str  # release date (not the capture date)
    metadata_url: str


@dataclass
class Capture:
    release: int
    release_date: str
    captured: str | None  # acquisition date of the pixels
    sensor: str | None
    resolution_m: float | None
    provider: str | None


class Wayback:
    def __init__(self, cache: Path):
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.http = httpx.Client(timeout=40, headers=UA, follow_redirects=True)
        cfg_path = self.cache / "config.json"
        if not cfg_path.exists():
            cfg_path.write_bytes(self.http.get(CONFIG).content)
        cfg = json.loads(cfg_path.read_text())
        rels = []
        for k, v in cfg.items():
            d = v["itemTitle"].split("Wayback ")[-1].rstrip(")")
            rels.append(Release(int(k), d, v["metadataLayerUrl"]))
        self.releases = sorted(rels, key=lambda r: r.date)  # oldest first
        self.by_num = {r.num: r for r in self.releases}

    # ---------- low level ----------
    def _json(self, url: str, key: str) -> dict:
        p = self.cache / "json" / f"{hashlib.sha1(key.encode()).hexdigest()}.json"
        if p.exists():
            return json.loads(p.read_text())
        r = self.http.get(url)
        r.raise_for_status()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(r.text)
        return r.json()

    def tile(self, release: int, z: int, x: int, y: int) -> bytes:
        p = self.cache / "tiles" / str(release) / f"{z}_{x}_{y}.jpg"
        if p.exists():
            return p.read_bytes()
        r = self.http.get(f"{BASE}/tile/{release}/{z}/{y}/{x}")
        r.raise_for_status()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(r.content)
        return r.content

    def last_change(self, release: int, z: int, x: int, y: int) -> int | None:
        d = self._json(f"{BASE}/tilemap/{release}/{z}/{y}/{x}", f"tm/{release}/{z}/{y}/{x}")
        if not d.get("data") or not d["data"][0]:
            return None
        sel = d.get("select")
        return int(sel[0]) if sel else release

    # ---------- the site's history ----------
    def distinct_releases(self, lon: float, lat: float, z: int = 18) -> list[int]:
        """Releases where the tile under (lon, lat) actually changed, newest first."""
        t = mercantile.tile(lon, lat, z)
        order = [r.num for r in reversed(self.releases)]  # newest first
        out: list[int] = []
        i = 0
        while i < len(order):
            ch = self.last_change(order[i], z, t.x, t.y)
            if ch is None or ch in out:
                break
            out.append(ch)
            try:
                i = order.index(ch) + 1
            except ValueError:
                break
        return out

    def capture(self, release: int, lon: float, lat: float, z: int = 18) -> Capture:
        """Acquisition metadata under a point. Older releases hold sub-metre metadata only down to
        zoom 17 at many sites, so coarser layers are tried until one names a dated source."""
        rel = self.by_num[release]
        for layer in range(_metadata_layer(z), 12):
            q = (f"{rel.metadata_url}/{layer}/query?where=1%3D1&geometry={lon}%2C{lat}&geometryType=esriGeometryPoint"
                 f"&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&returnGeometry=false&f=json")
            d = self._json(q, f"md/{release}/{layer}/{lon:.5f}/{lat:.5f}")
            feats = d.get("features") or []
            if not feats:
                continue
            a = {k.upper(): v for k, v in feats[0]["attributes"].items()}
            ms = a.get("SRC_DATE2") or a.get("SRC_DATE")
            captured = None
            if isinstance(ms, (int, float)) and ms > 1e11:
                captured = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()
            elif ms:
                v = str(int(ms)) if isinstance(ms, (int, float)) else str(ms)
                if len(v) >= 8:
                    captured = f"{v[:4]}-{v[4:6]}-{v[6:8]}"
            if not captured:
                continue
            return Capture(release, rel.date, captured, a.get("SRC_DESC"), _f(a.get("SRC_RES")),
                           a.get("NICE_DESC") or a.get("NICE_NAME"))
        return Capture(release, rel.date, None, None, None, None)

    def mosaic(self, release: int, bbox: tuple[float, float, float, float], z: int = 18) -> Image.Image:
        """Stitch the tiles covering bbox and crop to it exactly (Web Mercator pixels)."""
        w, s, e, n = bbox
        tiles = list(mercantile.tiles(w, s, e, n, z))
        xs, ys = [t.x for t in tiles], [t.y for t in tiles]
        x0, y0 = min(xs), min(ys)
        img = Image.new("RGB", ((max(xs) - x0 + 1) * 256, (max(ys) - y0 + 1) * 256))
        for t in tiles:
            img.paste(Image.open(io.BytesIO(self.tile(release, z, t.x, t.y))).convert("RGB"),
                      ((t.x - x0) * 256, (t.y - y0) * 256))
        px = lambda lon, lat: _lonlat_to_px(lon, lat, z)  # noqa: E731
        (lx, ty), (rx, by) = px(w, n), px(e, s)
        return img.crop((round(lx - x0 * 256), round(ty - y0 * 256), round(rx - x0 * 256), round(by - y0 * 256)))


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _metadata_layer(z: int) -> int:
    # Layer 0 is 1.9 cm, each next layer doubles; zoom 18 (~0.6 m) is layer 5, zoom 17 layer 6.
    return max(0, min(13, 23 - z))


def _lonlat_to_px(lon: float, lat: float, z: int) -> tuple[float, float]:
    n = 256 * 2 ** z
    x = (lon + 180) / 360 * n
    lr = math.radians(lat)
    y = (1 - math.log(math.tan(lr) + 1 / math.cos(lr)) / math.pi) / 2 * n
    return x, y


def metres_per_px(lat: float, z: int) -> float:
    return 156543.03392 * math.cos(math.radians(lat)) / 2 ** z
