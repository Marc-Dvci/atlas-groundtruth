"""Sentinel-2 time series along a river's BANKS, and the date a hard bank first appears.

A concrete wall replaces a vegetated bank with bright, dry, impervious material:
NDVI falls and brightness rises on the strip of land beside the water. The
reach line runs down the river, so we first find the water itself (MNDWI, median
over all clear scenes), then sample only the 20 m of land along its edge, inside
an 80 m corridor of the reach. Clouds are masked per scene with SCL.
Detectability is scored from the bank before the award: a bank that was
already bare cannot testify about a new wall.
"""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_bounds, transform_geom
from rasterio.windows import from_bounds
from scipy.ndimage import binary_dilation
from shapely.geometry import mapping, shape

from . import s2 as S2
from .geom import buffer_m

CORRIDOR_M = 80


def _read(href: str, bbox, out_shape=None):
    with rasterio.open(href) as ds:
        b = transform_bounds("EPSG:4326", ds.crs, *bbox)
        win = from_bounds(*b, transform=ds.transform)
        kw = {"window": win, "boundless": True, "fill_value": 0}
        if out_shape:
            kw["out_shape"] = (1, *out_shape)
        arr = ds.read(1, **kw)
        tr = ds.window_transform(win)
        if out_shape:
            tr = tr * tr.scale(win.width / out_shape[1], win.height / out_shape[0])
        return arr, tr, ds.crs


def sample(scene: S2.Scene, bbox) -> dict | None:
    """Raw per-scene arrays on the 10 m grid (small: the corridor is a few dozen pixels)."""
    try:
        red, tr, crs = _read(scene.href("red"), bbox)
        shp = red.shape
        nir, _, _ = _read(scene.href("nir"), bbox)
        green, _, _ = _read(scene.href("green"), bbox)
        swir, _, _ = _read(scene.href("swir16"), bbox, out_shape=shp)
        scl, _, _ = _read(scene.href("scl"), bbox, out_shape=shp)
    except Exception:
        return None
    if red.size == 0:
        return None
    r, n, g, s = (x.astype(np.float32) for x in (red, nir, green, swir))
    clear = (scl > 0) & ~np.isin(scl, list(S2.CLOUDY))
    return {
        "date": scene.date, "tr": tr, "crs": crs, "clear": clear,
        "ndvi": (n - r) / np.maximum(n + r, 1),
        "mndwi": (g - s) / np.maximum(g + s, 1),
        "bright": (r + g) / 2 / 10000,
    }


def series(reach_geo: dict, start: str, end: str, cache: Path, workers: int = 12) -> list[dict]:
    h = hashlib.sha1(json.dumps(reach_geo, sort_keys=True).encode()).hexdigest()[:16]
    key = cache / f"banks_{h}_{start}_{end}.json"
    if key.exists():
        return json.loads(key.read_text())
    corridor = buffer_m(shape(reach_geo), CORRIDOR_M)
    bbox = corridor.bounds
    scenes = S2.search(bbox, start, end, cache, max_cloud=70)
    by_month: dict[str, list] = {}
    for sc in scenes:
        by_month.setdefault(sc.date[:7], []).append(sc)
    scenes = [x for m in sorted(by_month) for x in sorted(by_month[m], key=lambda s: s.cloud)[:2]]
    with ThreadPoolExecutor(workers) as ex:
        raw = [x for x in ex.map(lambda s: sample(s, bbox), scenes) if x]
    if not raw:
        return []
    shp = raw[0]["ndvi"].shape
    raw = [x for x in raw if x["ndvi"].shape == shp]
    ref = raw[0]
    inside = ~geometry_mask([transform_geom("EPSG:4326", ref["crs"], mapping(corridor))], out_shape=shp,
                            transform=ref["tr"], all_touched=True)
    # stable water mask: median MNDWI over clear observations
    stack = np.where(np.stack([x["clear"] for x in raw]), np.stack([x["mndwi"] for x in raw]), np.nan)
    with np.errstate(all="ignore"):
        med = np.nanmedian(stack, axis=0)
    water = np.nan_to_num(med, nan=-1) > 0.05
    bank = binary_dilation(water, iterations=2) & ~water & inside
    if bank.sum() < 6:  # no water resolved (narrow creek): sample the corridor's land instead
        bank = inside & ~water
    rows = []
    for x in raw:
        ok = bank & x["clear"]
        frac = ok.sum() / max(1, bank.sum())
        if frac < 0.8 or ok.sum() < 4:
            continue
        rows.append({"date": x["date"], "px": int(ok.sum()),
                     "ndvi": round(float(np.median(x["ndvi"][ok])), 4),
                     "bright": round(float(np.median(x["bright"][ok])), 4),
                     "mndwi": round(float(np.median(x["mndwi"][ok])), 4)})
    rows.sort(key=lambda r: r["date"])
    meta = {"water_px": int(water.sum()), "bank_px": int(bank.sum()), "scenes": len(raw)}
    for r in rows:
        r.update(meta)
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text(json.dumps(rows))
    return rows


def season_of(d: str) -> tuple[str, str]:
    """Luzon seasons: dry Dec-May, wet Jun-Nov. Returns (kind, key) with key sortable."""
    y, m = int(d[:4]), int(d[5:7])
    if m >= 12:
        return "dry", f"{y + 1}-1dry"
    if m <= 5:
        return "dry", f"{y}-1dry"
    return "wet", f"{y}-2wet"


def seasons(rows: list[dict]) -> list[dict]:
    by: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("ndvi") is None:
            continue
        by.setdefault(season_of(r["date"])[1], []).append(r)
    out = []
    for k in sorted(by):
        rs = by[k]
        if len(rs) < 2:
            continue
        out.append({"key": k, "kind": k.split("-")[1][1:], "first": rs[0]["date"], "n": len(rs),
                    "ndvi": float(np.median([r["ndvi"] for r in rs])), "bright": float(np.median([r["bright"] for r in rs]))})
    return out


def first_change(rows: list[dict], *, min_shift: float = 0.15) -> dict | None:
    """First season whose bank NDVI is at least `min_shift` below the same season in earlier years,
    and stays below in the next same-kind season (comparing wet with wet and dry with dry removes the
    monsoon cycle). Returns the date of the first scene of that season."""
    ss = seasons(rows)
    for i, s in enumerate(ss):
        prior = [x["ndvi"] for x in ss[:i] if x["kind"] == s["kind"]][-2:]
        if not prior:
            continue
        base = float(np.median(prior))
        if s["ndvi"] > base - min_shift:
            continue
        nxt = [x for x in ss[i + 1:] if x["kind"] == s["kind"]][:1]
        if nxt and nxt[0]["ndvi"] > base - min_shift / 2:
            continue
        # the other season kind should agree when it can be checked
        other = [x for x in ss if x["kind"] != s["kind"]]
        o_before = [x["ndvi"] for x in other if x["key"] < s["key"]][-2:]
        o_after = [x["ndvi"] for x in other if x["key"] > s["key"]][:2]
        if o_before and o_after and np.median(o_after) > np.median(o_before) - min_shift / 2:
            continue
        return {"date": s["first"], "season": s["key"], "ndvi_before": round(base, 3), "ndvi_after": round(s["ndvi"], 3),
                "shift": round(base - s["ndvi"], 3), "method": "same-season comparison (wet vs wet, dry vs dry)"}
    return None


def window_stats(rows: list[dict], start: str | None, end: str | None) -> dict | None:
    sel = [r for r in rows if r.get("ndvi") is not None and (start is None or r["date"] >= start) and (end is None or r["date"] <= end)]
    if not sel:
        return None
    return {
        "n": len(sel),
        "ndvi": round(float(np.median([r["ndvi"] for r in sel])), 3),
        "bright": round(float(np.median([r["bright"] for r in sel])), 4),
        "from": sel[0]["date"],
        "to": sel[-1]["date"],
    }
