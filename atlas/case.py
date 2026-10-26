"""One project under audit: shared context for the agents that work on it."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .ledger import Ledger
from .meta import MetaClient
from .verdict import Finding

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


@dataclass
class Event:
    t: float
    kind: str
    case: str
    agent: str
    data: dict

    def as_dict(self) -> dict:
        return {"t": round(self.t, 3), "kind": self.kind, "case": self.case, "agent": self.agent, "data": self.data}


@dataclass
class Case:
    record: dict
    ledger: Ledger
    meta: MetaClient | None
    emit: Callable[[Event], None]
    workdir: Path
    findings: list[Finding] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)  # agent outputs other agents may read
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def id(self) -> str:
        return self.record["id"]

    def say(self, agent: str, kind: str, **data) -> None:
        self.emit(Event(time.time(), kind, self.id, agent, data))

    def record_entry(self, agent: str, kind: str, payload: dict) -> str:
        e = self.ledger.append(self.id, agent, kind, payload)
        self.say(agent, "ledger", seq=e.seq, hash=e.hash, entry_kind=kind)
        return e.hash

    def blob(self, data: bytes, ext: str) -> str:
        return self.ledger.put_blob(data, ext)

    def file(self, f: Finding) -> Finding:
        h = self.record_entry(f.agent, "finding", {"finding": f.__dict__})
        f = Finding(**{**f.__dict__, "entry": h})
        with self._lock:
            self.findings.append(f)
        self.say(f.agent, "finding", finding=f.__dict__)
        return f

    def save_json(self, name: str, obj: Any) -> None:
        self.workdir.mkdir(parents=True, exist_ok=True)
        (self.workdir / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
