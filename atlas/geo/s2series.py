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
NARROW_M = 15  # bank strip either side of a channel too narrow for the water mask


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


def _raw(reach_geo: dict, start: str, end: str, cache: Path, workers: int, per_month: int = 2) -> list[dict]:
    """Per-scene arrays over the corridor, read once and cached (the reads are the slow part)."""
    from rasterio.crs import CRS
    from rasterio.transform import Affine
    h = hashlib.sha1(json.dumps(reach_geo, sort_keys=True).encode()).hexdigest()[:16]
    npz = cache / (f"raw_{h}_{start}_{end}.npz" if per_month == 2 else f"raw_{h}_{start}_{end}_m{per_month}.npz")
    if npz.exists():
        z = np.load(npz, allow_pickle=False)
        meta = json.loads(str(z["meta"]))
        tr, crs = Affine(*meta["tr"]), CRS.from_string(meta["crs"])
        return [{"date": d, "tr": tr, "crs": crs, "clear": z["clear"][i], "ndvi": z["ndvi"][i], "mndwi": z["mndwi"][i],
                 "bright": z["bright"][i]} for i, d in enumerate(meta["dates"])]
    corridor = buffer_m(shape(reach_geo), CORRIDOR_M)
    bbox = corridor.bounds
    scenes = S2.search(bbox, start, end, cache, max_cloud=70)
    by_month: dict[str, list] = {}
    for sc in scenes:
        by_month.setdefault(sc.date[:7], []).append(sc)
    scenes = [x for m in sorted(by_month) for x in sorted(by_month[m], key=lambda s: s.cloud)[:per_month]]
    with ThreadPoolExecutor(workers) as ex:
        raw = [x for x in ex.map(lambda s: sample(s, bbox), scenes) if x]
    if not raw:
        return []
    shp = raw[0]["ndvi"].shape
    raw = sorted((x for x in raw if x["ndvi"].shape == shp), key=lambda x: x["date"])
    npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(npz, clear=np.stack([x["clear"] for x in raw]), ndvi=np.stack([x["ndvi"] for x in raw]).astype(np.float32),
                        mndwi=np.stack([x["mndwi"] for x in raw]).astype(np.float32),
                        bright=np.stack([x["bright"] for x in raw]).astype(np.float32),
                        meta=json.dumps({"dates": [x["date"] for x in raw], "tr": list(raw[0]["tr"])[:6],
                                         "crs": raw[0]["crs"].to_string()}))
    return raw


def series(reach_geo: dict, start: str, end: str, cache: Path, workers: int = 12, per_month: int = 2) -> list[dict]:
    """Bank NDVI per scene: both banks together, and each bank alone ("l" and "r" of the reach line).
    A wall is usually built on one bank; on a median over both, a vegetated far bank can hide it."""
    from .geom import to_deg, to_m
    h = hashlib.sha1(json.dumps(reach_geo, sort_keys=True).encode()).hexdigest()[:16]
    key = cache / (f"banks3_{h}_{start}_{end}.json" if per_month == 2 else f"banks3_{h}_{start}_{end}_m{per_month}.json")
    if key.exists():
        return json.loads(key.read_text())
    raw = _raw(reach_geo, start, end, cache, workers, per_month)
    if not raw:
        return []
    shp = raw[0]["ndvi"].shape
    ref = raw[0]
    reach = shape(reach_geo)
    corridor = buffer_m(reach, CORRIDOR_M)

    def mask(geom) -> np.ndarray:
        return ~geometry_mask([transform_geom("EPSG:4326", ref["crs"], mapping(geom))], out_shape=shp,
                              transform=ref["tr"], all_touched=True)

    inside = mask(corridor)
    rm = to_m(reach)
    left, right = mask(to_deg(rm.buffer(CORRIDOR_M, single_sided=True))), mask(to_deg(rm.buffer(-CORRIDOR_M, single_sided=True)))
    # stable water mask: median MNDWI over clear observations
    stack = np.where(np.stack([x["clear"] for x in raw]), np.stack([x["mndwi"] for x in raw]), np.nan)
    with np.errstate(all="ignore"):
        med = np.nanmedian(stack, axis=0)
    water = np.nan_to_num(med, nan=-1) > 0.05
    bank = binary_dilation(water, iterations=2) & ~water & inside
    if bank.sum() < 6:  # no water resolved (a creek narrower than a pixel): the strip along the channel itself
        bank = mask(buffer_m(reach, NARROW_M)) & ~water
    sides = {"l": bank & left & ~right, "r": bank & right & ~left}
    rows = []
    for x in raw:
        ok = bank & x["clear"]
        frac = ok.sum() / max(1, bank.sum())
        if frac < 0.8 or ok.sum() < 4:
            continue
        row = {"date": x["date"], "px": int(ok.sum()),
               "ndvi": round(float(np.median(x["ndvi"][ok])), 4),
               "bright": round(float(np.median(x["bright"][ok])), 4),
               "mndwi": round(float(np.median(x["mndwi"][ok])), 4)}
        for k, m in sides.items():
            okk = m & x["clear"]
            if m.sum() >= 3 and okk.sum() >= 0.8 * m.sum():
                row[f"ndvi_{k}"] = round(float(np.median(x["ndvi"][okk])), 4)
        rows.append(row)
    meta = {"water_px": int(water.sum()), "bank_px": int(bank.sum()), "bank_px_l": int(sides["l"].sum()),
            "bank_px_r": int(sides["r"].sum()), "scenes": len(raw)}
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


def seasons(rows: list[dict], field: str = "ndvi") -> list[dict]:
    by: dict[str, list[dict]] = {}
    for r in rows:
        if r.get(field) is None:
            continue
        by.setdefault(season_of(r["date"])[1], []).append(r)
    out = []
    for k in sorted(by):
        rs = by[k]
        if len(rs) < 2:
            continue
        out.append({"key": k, "kind": k.split("-")[1][1:], "first": rs[0]["date"], "n": len(rs),
                    "ndvi": float(np.median([r[field] for r in rs])), "bright": float(np.median([r["bright"] for r in rs]))})
    return out


def first_change(rows: list[dict], *, min_shift: float = 0.15, field: str = "ndvi") -> dict | None:
    """First season whose bank NDVI is at least `min_shift` below the same season in earlier years,
    and stays below in the next same-kind season (comparing wet with wet and dry with dry removes the
    monsoon cycle). Returns the date of the first scene of that season."""
    ss = seasons(rows, field)
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


def first_change_any_bank(rows: list[dict], *, min_shift: float = 0.15) -> dict | None:
    """The earliest lasting change on either bank, or on both together. Says which."""
    found = []
    for field, where in (("ndvi", "both banks"), ("ndvi_l", "left bank"), ("ndvi_r", "right bank")):
        fc = first_change(rows, min_shift=min_shift, field=field)
        if fc:
            found.append({**fc, "bank": where})
    return min(found, key=lambda f: f["date"]) if found else None


def side_stats(rows: list[dict], start: str | None, end: str | None) -> dict:
    """Median NDVI of each bank in a window (for detectability: a bank already bare can't show a new wall)."""
    out = {}
    for k in ("l", "r"):
        v = [r[f"ndvi_{k}"] for r in rows if r.get(f"ndvi_{k}") is not None and (start is None or r["date"] >= start)
             and (end is None or r["date"] <= end)]
        if len(v) >= 3:
            out[k] = round(float(np.median(v)), 3)
    return out


def disturbance(rows: list[dict], *, min_shift: float = 0.15, field: str = "ndvi", after: str | None = None) -> dict | None:
    """First season whose bank NDVI falls at least `min_shift` below the same season in earlier years, even if it
    recovers later: cleared ground, equipment, fresh concrete, then regrowth. A change of state, not a wall."""
    ss = seasons(rows, field)
    for i, s in enumerate(ss):
        if after and s["first"] < after:
            continue
        prior = [x["ndvi"] for x in ss[:i] if x["kind"] == s["kind"]][-2:]
        if prior and s["ndvi"] <= float(np.median(prior)) - min_shift:
            return {"date": s["first"], "season": s["key"], "ndvi_before": round(float(np.median(prior)), 3),
                    "ndvi_after": round(s["ndvi"], 3)}
    return None


def disturbance_any_bank(rows: list[dict], *, min_shift: float = 0.15, after: str | None = None) -> dict | None:
    found = []
    for field, where in (("ndvi", "both banks"), ("ndvi_l", "left bank"), ("ndvi_r", "right bank")):
        d = disturbance(rows, min_shift=min_shift, field=field, after=after)
        if d:
            found.append({**d, "bank": where})
    return min(found, key=lambda f: f["date"]) if found else None
