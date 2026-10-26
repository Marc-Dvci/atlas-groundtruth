import io, sys, json, zipfile, collections
SP = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
sys.path.insert(0, SP)
from rangezip import HTTPRangeFile
URL = "https://data.humdata.org/dataset/caf116df-f984-4deb-85ca-41b349d3f313/resource/0120c30e-ba8b-487d-83f5-a664eddd3a8e/download/phl_admin_boundaries.geojson.zip"
RAW = "D:/Boulot temp/Meta global hackathon/atlas/data/raw/psa_admin"

def stream_layer(member):
    raw = HTTPRangeFile(URL)
    buf = io.BufferedReader(raw, buffer_size=16 * 1024 * 1024)
    z = zipfile.ZipFile(buf)
    kept, total = [], 0
    with z.open(member) as f:
        for line in f:
            s = line.strip()
            if not (s.startswith(b'{"type"') and b"Feature" in s[:40]):
                continue
            total += 1
            if s.endswith(b","):
                s = s[:-1]
            obj = json.loads(s)
            if obj["properties"].get("adm2_name") == "Bulacan":
                kept.append(obj)
    return kept, total

for member, out in [("phl_admin4.geojson", "bulacan_adm4_raw.geojson"),
                    ("phl_admin3.geojson", "bulacan_adm3_raw.geojson")]:
    feats, total = stream_layer(member)
    print(member, "total features streamed:", total, "Bulacan kept:", len(feats))
    fc = {"type": "FeatureCollection", "name": member[:-8], "features": feats}
    with open(f"{RAW}/{out}", "w", encoding="utf-8") as fh:
        json.dump(fc, fh, ensure_ascii=False)
    print("  saved", out)
    c = collections.Counter()
    for ft in feats:
        p = ft["properties"]
        c["adm2_pcode=" + str(p.get("adm2_pcode"))] += 1
        c["valid_to_nonnull"] += p.get("valid_to") is not None
        c["geom=" + ft["geometry"]["type"]] += 1
    print("  ", dict(c))
    pcodes = [ft["properties"]["adm4_pcode" if "adm4" in member else "adm3_pcode"] for ft in feats]
    print("   unique pcodes:", len(set(pcodes)), "rows:", len(pcodes))
