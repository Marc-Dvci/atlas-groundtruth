"""HTTP API for the Atlas web app.

    .venv/Scripts/python -m uvicorn atlas.server:app --port 8787
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
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
from .signing import CHALLENGES, DECISIONS, check_entry, key_id, registry

app = FastAPI(title="Atlas")
_fleets: dict[str, Fleet] = {}
_tiles = httpx.Client(timeout=30, headers={"User-Agent": "Atlas-Groundtruth/0.1"})
# live audits (a hosted demo: one contract at a time, from scratch, under a hard budget)
LIVE_ON = os.environ.get("ATLAS_LIVE") == "1"
LIVE_BUDGET = float(os.environ.get("ATLAS_LIVE_BUDGET_USD", "15"))
LIVE_PER_DAY = int(os.environ.get("ATLAS_LIVE_PER_DAY", "30"))
_live: dict = {"thread": None, "run": None, "id": None, "started": None}
ON_AUDIT_DONE: list = []  # hooks a host adds, e.g. committing a volume
REPLAY_GAP_S = 4.0  # a replay cuts longer idle stretches (a stopped and resumed mission) to this many recorded seconds


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
async def events(run: str, request: Request, since: int = 0, speed: float = 0.0, duration: float = 0.0):
    """Server-sent events from the run log. speed=0 streams live (tail); speed>0 replays
    the recorded log with its original pacing divided by `speed`; duration>0 replays the whole
    recording in about that many seconds."""
    path = _run_dir(run) / "events.jsonl"
    if duration > 0 and path.exists():
        with path.open(encoding="utf-8") as f:
            ts = [json.loads(line).get("t", 0) for line in f if line.strip()]
        span = sum(min(REPLAY_GAP_S, max(0.0, b - a)) for a, b in zip(ts, ts[1:]))
        speed = max(1.0, span / duration)

    async def gen():
        n = 0
        last_t = None
        replay = 0.0  # recorded seconds so far, idle stretches cut to REPLAY_GAP_S
        while not path.exists():
            await asyncio.sleep(0.5)
        start = time.monotonic()
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
                    # an absolute schedule: thousands of sub-millisecond gaps must not each cost a timer tick
                    t = json.loads(line).get("t", 0)
                    if last_t is not None:
                        replay += min(REPLAY_GAP_S, max(0.0, t - last_t))
                    last_t = t
                    ahead = start + replay / speed - time.monotonic()
                    if ahead > 0.004:
                        await asyncio.sleep(ahead)
                yield f"id: {n}\ndata: {line.strip()}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/api/runs/{run}/launch")
async def launch(run: str, request: Request):
    if os.environ.get("ATLAS_LIVE") == "1":
        raise HTTPException(403, "fleet launches are off on the hosted server; use the live audit")
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


INVESTIGATORS = DATA / "investigators.json"
_audits: dict[str, threading.Thread] = {}


def _latest(lg: Ledger, cid: str, kind: str):
    last = None
    for e in lg.entries():
        if e.case == cid and e.kind == kind:
            last = e
    return last


@app.get("/api/investigators")
def investigators():
    return {"investigators": list(registry(INVESTIGATORS).values()),
            "self_enrol": os.environ.get("ATLAS_SELF_ENROL", "1") == "1"}


@app.post("/api/investigators/enrol")
async def enrol(request: Request):
    """Enrol a public key. An audit office enrols its investigators with its admin token; a demo deployment may let
    visitors enrol their own key, and the registry says so next to every visitor key."""
    body = await request.json()
    pk, name = body.get("public_key") or "", (body.get("name") or "").strip()[:80]
    admin = os.environ.get("ATLAS_ADMIN_TOKEN")
    by_office = bool(admin) and request.headers.get("X-Admin-Token") == admin
    if not by_office and os.environ.get("ATLAS_SELF_ENROL", "1") != "1":
        raise HTTPException(403, "enrolment needs the office's admin token")
    try:
        if len(base64.b64decode(pk)) != 32:
            raise ValueError
        kid = key_id(pk)
    except ValueError:
        raise HTTPException(400, "public_key must be a base64 Ed25519 key (32 bytes)")
    if not name:
        raise HTTPException(400, "name required")
    reg = json.loads(INVESTIGATORS.read_text(encoding="utf-8")) if INVESTIGATORS.exists() else {"investigators": []}
    if not any(r["key_id"] == kid for r in reg["investigators"]):
        reg["investigators"].append({"key_id": kid, "name": name, "public_key": pk,
                                     "role": "investigator" if by_office else "visitor (self-enrolled demo key)",
                                     "enrolled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        INVESTIGATORS.write_text(json.dumps(reg, indent=1, ensure_ascii=False), encoding="utf-8")
    return registry(INVESTIGATORS)[kid]


@app.get("/api/runs/{run}/cases/{cid}/to-sign")
def to_sign(run: str, cid: str):
    """What a decision on this case must name: the verdict it is about and the ledger head the investigator saw."""
    lg = Ledger(_run_dir(run) / "ledger.jsonl", DATA / "evidence")
    v = _latest(lg, cid, "verdict")
    if v is None:
        raise HTTPException(404, "no verdict for this case")
    return {"run": run, "case": cid, "verdict": v.payload["outcome"], "verdict_reason": v.payload["reason"],
            "verdict_entry": v.hash, "ledger_head": lg.head, "challenges": CHALLENGES}


@app.post("/api/runs/{run}/cases/{cid}/sign")
async def sign(run: str, cid: str, request: Request):
    """Seal a signed decision. Body: {statement, public_key, signature}; see atlas/signing.py."""
    body = await request.json()
    st, pk, sig = body.get("statement") or {}, body.get("public_key") or "", body.get("signature") or ""
    if st.get("run") != run or st.get("case") != cid:
        raise HTTPException(400, "the statement names another case")
    if st.get("decision") not in DECISIONS:
        raise HTTPException(400, f"decision must be one of {DECISIONS}")
    if st["decision"] == "challenge" and st.get("challenge") not in CHALLENGES:
        raise HTTPException(400, f"a challenge needs a reason: {list(CHALLENGES)}")
    lg = Ledger(_run_dir(run) / "ledger.jsonl", DATA / "evidence")
    v = _latest(lg, cid, "verdict")
    if v is None or st.get("verdict_entry") != v.hash:
        raise HTTPException(409, "the statement is about a verdict that is not this case's current one")
    if not any(e.hash == st.get("ledger_head") for e in lg.entries()):
        raise HTTPException(400, "the statement names a ledger head this ledger never had")
    enrolled = registry(INVESTIGATORS)
    ok, why = check_entry({"statement": st, "public_key": pk, "signature": sig}, enrolled)
    if not ok:
        raise HTTPException(403, why)
    if LIVE_ON and st["decision"] == "challenge" and st.get("challenge") == "WRONG_SITE" and st.get("site"):
        live_gate(request)  # checked before sealing: a challenge that cannot start its re-audit is refused whole
    lg2, _ = open_run(run)
    e = lg2.append(cid, f"human:{st['key_id']}", "challenge" if st["decision"] == "challenge" else "signature",
                   {"statement": st, "public_key": pk, "signature": sig, "investigator": enrolled[st["key_id"]]["name"]})
    out = e.as_dict()
    if st["decision"] == "challenge" and st.get("challenge") == "WRONG_SITE" and st.get("site"):
        lon, lat = (float(x) for x in st["site"].split(","))
        out["reaudit"] = reaudit(run, cid, {"lon": lon, "lat": lat, "challenge_entry": e.hash, "challenge_seq": e.seq})
    return out


def reaudit(run: str, cid: str, site: dict, wait: bool = False) -> dict:
    """Audit the case again at the reach a challenge names. The earlier case file is kept beside the new one, and the
    ledger keeps every earlier entry: a correction adds to the record, it never edits it."""
    from .audit import audit, declarations, make_client
    if cid in _audits and _audits[cid].is_alive():
        raise HTTPException(409, "this case is already being audited again")
    client = (make_client(cap_usd=LIVE_BUDGET, meter_path=DATA / "meter_live.json") if LIVE_ON else make_client())
    if client is None:
        raise HTTPException(503, "no model access")
    lg, rdir = open_run(run)
    cdir = rdir / "cases" / cid
    prev = json.loads((cdir / "case.json").read_text(encoding="utf-8"))
    n = len(list(cdir.glob("case.r*.json"))) + 1
    (cdir / f"case.r{n}.json").write_text(json.dumps(prev, ensure_ascii=False), encoding="utf-8")
    # the mission's own log replays the mission as it ran; a later correction keeps its events beside it
    log = open(rdir / "events_revisions.jsonl", "a", encoding="utf-8")

    def emit(ev) -> None:
        log.write(json.dumps(ev.as_dict(), ensure_ascii=False, default=str) + "\n")
        log.flush()

    def go() -> None:
        out = audit(prev["record"], lg, client, emit, rdir, declaration=declarations().get(cid), depth="full", lm="meta",
                    site=site)
        pv = prev.get("verdict") or {}
        out["revision"] = {"n": n, "challenge_entry": site["challenge_entry"], "challenge_seq": site["challenge_seq"],
                           "previous": (prev.get("revision") or {}).get("previous", []) + [
                               {"outcome": pv.get("outcome"), "reason": pv.get("reason"), "headline": pv.get("headline"),
                                "file": f"case.r{n}.json", "ledger_head": prev.get("ledger_head"),
                                "reach": (prev.get("locator") or {}).get("reach")}]}
        (cdir / "case.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    t = threading.Thread(target=go, daemon=True)
    _audits[cid] = t
    if LIVE_ON:
        _live.update(thread=t, run=run, id=cid, started=time.time())
    t.start()
    if wait:
        t.join()
    return {"started": True, "previous_kept_as": f"case.r{n}.json"}


@app.get("/api/runs/{run}/signatures")
def signatures(run: str):
    """Every sealed decision in the run, with its signature checked against the registry."""
    lg = Ledger(_run_dir(run) / "ledger.jsonl", DATA / "evidence")
    enrolled = registry(INVESTIGATORS)
    out = []
    for e in lg.entries():
        if e.kind in ("signature", "challenge"):
            ok, why = check_entry(e.payload, enrolled)
            out.append({"seq": e.seq, "case": e.case, "kind": e.kind, "ok": ok, "why": why,
                        "decision": (e.payload.get("statement") or {}).get("decision")})
    return out


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
    if LIVE_ON:
        live_gate(request, audit=False)
    wav = await request.body()
    client = make_client()
    if client is None:
        raise HTTPException(503, "no model access")
    tr = transcribe(client, wav)
    text = re.sub(r"\.{2,}$", ".", (tr.get("transcript") or "").strip())
    return {"transcript": text, "audio_ms": tr.get("audioDurationMs"), "mission": parse(client, text)}


@app.post("/api/mission/text")
async def mission_text(request: Request):
    from .audit import make_client
    from .mission import parse
    if LIVE_ON:
        live_gate(request, audit=False)
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
def evaluation(run: str, key: str = "cases"):
    if not key.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(400, "bad key name")
    out = _evaluate_module().score(run, key)
    about = json.loads((DATA / "answer_key" / f"{key}.json").read_text(encoding="utf-8"))
    out["about"] = about.get("_about")
    key_rows = {k["id"]: k for k in about["cases"]}
    for r in out["rows"]:
        k = key_rows[r["id"]]
        r["quote"], r["date"], r["sources"] = k["quote"], k["date"], k["sources"]
        rec = portfolio().get(r["id"]) or {}
        r["desc"], r["cost"], r["muni"] = rec.get("desc"), rec.get("cost"), rec.get("muni")
        cf = _run_dir(run) / "cases" / r["id"] / "case.json"
        r["tier"] = ((json.loads(cf.read_text(encoding="utf-8")).get("triage") or {}).get("tier")) if cf.exists() else None
    # what Atlas said, against what the ruling said: how often each kind of answer held
    by: dict[str, dict] = {}
    for r in out["rows"]:
        b = by.setdefault(r["atlas"] or "error", {"n": 0, "same": 0, "compatible": 0, "disagree": 0, "ids": []})
        b["n"] += 1
        b["same"] += r["agree"]
        b["compatible"] += r["partial"]
        b["disagree"] += r["contradict"]
        b["ids"].append(r["id"])
    out["by_atlas"] = by
    sc = DATA / "runs" / f"{run}-sitecheck" / "summary.json"
    out["sitecheck"] = json.loads(sc.read_text(encoding="utf-8")) if sc.exists() else None
    tr = _run_dir(run) / "triage.json"
    out["triage"] = {k: v for k, v in json.loads(tr.read_text(encoding="utf-8")).items() if k != "tier_text"} if tr.exists() else None
    return out


@app.get("/api/runs/{run}/triage")
def triage(run: str):
    p = _run_dir(run) / "triage.json"
    if not p.exists():
        raise HTTPException(404)
    return json.loads(p.read_text(encoding="utf-8"))


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


# ---------- live audit routes ----------


def _live_runs() -> list[dict]:
    out = []
    for d in sorted((DATA / "runs").glob("live-*"), reverse=True):
        cs = list((d / "cases").glob("*/case.json"))
        c = json.loads(cs[0].read_text(encoding="utf-8")) if cs else None
        out.append({"run": d.name, "id": d.name.split("-", 3)[-1], "outcome": ((c or {}).get("verdict") or {}).get("outcome"),
                    "seconds": (c or {}).get("seconds"), "done": c is not None})
    return out


def live_gate(request: Request, audit: bool = True) -> None:
    """Who may spend on a hosted server: anyone once the owner opens it (ATLAS_LIVE_OPEN=1), otherwise only a request
    carrying the owner's token. Audits also need the budget, the daily cap and no other audit running."""
    if os.environ.get("ATLAS_LIVE_OPEN") != "1":
        tok = os.environ.get("ATLAS_LIVE_TOKEN")
        if not tok or request.headers.get("X-Live-Token") != tok:
            raise HTTPException(403, "live audits are not open to the public on this server yet")
    if not audit:
        return
    t = _live["thread"]
    if t is not None and t.is_alive():
        raise HTTPException(409, json.dumps({"run": _live["run"], "id": _live["id"]}))
    st = live_status()
    if st["today"] >= LIVE_PER_DAY:
        raise HTTPException(429, f"{LIVE_PER_DAY} live audits a day; come back tomorrow (UTC)")
    if st["spent_usd"] >= LIVE_BUDGET - 0.5:
        raise HTTPException(402, f"the live budget (${LIVE_BUDGET:.0f}) is spent")


@app.get("/api/live/status")
def live_status():
    from .meta import Meter
    m = Meter(DATA / "meter_live.json", LIVE_BUDGET)
    t = _live["thread"]
    today = time.strftime("%Y%m%d", time.gmtime())
    runs = _live_runs()
    return {"enabled": LIVE_ON, "open": os.environ.get("ATLAS_LIVE_OPEN") == "1", "running": {"run": _live["run"], "id": _live["id"], "started": _live["started"]}
            if t is not None and t.is_alive() else None,
            "spent_usd": round(m.spent_usd, 3), "budget_usd": LIVE_BUDGET, "today": sum(1 for r in runs if r["run"][5:13] == today),
            "per_day": LIVE_PER_DAY, "recent": runs[:12]}


@app.post("/api/live/audit")
async def live_audit(request: Request):
    """Audit one Bulacan contract now, at full depth, with an empty model cache: every answer is a fresh call."""
    import random
    from .audit import audit, declarations, make_client
    if not LIVE_ON:
        raise HTTPException(403, "live audits are off on this server")
    live_gate(request)
    body = await request.json() if request.headers.get("content-length") not in (None, "0") else {}
    recs = portfolio()
    pool = [r for r in recs.values() if (r.get("province") or "").lower() == "bulacan" and r.get("completion")]
    cid = (body.get("id") or "").strip().upper()
    if cid and (cid not in recs or recs[cid] not in pool):
        raise HTTPException(404, "not a Bulacan contract with a completion date")
    rec = recs[cid] if cid else random.choice(pool)
    run = f"live-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{rec['id']}"
    lg, rdir = open_run(run)
    client = make_client(cap_usd=LIVE_BUDGET, cache_dir=rdir / "cache", meter_path=DATA / "meter_live.json")
    if client is None:
        raise HTTPException(503, "no model access")
    log = open(rdir / "events.jsonl", "a", encoding="utf-8")

    def emit(ev) -> None:
        log.write(json.dumps(ev.as_dict(), ensure_ascii=False, default=str) + "\n")
        log.flush()

    def go() -> None:
        try:
            audit(rec, lg, client, emit, rdir, declaration=declarations().get(rec["id"]), depth="full", lm="meta")
        finally:
            log.close()
            for h in ON_AUDIT_DONE:
                h()

    th = threading.Thread(target=go, daemon=True)
    _live.update(thread=th, run=run, id=rec["id"], started=time.time())
    th.start()
    return {"run": run, "id": rec["id"], "desc": rec.get("desc"), "cost": rec.get("cost"), "random": not cid}


_ = ROOT
