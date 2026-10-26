# Atlas · Groundtruth

Atlas checks what a government declared against what the Earth shows. Its first mission, Groundtruth,
audits whether paid flood-control works in the Philippines were actually built.

## Run it

```
python -m venv --system-site-packages .venv
.venv/Scripts/python -m pip install rasterio shapely pyproj mercantile httpx fastapi uvicorn
cp .env.example .env            # add MODEL_API_KEY
.venv/Scripts/python scripts/build_portfolio.py
.venv/Scripts/python scripts/overlaps.py
.venv/Scripts/python -m uvicorn atlas.server:app --port 8787
cd web && npm install && npm run dev   # http://localhost:5317
```

Audit one contract from the command line: `.venv/Scripts/python -m atlas.audit 24CC0144 --run dev`.

## Layout

- `atlas/agents/` Locator (Muse Spark tool loop), Existence (Wayback history + SAM 3.1 + Muse Spark reading,
  Sentinel-2 banks), Timeline / Valuation / Impact (code), Case builder (Muse Wonder, Muse Image illustration)
- `atlas/verdict.py` the evidence calculus: outcomes are computed by rules, never by a model
- `atlas/ledger.py` append-only, hash-chained evidence ledger; pixels sealed by content hash
- `atlas/fleet.py`, `atlas/server.py` mission planning against budget and deadline; HTTP API
- `web/` the investigator's interface (React, MapLibre)
- `data/answer_key/` official findings used only by the evaluation, never by an audit

## Data

DPWH flood-control projects (President's portal mirror, 9,855 rows; BetterGov DPWH API), Esri World Imagery Wayback,
Sentinel-2 L2A (Element84 Earth Search), Copernicus DEM GLO-30, Meta & CIESIN HRSL population (CC BY 4.0),
OpenStreetMap waterways (ODbL), PSA/NAMRIA barangay boundaries via OCHA COD-AB (CC BY-IGO).
