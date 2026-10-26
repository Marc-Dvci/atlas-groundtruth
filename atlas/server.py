"""HTTP API for the Atlas web app.

    .venv/Scripts/python -m uvicorn atlas.server:app --port 8787
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from .audit import open_run, portfolio
from .case import DATA, ROOT
from .fleet import Fleet
from .geo.wayback import BASE as WAYBACK
from .ledger import Ledger

app = FastAPI(title="Atlas")
_fleets: dict[str, Fleet] = {}
_tiles = httpx.Client(timeout=30, headers={"User-Agent": "Atlas-Groundtruth/0.1"})


def _run_dir(run: str) -> Path:
    if not run.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(400, "bad run name")
    return DATA / "runs" / run


@app.get("/api/summary")
def summary():
    s = json.loads((DATA / "portfolio/summary.json").read_text(encoding="utf-8"))
    ov = DATA / "portfolio/overlaps.json"
    s["overlaps"] = json.loads(ov.read_text(encoding="utf-8")) if ov.exists() else []
    pins = DATA / "portfolio/pins.json"
    s["pins"] = {k: v for k, v in json.loads(pins.read_text(encoding="utf-8")).items() if k != "worst"} if pins.exists() else None
    return s


@app.get("/api/province/{name}")
def province(name: str):
    recs = [r for r in portfolio().values() if (r.get("province") or "").lower() == name.lower()]
    keep = ("id", "desc", "muni", "contractor", "cost", "abc", "start", "completion", "lon", "lat", "flags", "priority",
            "suspicion", "length_m", "cost_per_m", "status", "source", "year")
    return [{k: r.get(k) for k in keep} for r in sorted(recs, key=lambda r: -(r.get("priority") or 0))]


@app.get("/api/project/{cid}")
def project(cid: str):
    r = portfolio().get(cid)
    if not r:
        raise HTTPException(404)
    return r


@app.get("/api/runs")
def runs():
    out = []
    for d in sorted((DATA / "runs").glob("*")):
        if d.is_dir():
            out.append({"run": d.name, "cases": sorted(p.name for p in (d / "cases").glob("*")) if (d / "cases").exists() else []})
    return out


@app.get("/api/runs/{run}/cases/{cid}")
def case(run: str, cid: str):
    p = _run_dir(run) / "cases" / cid / "case.json"
    if not p.exists():
        raise HTTPException(404)
    return JSONResponse(json.loads(p.read_text(encoding="utf-8")))


@app.get("/api/runs/{run}/cases")
def cases(run: str):
    out = []
    for p in sorted((_run_dir(run) / "cases").glob("*/case.json")):
        c = json.loads(p.read_text(encoding="utf-8"))
        out.append({"id": c["id"], "outcome": (c.get("verdict") or {}).get("outcome"),
                    "reason": (c.get("verdict") or {}).get("reason"), "headline": (c.get("verdict") or {}).get("headline"),
                    "cost": c["record"].get("cost"), "lon": c["record"].get("lon"), "lat": c["record"].get("lat"),
                    "located": (c.get("locator") or {}).get("center"), "seconds": c.get("seconds")})
    return out


@app.get("/api/runs/{run}/events")
async def events(run: str, request: Request, since: int = 0, speed: float = 0.0):
    """Server-sent events from the run log. speed=0 streams live (tail); speed>0 replays
    the recorded log with its original pacing divided by `speed`."""
    path = _run_dir(run) / "events.jsonl"

    async def gen():
        n = 0
        last_t = None
        while not path.exists():
            await asyncio.sleep(0.5)
        with path.open(encoding="utf-8") as f:
            while True:
                if await request.is_disconnected():
                    return
                line = f.readline()
                if not line:
                    if speed > 0:
                        yield "event: end\ndata: {}\n\n"
                        return
                    await asyncio.sleep(0.25)
                    continue
                n += 1
                if n <= since:
                    continue
                if speed > 0:
                    t = json.loads(line).get("t", 0)
                    if last_t is not None:
                        await asyncio.sleep(min(4.0, max(0.0, (t - last_t) / speed)))
                    last_t = t
                yield f"id: {n}\ndata: {line.strip()}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/api/runs/{run}/launch")
async def launch(run: str, request: Request):
    body = await request.json()
    ids = body.get("ids") or []
    if not ids:
        raise HTTPException(400, "no projects")
    if run in _fleets:
        raise HTTPException(409, "run already active")
    fl = Fleet(run, workers=int(body.get("workers", 4)))
    _fleets[run] = fl
    threading.Thread(target=lambda: (fl.launch(ids, mission=body.get("mission", ""), budget_usd=float(body.get("budget_usd", 20)),
                                               deadline=body.get("deadline"), lm=body.get("lm", "meta"),
                                               full_top=int(body.get("full_top", 0))), _fleets.pop(run, None)), daemon=True).start()
    return {"ok": True}


@app.get("/api/runs/{run}/ledger")
def ledger(run: str, case: str | None = None, limit: int = 500):
    lg = Ledger(_run_dir(run) / "ledger.jsonl", DATA / "evidence")
    rows = [e.as_dict() for e in lg.entries() if case is None or e.case in (case, "*")]
    return rows[-limit:]


@app.get("/api/runs/{run}/ledger.jsonl")
def ledger_raw(run: str):
    """The ledger exactly as written, for verification in the browser."""
    p = _run_dir(run) / "ledger.jsonl"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="application/x-ndjson")


@app.get("/api/runs/{run}/verify")
def verify(run: str):
    lg = Ledger(_run_dir(run) / "ledger.jsonl", DATA / "evidence")
    t = time.time()
    ok, bad, why = lg.verify()
    n = sum(1 for _ in lg.entries())
    return {"ok": ok, "first_bad": bad, "reason": why, "entries": n, "head": lg.head, "ms": round((time.time() - t) * 1000)}


@app.post("/api/runs/{run}/cases/{cid}/sign")
async def sign(run: str, cid: str, request: Request):
    body = await request.json()
    name = (body.get("investigator") or "").strip()
    decision = body.get("decision")
    if not name or decision not in ("concur", "dissent", "refer_for_site_visit"):
        raise HTTPException(400, "investigator and decision (concur | dissent | refer_for_site_visit) required")
    lg, _ = open_run(run)
    c = case(run, cid)
    v = json.loads(c.body)["verdict"]
    e = lg.append(cid, f"human:{name}", "signature", {"decision": decision, "note": body.get("note", ""),
                                                      "verdict": v["outcome"], "reason": v["reason"]})
    return e.as_dict()


@app.post("/api/runs/{run}/tamper-demo")
async def tamper_demo(run: str, request: Request):
    """Copy the run's ledger, change one sealed claim (as someone editing the file would), verify both.
    The original is never touched."""
    import shutil
    body = await request.json()
    cid = body.get("case")
    src = _run_dir(run) / "ledger.jsonl"
    dst_dir = _run_dir(f"{run}-tampered")
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "ledger.jsonl"
    shutil.copyfile(src, dst)
    lines = dst.read_text(encoding="utf-8").splitlines()
    changed = None
    for i, line in enumerate(lines):
        e = json.loads(line)
        f = (e.get("payload") or {}).get("finding")
        if e["kind"] == "finding" and (cid is None or e["case"] == cid) and f and f.get("claim") in ("absent", "present"):
            before = f["claim"]
            f["claim"] = "present" if before == "absent" else "absent"
            lines[i] = json.dumps(e, ensure_ascii=False)
            changed = {"seq": e["seq"], "field": "finding.claim", "from": before, "to": f["claim"], "source": f.get("source")}
            break
    dst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok1, bad1, why1 = Ledger(src, DATA / "evidence").verify()
    ok2, bad2, why2 = Ledger(dst, DATA / "evidence").verify()
    return {"changed": changed, "original": {"ok": ok1, "first_bad": bad1, "reason": why1},
            "tampered": {"ok": ok2, "first_bad": bad2, "reason": why2}}


@app.get("/api/evidence/{name}")
def evidence(name: str):
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(400)
    p = DATA / "evidence" / name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/api/wayback/{release}/{z}/{y}/{x}")
def wayback_tile(release: int, z: int, y: int, x: int):
    """Wayback tiles through a disk cache: the case view scrubs through releases instantly."""
    p = DATA / "cache/wayback/tiles" / str(release) / f"{z}_{x}_{y}.jpg"
    if not p.exists():
        try:
            r = _tiles.get(f"{WAYBACK}/tile/{release}/{z}/{y}/{x}", follow_redirects=True)
        except httpx.HTTPError:
            return Response(status_code=504)
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image"):
            return Response(status_code=404)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(r.content)
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000"})


@app.post("/api/mission/voice")
async def mission_voice(request: Request):
    """Body: a mono 16-bit WAV (16 or 24 kHz). Muse Voice Transcribe, then Muse Spark parses the mission."""
    from .audit import make_client
    from .mission import parse, transcribe
    wav = await request.body()
    client = make_client()
    if client is None:
        raise HTTPException(503, "no model access")
    tr = transcribe(client, wav)
    return {"transcript": tr.get("transcript", ""), "audio_ms": tr.get("audioDurationMs"),
            "mission": parse(client, tr.get("transcript", ""))}


@app.post("/api/mission/text")
async def mission_text(request: Request):
    from .audit import make_client
    from .mission import parse
    body = await request.json()
    client = make_client()
    if client is None:
        raise HTTPException(503, "no model access")
    return {"transcript": body.get("text", ""), "mission": parse(client, body.get("text", ""))}


@app.get("/api/meter")
def meter():
    p = DATA / "meter.json"
    return json.loads(p.read_text()) if p.exists() else {"spent_usd": 0, "calls": 0}


@app.get("/api/runs/{run}/evaluation")
def evaluation(run: str):
    out = _evaluate_module().score(run)
    key = {k["id"]: k for k in json.loads((DATA / "answer_key/cases.json").read_text(encoding="utf-8"))["cases"]}
    for r in out["rows"]:
        k = key[r["id"]]
        r["quote"], r["date"], r["sources"] = k["quote"], k["date"], k["sources"]
        rec = portfolio().get(r["id"]) or {}
        r["desc"], r["cost"], r["muni"] = rec.get("desc"), rec.get("cost"), rec.get("muni")
    return out


def _evaluate_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("evaluate", ROOT / "scripts/evaluate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@app.get("/api/runs/{run}/compare/{other}")
def compare(run: str, other: str):
    """The same contracts audited with two model hosts (Muse Spark 1.3 and Muse Spark Open)."""
    _run_dir(run), _run_dir(other)
    return _evaluate_module().compare(run, other)


@app.get("/api/open_meter")
def open_meter():
    p = DATA / "meter_open.json"
    return json.loads(p.read_text()) if p.exists() else {"spent_usd": 0, "calls": 0}


@app.get("/api/answer_key")
def answer_key():
    return json.loads((DATA / "answer_key/cases.json").read_text(encoding="utf-8"))


_ = ROOT
