"""Who lives behind the wall.

Population: Meta / CIESIN High Resolution Settlement Layer (HRSL, CC BY 4.0),
~30 m cells, public COGs on AWS. Ground height: Copernicus DEM GLO-30.

A flood wall protects the low ground beside its reach. We count the people in
cells within `radius_m` of the reach whose ground is at most `rise_m` above the
river bank there (a simple height-above-river screen, not a flood model).
"""
from __future__ import annotations

import math
import os

import numpy as np

os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

import rasterio  # noqa: E402
from rasterio.features import geometry_mask  # noqa: E402
from rasterio.warp import Resampling, reproject  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402
from shapely.geometry import mapping, shape  # noqa: E402

from .geom import buffer_m  # noqa: E402

HRSL = "https://dataforgood-fb-data.s3.amazonaws.com/hrsl-cogs/hrsl_general/v1.5/cog_globallat_10_lon_120_general-v1.5.3.tif"
DEM = "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif"


def _dem_url(lon: float, lat: float) -> str:
    la, lo = math.floor(lat), math.floor(lon)
    return DEM.format(ns="N" if la >= 0 else "S", lat=abs(la), ew="E" if lo >= 0 else "W", lon=abs(lo))


def _read_wgs(url: str, bbox):
    with rasterio.open(url) as ds:
        win = from_bounds(*bbox, transform=ds.transform)
        arr = ds.read(1, window=win, boundless=True, fill_value=0).astype(np.float32)
        return arr, ds.window_transform(win), ds.nodata


def people_behind(reach_geo: dict, radius_m: float = 1500, rise_m: float = 3.0) -> dict:
    reach = shape(reach_geo)
    zone = buffer_m(reach, radius_m)
    bbox = zone.bounds
    pop, ptr, pnd = _read_wgs(HRSL, bbox)
    if pnd is not None:
        pop[pop == pnd] = 0
    pop[~np.isfinite(pop)] = 0
    pop[pop < 0] = 0
    # DEM onto the population grid (the reach may straddle a 1-degree tile edge; use the centre tile)
    c = reach.centroid
    with rasterio.open(_dem_url(c.x, c.y)) as ds:
        dem = np.zeros_like(pop)
        reproject(rasterio.band(ds, 1), dem, dst_transform=ptr, dst_crs="EPSG:4326", resampling=Resampling.bilinear)
    in_zone = ~geometry_mask([mapping(zone)], out_shape=pop.shape, transform=ptr, all_touched=False)
    # Bank height: the reach line runs down the water, so sample the land ring 40-200 m from it and take
    # its lower quartile (the ground beside the river, not the water surface and not the hills).
    ring = (~geometry_mask([mapping(buffer_m(reach, 200))], out_shape=pop.shape, transform=ptr, all_touched=True)
            & geometry_mask([mapping(buffer_m(reach, 40))], out_shape=pop.shape, transform=ptr, all_touched=True))
    sample = dem[ring] if ring.any() else dem[in_zone]
    bank = float(np.percentile(sample, 25))
    low = in_zone & (dem <= bank + rise_m)
    total = float(pop[in_zone].sum())
    behind = float(pop[low].sum())
    # cells for the map: centre points of populated low cells, with their count
    ys, xs = np.nonzero(low & (pop > 0))
    pts = []
    for y, x in zip(ys, xs):
        lon, lat = ptr * (x + 0.5, y + 0.5)
        pts.append([round(lon, 6), round(lat, 6), round(float(pop[y, x]), 2)])
    return {
        "people_low_ground": round(behind),
        "people_in_radius": round(total),
        "radius_m": radius_m,
        "rise_m": rise_m,
        "bank_elevation_m": round(bank, 1),
        "cells": pts,
        "method": f"HRSL v1.5 population in cells within {radius_m:.0f} m of the reach and at most {rise_m:.0f} m above "
                  f"the bank ({bank:.1f} m, Copernicus DEM GLO-30).",
    }
