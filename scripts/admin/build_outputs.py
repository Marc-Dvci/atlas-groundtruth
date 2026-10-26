import json, os, sys
from shapely.geometry import shape, mapping, Point
from shapely.validation import explain_validity

RAW = "D:/Boulot temp/Meta global hackathon/atlas/data/raw/psa_admin"
OUT = "D:/Boulot temp/Meta global hackathon/atlas/data/admin"
TOL = 0.00005

def clean_muni(n):
    n = n.replace("City of ", "").replace(" (Capital)", "").replace(" (Bigaa)", "").strip()
    if n == "Bulacan":  # source labels the town of Bulakan as "Bulacan"
        n = "Bulakan"
    return n

def round_coords(c):
    if isinstance(c[0], (int, float)):
        return [round(c[0], 6), round(c[1], 6)]
    return [round_coords(x) for x in c]

def simp_geojson(geom):
    g = shape(geom).simplify(TOL, preserve_topology=True)
    m = mapping(g)
    m["coordinates"] = round_coords(m["coordinates"])
    return m, g

def load(name):
    with open(f"{RAW}/{name}", encoding="utf-8") as fh:
        return json.load(fh)["features"]

def write(path, feats):
    fc = {"type": "FeatureCollection", "features": feats}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(fc, fh, ensure_ascii=False, separators=(",", ":"))
    return os.path.getsize(path)

# ---- barangays
b_src = load("bulacan_adm4_raw.geojson")
b_feats, b_geoms = [], []
for f in b_src:
    p = f["properties"]
    gj, g = simp_geojson(f["geometry"])
    b_feats.append({"type": "Feature",
                    "properties": {"name": p["adm4_name"],
                                   "muni": clean_muni(p["adm3_name"]),
                                   "psgc": p["adm4_pcode"][2:]},
                    "geometry": gj})
    b_geoms.append((p["adm4_name"], clean_muni(p["adm3_name"]), g, p["adm4_pcode"]))
bsize = write(f"{OUT}/bulacan_barangays.geojson", b_feats)
print("barangays:", len(b_feats), "bytes:", bsize)
print("  invalid after round:", sum(1 for ft in b_feats if not shape(ft["geometry"]).is_valid))
print("  empty:", sum(1 for ft in b_feats if shape(ft["geometry"]).is_empty))

# ---- municipalities (official ADM3 layer)
m_src = load("bulacan_adm3_raw.geojson")
m_feats, m_geoms = [], {}
for f in m_src:
    p = f["properties"]
    gj, g = simp_geojson(f["geometry"])
    nm = clean_muni(p["adm3_name"])
    m_feats.append({"type": "Feature",
                    "properties": {"name": nm, "muni": nm, "psgc": p["adm3_pcode"][2:] + "000"},
                    "geometry": gj})
    m_geoms[nm] = g
m_feats.sort(key=lambda ft: ft["properties"]["name"])
msize = write(f"{OUT}/bulacan_municipalities.geojson", m_feats)
print("municipalities:", len(m_feats), "bytes:", msize)

# ---- consistency: ADM3 polygon area vs union of its barangays (original geometry)
import collections
from shapely.ops import unary_union
by = collections.defaultdict(list)
for nm, mu, g, pc in b_geoms:
    by[mu].append(g)
worst = []
for f in b_src:
    pass
src_m = {clean_muni(f["properties"]["adm3_name"]): shape(f["geometry"]) for f in m_src}
for mu, gs in by.items():
    u = unary_union(gs)
    a3 = src_m[mu].area
    worst.append((abs(u.area - a3) / a3, mu, len(gs), round(u.area / a3, 4)))
worst.sort(reverse=True)
print("muni vs union-of-barangays area diff (top 5, rel, muni, n_bgy, ratio):", [(round(w,4), m, n, r) for w, m, n, r in worst[:5]])
print("  munis with barangays:", len(by))

# ---- point checks on OUTPUT geometry
bf = json.load(open(f"{OUT}/bulacan_barangays.geojson", encoding="utf-8"))["features"]
mf = json.load(open(f"{OUT}/bulacan_municipalities.geojson", encoding="utf-8"))["features"]
bsh = [(ft["properties"], shape(ft["geometry"])) for ft in bf]
msh = [(ft["properties"], shape(ft["geometry"])) for ft in mf]
for lon, lat in [(120.879176, 14.990567), (120.892235, 14.765788)]:
    p = Point(lon, lat)
    bh = [pr for pr, g in bsh if g.contains(p)]
    mh = [pr["name"] for pr, g in msh if g.contains(p)]
    print(f"point ({lon}, {lat}) -> barangay {[ (x['name'], x['muni'], x['psgc']) for x in bh]} | muni {mh}")
print("munis by barangay count:", sorted(collections.Counter(ft["properties"]["muni"] for ft in bf).items()))
