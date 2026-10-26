# Fetch all "Flood Control and Drainage" records from the public BetterGov DPWH API (no login).
import csv, json, sys, time, urllib.request, urllib.parse, os
from pathlib import Path

API = "https://api.dpwh.bettergov.ph/projects"
CAT = "Flood Control and Drainage"
OUT = Path("D:/Boulot temp/Meta global hackathon/atlas/data/raw/bettergov_api_flood_control")
OUT.mkdir(parents=True, exist_ok=True)
LIMIT = 2000
UA = "Mozilla/5.0 (research; Groundtruth hackathon data survey)"

def get(page):
    q = urllib.parse.urlencode({"category": CAT, "page": page, "limit": LIMIT})
    last = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)["data"]
        except Exception as e:
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"page {page} failed: {last}")

first = get(1)
total = int(first["pagination"]["totalCount"])
pages = int(first["pagination"]["totalPages"])
print("expected", total, "pages", pages, flush=True)
rows = list(first["data"])
for p in range(2, pages + 1):
    rows.extend(get(p)["data"])
    if p % 3 == 0:
        print("page", p, "rows", len(rows), flush=True)
print("fetched", len(rows), flush=True)

with (OUT / "projects.jsonl").open("w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

keys = []
for r in rows:
    for k in r.keys():
        if k not in keys:
            keys.append(k)
loc_keys = []
for r in rows:
    loc = r.get("location") or {}
    if isinstance(loc, dict):
        for k in loc.keys():
            if k not in loc_keys:
                loc_keys.append(k)
flat_cols = [k for k in keys if k != "location"] + ["loc_" + k for k in loc_keys]
with (OUT / "projects.csv").open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=flat_cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        d = {k: r.get(k) for k in keys if k != "location"}
        loc = r.get("location") or {}
        for k in loc_keys:
            d["loc_" + k] = loc.get(k) if isinstance(loc, dict) else None
        w.writerow(d)

meta = {"source": API, "filter": {"category": CAT}, "expectedCount": total, "count": len(rows),
        "limit": LIMIT, "location_keys": loc_keys, "fields": keys, "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
(OUT / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
if len(rows) != total:
    print("WARNING count mismatch", len(rows), total)
print("done", len(rows), "loc_keys", loc_keys)
