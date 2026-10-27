"""Sentinel-2 L2A over a site: scene search, windowed COG reads, local cloud mask.

Earth Search (Element84) serves the Sentinel-2 archive as public COGs on AWS,
so a 600 m window costs a few HTTP range requests and no account. Scene-level
cloud cover is useless at a riverbank, so every chip is scored with the scene
classification band (SCL) over the window itself.
"""
from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.TIF")
os.environ.setdefault("GDAL_HTTP_MULTIRANGE", "YES")
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
# neighbouring sites share the same 10 km tiles and dates: keep downloaded ranges in memory for the whole run
os.environ.setdefault("CPL_VSIL_CURL_CACHE_SIZE", str(3 * 1024 ** 3))
# a read with no HTTP timeout can wait forever on a dead connection, and every other GDAL read then waits behind it
os.environ.setdefault("GDAL_HTTP_TIMEOUT", "45")
os.environ.setdefault("GDAL_HTTP_CONNECTTIMEOUT", "15")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "3")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")

import rasterio  # noqa: E402
from rasterio.warp import transform_bounds  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402

STAC = "https://earth-search.aws.element84.com/v1/search"
# SCL classes: 3 cloud shadow, 8/9 cloud medium/high, 10 cirrus, 1 saturated
CLOUDY = {1, 3, 8, 9, 10}
WATER = 6


@dataclass
class Scene:
    id: str
    date: str
    cloud: float
    assets: dict

    def href(self, key: str) -> str:
        return self.assets[key]["href"]


def search(bbox: tuple[float, float, float, float], start: str, end: str, cache: Path, max_cloud: float = 60) -> list[Scene]:
    key = cache / f"s2_{'_'.join(f'{v:.4f}' for v in bbox)}_{start}_{end}_{max_cloud}.json"
    if key.exists():
        feats = json.loads(key.read_text())
    else:
        feats, body = [], {
            "collections": ["sentinel-2-l2a"],
            "bbox": list(bbox),
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
            "query": {"eo:cloud_cover": {"lt": max_cloud}},
            "limit": 200,
            "fields": {"include": ["id", "properties.datetime", "properties.eo:cloud_cover", "assets"]},
        }
        url = STAC
        while url:
            r = httpx.post(url, json=body, timeout=60)
            r.raise_for_status()
            d = r.json()
            feats += d["features"]
            nxt = next((l for l in d.get("links", []) if l.get("rel") == "next"), None)
            url, body = (nxt["href"], nxt.get("body", body)) if nxt else (None, None)
        key.parent.mkdir(parents=True, exist_ok=True)
        key.write_text(json.dumps(feats))
    out = []
    seen = set()
    for f in feats:
        p = f["properties"]
        d = p["datetime"][:10]
        if d in seen:  # same-day tiles of one pass
            continue
        seen.add(d)
        out.append(Scene(f["id"], d, p.get("eo:cloud_cover", 100), f["assets"]))
    return sorted(out, key=lambda s: s.date)


def _read(href: str, bbox: tuple[float, float, float, float], out_shape: tuple[int, int] | None = None) -> np.ndarray:
    with rasterio.open(href) as ds:
        b = transform_bounds("EPSG:4326", ds.crs, *bbox)
        win = from_bounds(*b, transform=ds.transform)
        kw = {"window": win, "boundless": True, "fill_value": 0}
        if out_shape:
            kw["out_shape"] = (ds.count, *out_shape)
        return ds.read(**kw)


def local_cloud(scene: Scene, bbox) -> float:
    scl = _read(scene.href("scl"), bbox)[0]
    if scl.size == 0:
        return 1.0
    valid = scl > 0
    if valid.sum() == 0:
        return 1.0
    return float(np.isin(scl[valid], list(CLOUDY)).mean())


def chip(scene: Scene, bbox, size: int = 256) -> bytes:
    """True-colour chip, upsampled with nearest-neighbour so the 10 m pixels stay honest."""
    rgb = _read(scene.href("visual"), bbox)
    img = Image.fromarray(np.transpose(rgb[:3], (1, 2, 0)).astype(np.uint8))
    img = img.resize((size, int(size * img.height / max(1, img.width))), Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def indices(scene: Scene, bbox, mask: np.ndarray | None = None) -> dict:
    """Mean NDVI and NDBI over the window (or a boolean mask on the 10 m grid)."""
    red = _read(scene.href("red"), bbox)[0].astype(np.float32)
    nir = _read(scene.href("nir"), bbox)[0].astype(np.float32)
    swir = _read(scene.href("swir16"), bbox, out_shape=red.shape)[0].astype(np.float32)
    scl = _read(scene.href("scl"), bbox, out_shape=red.shape)[0]
    ok = (scl > 0) & ~np.isin(scl, list(CLOUDY))
    if mask is not None and mask.shape == ok.shape:
        ok &= mask
    if ok.sum() < 5:
        return {"ndvi": None, "ndbi": None, "clear_px": int(ok.sum())}
    ndvi = (nir - red) / np.maximum(nir + red, 1)
    ndbi = (swir - nir) / np.maximum(swir + nir, 1)
    return {"ndvi": round(float(ndvi[ok].mean()), 4), "ndbi": round(float(ndbi[ok].mean()), 4), "clear_px": int(ok.sum())}
