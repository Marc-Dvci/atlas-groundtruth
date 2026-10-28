"""Meta Model API client: Muse Spark, Muse Wonder, SAM 3.1, Muse Image.

Three properties matter more than convenience here:

* Every request is cached on disk by the hash of its body, so a recorded run
  replays byte-for-byte without spending credit, and the demo never depends on
  the network.
* Every call is metered against a hard budget (the hackathon credit). A call
  that would exceed it is refused before it is sent.
* Tools run behind a default-deny gateway: the model can only call functions
  the agent registered, with arguments that validate.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx

BASE_URL = os.environ.get("META_BASE_URL", "https://api.meta.ai/v1")
# Muse Spark Open (open weights), served by Baseten and by Fireworks for the hackathon. The agents call it through
# the same interface as Muse Spark; only the host changes. An institution can serve the same weights itself.
OPEN = "meta-models/muse-spark-open-1026"
# host -> (base URL, key variable, the host's id for the same weights)
OPEN_HOSTS = {
    "baseten": (os.environ.get("OPEN_BASE_URL", "https://inference.baseten.co/v1"), "BASETEN_API_KEY", OPEN),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", "accounts/fireworks/models/muse-spark-open"),
}

# USD per 1M tokens (input, cached input, output); dev.meta.ai/docs/pricing-rate-limits.
PRICES = {
    "muse-wonder-1.0": (4.00, 0.20, 20.00),
    "muse-spark-1.3": (1.25, 0.15, 4.25),
    "muse-spark-1.2": (1.25, 0.15, 4.25),
    "muse-spark-1.3-contributor": (0.10, 0.002, 0.20),
    OPEN: (1.25, 0.15, 4.25),  # the rate hosts publish for Muse Spark Open; billed to the Baseten credit
}
SAM_PER_IMAGE = 2.50 / 1000
SAM_PER_FRAME = 0.20 / 1000
IMAGE_PER_GEN = 0.01

SPARK = os.environ.get("ATLAS_SPARK_MODEL", "muse-spark-1.3")
# Bulk screening sends only public records and public imagery, so it may use the contributor tier
# (Meta may train on it; it must never carry personal or confidential data). Case files stay on SPARK.
BULK = os.environ.get("ATLAS_BULK_MODEL", "muse-spark-1.3-contributor")
WONDER = os.environ.get("ATLAS_WONDER_MODEL", "muse-wonder-1.0")
SAM = os.environ.get("ATLAS_SAM_MODEL", "sam-3.1")
IMAGE = os.environ.get("ATLAS_IMAGE_MODEL", "muse-image-1.0")


def label(model: str) -> str:
    """The name a reader sees for a model id."""
    return {OPEN: "Muse Spark Open", "muse-wonder-1.0": "Muse Wonder", "muse-spark-1.3": "Muse Spark 1.3",
            "muse-spark-1.3-contributor": "Muse Spark 1.3", "muse-image-1.0": "Muse Image", "sam-3.1": "SAM 3.1"}.get(model, model)


def load_env(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE lines); never overrides the real environment."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class BudgetExceeded(RuntimeError):
    pass


class OfflineMiss(RuntimeError):
    """Replay mode and the request is not in the cache."""


class ToolRefused(RuntimeError):
    pass


@dataclass
class Meter:
    path: Path
    cap_usd: float
    spent_usd: float = 0.0
    calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if self.path.exists():
            d = json.loads(self.path.read_text())
            self.spent_usd, self.calls = d.get("spent_usd", 0.0), d.get("calls", 0)

    def check(self, est: float) -> None:
        if self.spent_usd + est > self.cap_usd:
            raise BudgetExceeded(
                f"refused: ${self.spent_usd:.2f} spent of a ${self.cap_usd:.2f} cap; this call needs about ${est:.3f}"
            )

    def add(self, usd: float, model: str) -> None:
        with self._lock:
            if self.path.exists():  # another process (a fleet beside an evaluation) may have spent since we last looked
                try:
                    d = json.loads(self.path.read_text())
                    self.spent_usd, self.calls = max(self.spent_usd, d.get("spent_usd", 0.0)), max(self.calls, d.get("calls", 0))
                except (json.JSONDecodeError, OSError):
                    pass
            self.spent_usd += usd
            self.calls += 1
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"spent_usd": round(self.spent_usd, 5), "calls": self.calls,
                                             "last_model": model, "updated": time.time()}))


def data_url(data: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def _key(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _json_of(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        return json.loads(text[s:e + 1]) if 0 <= s < e else None


def _parses(text: str) -> bool:
    try:
        return isinstance(_json_of(text.strip()), dict)
    except json.JSONDecodeError:
        return False


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., Any]

    def spec(self) -> dict:
        return {"type": "function", "name": self.name, "description": self.description,
                "parameters": self.parameters}


@dataclass
class Turn:
    """One tool call made by a model, as the UI and the ledger show it."""
    name: str
    arguments: dict
    result: Any
    refused: str | None = None


class MetaClient:
    def __init__(self, cache_dir: Path, meter: Meter, *, offline: bool = False, api_key: str | None = None,
                 open_meter: Meter | None = None, open_host: str = "baseten"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.meter = meter
        # Muse Spark Open calls are billed to a separate credit (Baseten), so they get their own meter.
        self.open_meter = open_meter or meter
        self.offline = offline
        self.api_key = api_key or os.environ.get("MODEL_API_KEY", "")
        self.open_host = open_host
        open_url, key_var, self.open_model_id = OPEN_HOSTS[open_host]
        self.open_key_var = key_var
        self.open_key = os.environ.get(key_var, "")
        self._http = httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(180.0, connect=20.0))
        self._open_http = httpx.Client(base_url=open_url, timeout=httpx.Timeout(300.0, connect=20.0))

    # ---------- transport ----------
    def _post(self, path: str, body: dict, est_usd: float, *, files: dict | None = None) -> dict:
        key = _key({"path": path, **body})
        hit = self.cache_dir / f"{key}.json"
        if hit.exists():
            return json.loads(hit.read_text(encoding="utf-8"))
        if self.offline:
            raise OfflineMiss(f"{path} not in cache ({key[:12]})")
        if not self.api_key:
            raise RuntimeError("MODEL_API_KEY is not set (put it in atlas/.env)")
        self.meter.check(est_usd)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for attempt in range(5):
            try:
                if files:
                    r = self._http.post(path, data=body, files=files, headers=headers)
                else:
                    r = self._http.post(path, json=body, headers=headers)
            except httpx.TransportError:  # a dropped connection is retried like a 503
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt + 0.5)
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(2 ** attempt + 0.5)
                continue
            break
        if r.status_code >= 400:
            raise RuntimeError(f"Meta API {path} -> HTTP {r.status_code}: {r.text[:800]}")
        out = r.json()
        out["_atlas"] = {"cached_at": time.time(), "path": path}
        hit.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        out["_fresh"] = True  # billed once, by the caller; cache hits are free
        return out

    def _bill_tokens(self, model: str, resp: dict) -> float:
        if not resp.get("_fresh"):
            return 0.0
        u = resp.get("usage") or {}
        pin, pcached, pout = PRICES.get(model, PRICES[SPARK])
        cached = (u.get("input_tokens_details") or {}).get("cached_tokens", 0) or 0
        inp = (u.get("input_tokens") or 0) - cached
        out = u.get("output_tokens") or 0
        usd = (inp * pin + cached * pcached + out * pout) / 1e6
        (self.open_meter if model == OPEN else self.meter).add(usd, model)
        return usd

    # ---------- Muse Spark Open (OpenAI-compatible chat completions) ----------
    @staticmethod
    def _to_chat(instructions: str, items: list[dict]) -> list[dict]:
        """Responses-style input items -> chat messages (text, images, tool calls and their outputs)."""
        msgs: list[dict] = [{"role": "system", "content": instructions}] if instructions else []
        for it in items:
            if it.get("type") == "function_call":
                call = {"id": it["call_id"], "type": "function",
                        "function": {"name": it["name"], "arguments": it.get("arguments") or "{}"}}
                if msgs and msgs[-1]["role"] == "assistant" and msgs[-1].get("tool_calls"):
                    msgs[-1]["tool_calls"].append(call)
                else:
                    msgs.append({"role": "assistant", "content": None, "tool_calls": [call]})
            elif it.get("type") == "function_call_output":
                msgs.append({"role": "tool", "tool_call_id": it["call_id"], "content": it["output"]})
            elif it.get("role") == "assistant":
                msgs.append({"role": "assistant", "content": it["content"] if isinstance(it["content"], str) else
                             "".join(c.get("text", "") for c in it["content"])})
            else:
                parts = []
                for c in it.get("content", []):
                    if c.get("type") == "input_text":
                        parts.append({"type": "text", "text": c["text"]})
                    elif c.get("type") == "input_image":
                        parts.append({"type": "image_url", "image_url": {"url": c["image_url"]}})
                msgs.append({"role": it.get("role", "user"), "content": parts})
        return msgs

    def _respond_open(self, model: str, instructions: str, items: list[dict], *, schema: dict | None,
                      schema_name: str, tools: list["Tool"] | None, effort: str | None, est_usd: float) -> dict:
        body: dict[str, Any] = {"model": self.open_model_id, "messages": self._to_chat(instructions, items), "max_tokens": 16000,
                                # without an effort the open model's guided JSON can stall in whitespace
                                "reasoning_effort": effort or "low"}
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                               "parameters": t.parameters}} for t in tools]
        elif schema:  # guided JSON and tool calls don't mix on this host: the tool loop asks for the JSON last
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema,
                                                                              "strict": True}}
        path = f"{self.open_host}:/chat/completions"
        key = _key({"path": path, **body})
        hit = self.cache_dir / f"{key}.json"
        if hit.exists():
            return json.loads(hit.read_text(encoding="utf-8"))
        if self.offline:
            raise OfflineMiss(f"open model not in cache ({key[:12]})")
        if not self.open_key:
            raise RuntimeError(f"{self.open_key_var} is not set (put it in atlas/.env)")
        self.open_meter.check(est_usd)
        last = ""
        for attempt in range(4):
            try:
                r = self._open_http.post("/chat/completions", json=body, headers={"Authorization": f"Bearer {self.open_key}"})
            except httpx.TransportError as e:
                last = f"{type(e).__name__}"
                time.sleep(2 ** attempt + 0.5)
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}: {r.text[:300]}"
                time.sleep(2 ** attempt + 0.5)
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"Muse Spark Open ({self.open_host}) -> HTTP {r.status_code}: {r.text[:800]}")
            d = r.json()
            ch = (d.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            u = d.get("usage") or {}
            out: dict[str, Any] = {"output": [], "model": model, "usage": {
                "input_tokens": u.get("prompt_tokens") or 0, "output_tokens": u.get("completion_tokens") or 0,
                "input_tokens_details": {"cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0}},
                "reasoning": msg.get("reasoning_content"), "finish_reason": ch.get("finish_reason")}
            for tc in msg.get("tool_calls") or []:
                out["output"].append({"type": "function_call", "call_id": tc["id"], "name": tc["function"]["name"],
                                      "arguments": tc["function"].get("arguments") or "{}"})
            text = msg.get("content") or ""
            if text:
                out["output"].append({"type": "message", "content": [{"type": "output_text", "text": text}]})
            out["_fresh"] = True
            usd = self._bill_tokens(model, out)
            # an answer that should be JSON but isn't is billed, never cached, and asked again
            if schema and not tools and not _parses(text):
                last = f"unparseable JSON ({ch.get('finish_reason')})"
                continue
            if not out["output"]:
                last = f"empty answer ({ch.get('finish_reason')})"
                continue
            out["_atlas"] = {"cached_at": time.time(), "path": path}
            hit.write_text(json.dumps({k: v for k, v in out.items() if k != "_fresh"}, ensure_ascii=False), encoding="utf-8")
            out["_usd_billed"] = usd
            return out
        raise RuntimeError(f"Muse Spark Open ({self.open_host}) gave no usable answer after 4 tries: {last}")

    # ---------- Responses API ----------
    def respond(
        self,
        model: str,
        instructions: str,
        content: list[dict],
        *,
        schema: dict | None = None,
        schema_name: str = "result",
        tools: list[Tool] | None = None,
        history: list[dict] | None = None,
        effort: str | None = None,
        est_usd: float = 0.05,
    ) -> dict:
        if model == OPEN:
            items = (history or []) + ([{"role": "user", "content": content}] if content else [])
            resp = self._respond_open(model, instructions, items, schema=schema, schema_name=schema_name, tools=tools,
                                      effort=effort, est_usd=est_usd)
            resp["_usd"] = resp.pop("_usd_billed", 0.0)
            return resp
        body: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": (history or []) + ([{"role": "user", "content": content}] if content else []),
            "store": False,
        }
        if schema:
            body["text"] = {"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}}
        if tools:
            body["tools"] = [t.spec() for t in tools]
        if effort:
            body["reasoning"] = {"effort": effort}
        resp = self._post("/responses", body, est_usd)
        resp["_usd"] = self._bill_tokens(model, resp)
        return resp

    @staticmethod
    def output_text(resp: dict) -> str:
        if isinstance(resp.get("output_text"), str):
            return resp["output_text"]
        parts = []
        for item in resp.get("output", []):
            if item.get("type") == "message":
                for c in item.get("content", []):
                    if c.get("type") in ("output_text", "text"):
                        parts.append(c.get("text", ""))
        return "".join(parts)

    def structured(self, model: str, instructions: str, content: list[dict], schema: dict, **kw) -> dict:
        resp = self.respond(model, instructions, content, schema=schema, **kw)
        return {"data": _json_of(self.output_text(resp).strip()), "response": resp}

    def tool_loop(
        self,
        model: str,
        instructions: str,
        content: list[dict],
        tools: list[Tool],
        *,
        schema: dict | None = None,
        max_turns: int = 8,
        on_turn: Callable[[Turn], None] | None = None,
        effort: str | None = None,
    ) -> dict:
        """Run a function-calling loop. Unknown tools and invalid arguments are refused, not executed."""
        allowed = {t.name: t for t in tools}
        history: list[dict] = [{"role": "user", "content": content}]
        turns: list[Turn] = []
        resp: dict = {}
        for _ in range(max_turns):
            resp = self.respond(model, instructions, [], schema=schema, tools=tools, history=history, effort=effort)
            calls = [i for i in resp.get("output", []) if i.get("type") == "function_call"]
            if not calls:
                break
            # Stateless replay (store=false): resend the calls themselves; reasoning items
            # would need encrypted content, so they are not replayed.
            for item in resp.get("output", []):
                if item.get("type") == "function_call":
                    history.append({k: item[k] for k in ("type", "call_id", "name", "arguments") if k in item})
            for c in calls:
                name = c.get("name", "")
                try:
                    args = json.loads(c.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                t = allowed.get(name)
                if t is None:
                    turn = Turn(name, args, None, refused="tool not in this agent's release")
                    result: Any = {"error": turn.refused}
                else:
                    missing = [k for k in t.parameters.get("required", []) if k not in args]
                    if missing:
                        turn = Turn(name, args, None, refused=f"missing arguments: {missing}")
                        result = {"error": turn.refused}
                    else:
                        try:
                            result = t.fn(**args)
                            turn = Turn(name, args, result)
                        except Exception as e:  # tool errors go back to the model as data
                            result = {"error": f"{type(e).__name__}: {e}"}
                            turn = Turn(name, args, result)
                turns.append(turn)
                if on_turn:
                    on_turn(turn)
                history.append({"type": "function_call_output", "call_id": c.get("call_id"),
                                "output": json.dumps(result, ensure_ascii=False, default=str)[:20000]})
        text = self.output_text(resp)
        data = None
        if schema and text.strip():
            try:
                data = _json_of(text)
            except json.JSONDecodeError:
                data = None
        if schema and not isinstance(data, dict):
            # The model finished in prose (or not at all): ask once more for the answer as the JSON object,
            # with the whole tool history in view and no tools offered.
            tail = ([{"role": "assistant", "content": text}] if text.strip() else []) + [
                {"role": "user", "content": [{"type": "input_text", "text": "Give your final answer now, as the JSON object only."}]}]
            resp = self.respond(model, instructions, [], schema=schema, history=history + tail, effort=effort)
            text = self.output_text(resp)
            try:
                data = _json_of(text)
            except json.JSONDecodeError:
                data = None
        return {"text": text, "data": data, "turns": turns, "response": resp}


# ---------- SAM 3.1 ----------
import re as _re  # noqa: E402

_FRAME = _re.compile(r"<(\d+)f>")
_RECORD = _re.compile(
    r"(?P<obj>\d+)"
    r"<\|box;x1=(?P<x1>\d+);y1=(?P<y1>\d+);x2=(?P<x2>\d+);y2=(?P<y2>\d+);w=(?P<w>\d+);h=(?P<h>\d+)(?:;c=(?P<bc>[0-9.]+))?\|>"
    r"<\|mask;x=0;y=0(?:;c=(?P<mc>[0-9.]+))?;data=(?P<mh>\d+),(?P<mw>\d+),(?P<enc>[~!])(?P<payload>.*?)\|>"
)


@dataclass
class SamObject:
    frame: int
    object_id: int
    box: tuple[int, int, int, int]  # x1, y1, x2, y2 inclusive, source pixels
    size: tuple[int, int]  # media w, h
    confidence: float | None
    mask_hw: tuple[int, int]
    encoding: str
    payload: str

    def mask(self):
        """Box-local boolean mask, or None if the payload can't be decoded."""
        return decode_mask(self.payload, self.encoding, *self.mask_hw)


def parse_sam(text: str) -> list[SamObject]:
    out: list[SamObject] = []
    for line in text.splitlines():
        line = line.strip()
        fm = _FRAME.match(line)
        if not fm:
            continue
        for m in _RECORD.finditer(line):
            out.append(SamObject(
                int(fm.group(1)), int(m["obj"]),
                (int(m["x1"]), int(m["y1"]), int(m["x2"]), int(m["y2"])), (int(m["w"]), int(m["h"])),
                float(m["bc"]) if m["bc"] else None, (int(m["mh"]), int(m["mw"])),
                "lossless" if m["enc"] == "~" else "one_bit", m["payload"]))
    return out


def decode_mask(payload: str, encoding: str, h: int, w: int):
    """Box-local boolean mask. Atlas always requests one_bit masks (see sam_codec)."""
    if encoding != "one_bit":
        return None
    from .sam_codec import decode_one_bit
    try:
        return decode_one_bit(payload, h, w)
    except Exception:
        return None


def _sam_body(prompt: str, part: dict) -> dict:
    return {
        "model": SAM,
        "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt}, part]}],
        "metadata": {"mask_encoding": "one_bit", "include_confidence": "true"},
        "store": False,
    }


def _sam_text(resp: dict) -> str:
    return MetaClient.output_text(resp)


def segment_image(client: "MetaClient", image: bytes, prompt: str, mime: str = "image/jpeg") -> list[SamObject]:
    body = _sam_body(prompt, {"type": "input_image", "image_url": data_url(image, mime)})
    resp = client._post("/responses", body, SAM_PER_IMAGE)
    if resp.get("_fresh"):
        client.meter.add(SAM_PER_IMAGE, SAM)
    return parse_sam(_sam_text(resp))


def segment_video(client: "MetaClient", mp4: bytes, prompt: str, frames: int) -> list[SamObject]:
    body = _sam_body(prompt, {"type": "input_video", "video_url": data_url(mp4, "video/mp4")})
    usd = max(50, frames) * SAM_PER_FRAME
    resp = client._post("/responses", body, usd)
    if resp.get("_fresh"):
        client.meter.add(usd, SAM)
    return parse_sam(_sam_text(resp))


# ---------- Muse Image ----------
def image_edit(client: "MetaClient", image: bytes, prompt: str, mime: str = "image/png") -> bytes:
    body = {"model": IMAGE, "prompt": prompt, "images": [{"image_url": data_url(image, mime)}], "n": 1,
            "output_format": "png", "response_format": "b64_json"}
    resp = client._post("/images/edits", body, IMAGE_PER_GEN)
    if resp.get("_fresh"):
        client.meter.add(IMAGE_PER_GEN, IMAGE)
    return base64.b64decode(resp["data"][0]["b64_json"])


def image_generate(client: "MetaClient", prompt: str, size: str = "1536x1024") -> bytes:
    body = {"model": IMAGE, "prompt": prompt, "n": 1, "size": size, "output_format": "png", "response_format": "b64_json"}
    resp = client._post("/images/generations", body, IMAGE_PER_GEN)
    if resp.get("_fresh"):
        client.meter.add(IMAGE_PER_GEN, IMAGE)
    return base64.b64decode(resp["data"][0]["b64_json"])
