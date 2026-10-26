"""Small raster helpers: chip georeferencing, masks to polygons, skeletons."""
from __future__ import annotations

import io
import math
import warnings

import numpy as np
from PIL import Image, ImageDraw
from rasterio.features import shapes
from rasterio.transform import from_bounds
from shapely.geometry import LineString, MultiPolygon, shape
from shapely.ops import unary_union


def merc_y(lat: float) -> float:
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def inv_merc_y(y: float) -> float:
    return math.degrees(2 * math.atan(math.exp(y)) - math.pi / 2)


class Chip:
    """An image of bbox (lon/lat) in Web Mercator pixel space."""

    def __init__(self, img: Image.Image, bbox: tuple[float, float, float, float]):
        self.img = img.convert("RGB")
        self.bbox = bbox
        self.w, self.h = self.img.size

    def to_px(self, lon: float, lat: float) -> tuple[float, float]:
        w, s, e, n = self.bbox
        x = (lon - w) / (e - w) * self.w
        y = (merc_y(n) - merc_y(lat)) / (merc_y(n) - merc_y(s)) * self.h
        return x, y

    def to_lonlat(self, x: float, y: float) -> tuple[float, float]:
        w, s, e, n = self.bbox
        lon = w + x / self.w * (e - w)
        lat = inv_merc_y(merc_y(n) - y / self.h * (merc_y(n) - merc_y(s)))
        return lon, lat

    def jpeg(self, quality: int = 88) -> bytes:
        b = io.BytesIO()
        self.img.save(b, "JPEG", quality=quality)
        return b.getvalue()

    def with_line(self, line: LineString, color=(95, 211, 255), width: int = 4, label: str | None = None) -> bytes:
        im = self.img.copy()
        d = ImageDraw.Draw(im)
        pts = [self.to_px(x, y) for x, y in line.coords]
        d.line(pts, fill=color, width=width, joint="curve")
        for p in (pts[0], pts[-1]):
            d.ellipse([p[0] - 6, p[1] - 6, p[0] + 6, p[1] + 6], outline=color, width=3)
        if label:
            d.rectangle([0, 0, 8 + 7 * len(label), 22], fill=(0, 0, 0))
            d.text((5, 5), label, fill=(255, 255, 255))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=88)
        return b.getvalue()

    def mask_to_geo(self, mask: np.ndarray, box: tuple[int, int, int, int], simplify_px: float = 1.5):
        """Box-local boolean mask (SAM) to a lon/lat polygon."""
        x1, y1, x2, y2 = box
        h, w = mask.shape
        tr = from_bounds(x1, y1 + h, x1 + w, y1, w, h)  # pixel space, y down
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            polys = [shape(g).simplify(simplify_px) for g, v in shapes(mask.astype(np.uint8), mask=mask, transform=tr) if v == 1]
        if not polys:
            return None
        u = unary_union(polys)

        def conv(poly):
            ext = [self.to_lonlat(x, y) for x, y in poly.exterior.coords]
            holes = [[self.to_lonlat(x, y) for x, y in r.coords] for r in poly.interiors]
            from shapely.geometry import Polygon
            return Polygon(ext, holes)

        if u.geom_type == "Polygon":
            return conv(u)
        return MultiPolygon([conv(p) for p in u.geoms if p.geom_type == "Polygon"])

    def box_to_geo(self, box: tuple[int, int, int, int]):
        from shapely.geometry import box as sbox
        x1, y1, x2, y2 = box
        (a, b), (c, d) = self.to_lonlat(x1, y2 + 1), self.to_lonlat(x2 + 1, y1)
        return sbox(a, b, c, d)


def full_mask(obj_mask: np.ndarray, box, size) -> np.ndarray:
    W, H = size
    out = np.zeros((H, W), dtype=bool)
    x1, y1, x2, y2 = box
    h, w = obj_mask.shape
    out[y1:y1 + h, x1:x1 + w] = obj_mask[: max(0, min(h, H - y1)), : max(0, min(w, W - x1))]
    return out


def zhang_suen(img: np.ndarray) -> np.ndarray:
    """Thin a binary image to a 1-pixel skeleton (Zhang-Suen, vectorised)."""
    im = np.pad(img.astype(np.uint8), 1)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            P = im
            p2, p3, p4 = P[:-2, 1:-1], P[:-2, 2:], P[1:-1, 2:]
            p5, p6, p7 = P[2:, 2:], P[2:, 1:-1], P[2:, :-2]
            p8, p9 = P[1:-1, :-2], P[:-2, :-2]
            nb = [p2, p3, p4, p5, p6, p7, p8, p9]
            B = sum(x.astype(np.int32) for x in nb)
            seq = nb + [p2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.int32) for i in range(8))
            c = P[1:-1, 1:-1] == 1
            if step == 0:
                m = c & (B >= 2) & (B <= 6) & (A == 1) & ((p2 * p4 * p6) == 0) & ((p4 * p6 * p8) == 0)
            else:
                m = c & (B >= 2) & (B <= 6) & (A == 1) & ((p2 * p4 * p8) == 0) & ((p2 * p6 * p8) == 0)
            if m.any():
                im[1:-1, 1:-1][m] = 0
                changed = True
    return im[1:-1, 1:-1].astype(bool)


def longest_skeleton_path(skel: np.ndarray) -> list[tuple[int, int]]:
    """Longest shortest-path through the skeleton graph (two BFS passes), as (x, y) pixels."""
    from collections import deque
    ys, xs = np.nonzero(skel)
    if len(xs) == 0:
        return []
    nodes = set(zip(xs.tolist(), ys.tolist()))

    def bfs(start):
        prev = {start: None}
        q = deque([start])
        last = start
        while q:
            p = q.popleft()
            last = p
            x, y = p
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (x + dx, y + dy)
                    if n in nodes and n not in prev:
                        prev[n] = p
                        q.append(n)
        return last, prev

    a, _ = bfs(next(iter(nodes)))
    b, prev = bfs(a)
    path = []
    p = b
    while p is not None:
        path.append(p)
        p = prev[p]
    return path
