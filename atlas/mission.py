"""A mission spoken or typed by the investigator: Muse Voice Transcribe, then Muse Spark parses it."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import date

from .case import DATA
from .meta import SPARK, MetaClient

VOICE = "muse-voice-transcribe-1.0"
VOICE_PER_HOUR = 0.18

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "province": {"type": ["string", "null"], "description": "Philippine province to audit"},
        "scope": {"type": "string", "description": "what to audit, e.g. 'flood-control contracts 2022-2025'"},
        "deadline": {"type": ["string", "null"], "description": "ISO date the results are needed by"},
        "deadline_label": {"type": ["string", "null"], "description": "what the deadline is, e.g. 'Senate hearing'"},
        "budget_usd": {"type": ["number", "null"]},
        "focus": {"type": "array", "items": {"type": "string"}, "description": "anything to prioritise"},
    },
    "required": ["province", "scope", "deadline", "deadline_label", "budget_usd", "focus"],
}


def transcribe(client: MetaClient, wav: bytes) -> dict:
    key = hashlib.sha256(wav).hexdigest()
    cache = DATA / "cache/voice" / f"{key}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    req = {"model": VOICE, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK", "languageBias": ["English", "Tagalog"],
           "keywords": ["Audit", "Bulacan", "flood-control", "Senate", "Blue Ribbon", "DPWH", "barangay", "Wawao", "SYMS", "Topnotch",
                        "Malolos", "Baliwag", "Hagonoy", "Calumpit", "Plaridel", "Angat River"]}
    client.meter.check(0.01)
    r = client._http.post("/asr/transcribe", headers={"Authorization": f"Bearer {client.api_key}", "Accept": "application/json"},
                          files={"request": (None, json.dumps(req), "application/json"), "audio": ("mission.wav", wav, "audio/wav")})
    if r.status_code >= 400:
        raise RuntimeError(f"transcribe HTTP {r.status_code}: {r.text[:300]}")
    out = r.json()
    secs = (out.get("audioDurationMs") or 0) // 1000
    client.meter.add(secs / 3600 * VOICE_PER_HOUR, VOICE)
    out["_at"] = time.time()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def parse(client: MetaClient, text: str) -> dict:
    instr = (f"Today is {date.today().isoformat()}. An investigator states an audit mission. Extract it. "
             "Resolve relative dates ('Friday', 'next week') to ISO dates. Do not invent a budget or a deadline.")
    res = client.structured(SPARK, instr, [{"type": "input_text", "text": text}], SCHEMA, schema_name="mission", effort="low")
    return res["data"]
