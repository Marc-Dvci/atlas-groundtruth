"""Atlas live: the API and the web app on Modal, so anyone can audit a contract live.

    sh deploy/upload.sh                      # once: the data the audits read, onto the atlas-data volume
    modal run deploy/modal_app.py::dry_run   # no keys, no model call: imports, maps, imagery, Sentinel-2
    modal deploy deploy/modal_app.py

One container (live audits are one at a time, and their state lives in the process). Data, evidence and new runs are
kept on a Modal volume; keys come from the `atlas-keys` secret. The live budget and the daily cap are set below.
"""
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
vol = modal.Volume.from_name("atlas-data", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install(
        "fastapi==0.115.6", "uvicorn==0.32.1", "httpx==0.28.1", "shapely==2.1.2", "numpy==2.2.6", "rasterio==1.4.4",
        "pyproj==3.7.1", "pillow==12.2.0", "scipy==1.15.3", "mercantile==1.2.1", "cryptography==46.0.3", "certifi",
        "requests",
    )
    .env({"ATLAS_DATA": "/data", "ATLAS_LIVE": "1", "ATLAS_LIVE_OPEN": "1",  # open to anyone, within the caps below
          "ATLAS_LIVE_BUDGET_USD": "15", "ATLAS_LIVE_PER_DAY": "30",
          "ATLAS_SELF_ENROL": "1", "GDAL_HTTP_TIMEOUT": "60",
          # caps for the meters a hosted server could reach: Meta outside live audits, and Baseten (the second reader)
          "ATLAS_BUDGET_USD": "15", "ATLAS_OPEN_BUDGET_USD": "5"})
    .add_local_dir(ROOT / "web" / "dist-live", "/web")
    .add_local_dir(ROOT / "atlas", "/root/atlas", ignore=["**/__pycache__/**"])  # /root is on the container's path
)
app = modal.App("atlas-live", image=image)


@app.function(volumes={"/data": vol}, secrets=[modal.Secret.from_name("atlas-keys")], cpu=2.0, memory=4096,
              timeout=3600, max_containers=1, scaledown_window=900)
@modal.concurrent(max_inputs=40)
@modal.asgi_app()
def web():
    from fastapi.staticfiles import StaticFiles

    from atlas import server

    server.ON_AUDIT_DONE.append(vol.commit)  # keep each live run on the volume once it is sealed
    server.app.mount("/", StaticFiles(directory="/web", html=True), name="web")
    return server.app


check_app = modal.App("atlas-check", image=image)  # its own app: it needs no secret


@check_app.function(volumes={"/data": vol}, cpu=2.0, memory=4096, timeout=900)
def check() -> dict:
    """Dry run with no keys and no model call: the code imports, the maps load from the volume, and the imagery an
    audit reads arrives (Wayback captures, a sub-metre chip, a Sentinel-2 series)."""
    import time
    from pathlib import Path

    t = time.time()
    from atlas import server  # noqa: F401  the whole API imports
    from atlas.agents import existence
    from atlas.audit import portfolio
    from atlas.geo.geom import bbox_around
    from atlas.geo.index import get_index
    from atlas.geo.s2series import series
    out: dict = {"import_s": round(time.time() - t, 1)}
    rec = portfolio()["24CC0055"]
    out["contracts"] = len(portfolio())
    out["barangays_named_malis"] = len(get_index().find_barangays("Malis", rec.get("muni")))
    caps = existence.captures(rec["lon"], rec["lat"])
    out["wayback_captures"] = len(caps)
    chip = existence.chip_for(caps[-1]["release"], bbox_around((rec["lon"], rec["lat"]), 150))
    out["chip_px"] = [chip.w, chip.h]
    reach = {"type": "LineString", "coordinates": [[rec["lon"] - 0.001, rec["lat"]], [rec["lon"] + 0.001, rec["lat"]]]}
    rows = series(reach, "2025-01-01", "2025-06-30", Path("/tmp/s2"), workers=8, per_month=1)
    out["s2_scenes"] = len([r for r in rows if r.get("ndvi") is not None])
    out["total_s"] = round(time.time() - t, 1)
    return out


@check_app.local_entrypoint()
def dry_run():
    print(check.remote())
