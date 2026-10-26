"""Append-only, hash-chained evidence ledger.

Every agent finding, tool call, refusal and signature is one entry. Each entry
carries the hash of the previous one, so editing any past entry breaks every
hash after it. Binary evidence (image chips, masks) is stored by content hash
and referenced from the entry, so the chain also seals the pixels.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

GENESIS = "0" * 64


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Entry:
    seq: int
    ts: float
    case: str
    actor: str
    kind: str
    payload: dict
    prev: str
    hash: str

    def as_dict(self) -> dict:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "case": self.case,
            "actor": self.actor,
            "kind": self.kind,
            "payload": self.payload,
            "prev": self.prev,
            "hash": self.hash,
        }


def entry_hash(seq: int, ts: float, case: str, actor: str, kind: str, payload: dict, prev: str) -> str:
    body = {"seq": seq, "ts": ts, "case": case, "actor": actor, "kind": kind, "payload": payload, "prev": prev}
    return sha256(canonical(body))


class Ledger:
    """One JSONL file per run. Thread-safe appends."""

    def __init__(self, path: Path, blob_dir: Path):
        self.path = Path(path)
        self.blob_dir = Path(blob_dir)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = 0
        self._head = GENESIS
        if self.path.exists():
            for e in self.entries():
                self._seq, self._head = e.seq + 1, e.hash

    @property
    def head(self) -> str:
        return self._head

    def put_blob(self, data: bytes, ext: str) -> str:
        """Store binary evidence by content hash; returns '<sha256>.<ext>'."""
        name = f"{sha256(data)}.{ext}"
        target = self.blob_dir / name
        if not target.exists():
            target.write_bytes(data)
        return name

    def append(self, case: str, actor: str, kind: str, payload: dict) -> Entry:
        with self._lock:
            seq, prev, ts = self._seq, self._head, round(time.time(), 3)
            h = entry_hash(seq, ts, case, actor, kind, payload, prev)
            e = Entry(seq, ts, case, actor, kind, payload, prev, h)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(e.as_dict(), ensure_ascii=False) + "\n")
            self._seq, self._head = seq + 1, h
            return e

    def entries(self) -> Iterator[Entry]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    yield Entry(**d)

    def verify(self) -> tuple[bool, int | None, str]:
        """Recompute the chain and every referenced blob hash.

        Returns (ok, first_bad_seq, reason).
        """
        prev = GENESIS
        for e in self.entries():
            if e.prev != prev:
                return False, e.seq, "broken link to previous entry"
            if entry_hash(e.seq, e.ts, e.case, e.actor, e.kind, e.payload, e.prev) != e.hash:
                return False, e.seq, "entry content changed after it was written"
            for ref in _blob_refs(e.payload):
                p = self.blob_dir / ref
                if not p.exists():
                    return False, e.seq, f"evidence file missing: {ref}"
                if sha256(p.read_bytes()) != ref.split(".")[0]:
                    return False, e.seq, f"evidence file altered: {ref}"
            prev = e.hash
        return True, None, "chain intact"


def _blob_refs(payload: Any) -> Iterator[str]:
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k in ("blob", "blobs") or k.endswith("_blob"):
                if isinstance(v, str):
                    yield v
                elif isinstance(v, list):
                    yield from (x for x in v if isinstance(x, str))
            else:
                yield from _blob_refs(v)
    elif isinstance(payload, list):
        for v in payload:
            yield from _blob_refs(v)
