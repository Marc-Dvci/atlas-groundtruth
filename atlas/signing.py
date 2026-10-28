"""Investigator signatures and challenges.

A decision on a case (concur, refer for a site visit, dissent, challenge) is a statement the investigator signs with
an Ed25519 key. The private key never leaves the investigator's browser; the audit office enrols the public key in a
registry (data/investigators.json) once, out of band. The server seals a decision only when its signature verifies
against an enrolled key and the statement names the verdict it is about, so a decision can be neither forged nor moved
to another case or another verdict, and anyone holding the registry can check every signature again.

The signed statement is a flat object of strings, serialised as canonical JSON (keys sorted, no spaces, UTF-8), the
same bytes in Python and in the browser.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from .ledger import canonical

DECISIONS = ("concur", "refer_for_site_visit", "dissent", "challenge")
CHALLENGES = {
    "WRONG_SITE": "The works are at another reach than the one the verdict was read on.",
    "EXISTING_STRUCTURE_WORKED_ON": "The contract repaired, raised or extended a structure that was already there.",
    "WRONG_READING": "A capture reading is wrong: the imagery shows something else.",
    "OTHER": "Another reason, in the note.",
}
STATEMENT_KEYS = ("run", "case", "decision", "challenge", "note", "verdict", "verdict_reason", "verdict_entry",
                  "ledger_head", "key_id", "signed_at", "site")


def key_id(public_key_b64: str) -> str:
    return hashlib.sha256(base64.b64decode(public_key_b64)).hexdigest()[:16]


def message(statement: dict) -> bytes:
    return canonical({k: statement.get(k, "") for k in STATEMENT_KEYS})


def verify_signature(statement: dict, public_key_b64: str, signature_b64: str) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64)).verify(
            base64.b64decode(signature_b64), message(statement))
        return True
    except (InvalidSignature, ValueError):
        return False


def registry(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {r["key_id"]: r for r in json.loads(path.read_text(encoding="utf-8"))["investigators"]}


def check_entry(payload: dict, enrolled: dict[str, dict]) -> tuple[bool, str]:
    """A sealed decision: does its signature verify, and was its key enrolled?"""
    st, pk, sig = payload.get("statement"), payload.get("public_key"), payload.get("signature")
    if not (st and pk and sig):
        return False, "unsigned"
    if key_id(pk) != st.get("key_id"):
        return False, "the statement names another key"
    if not verify_signature(st, pk, sig):
        return False, "signature does not verify"
    if st["key_id"] not in enrolled:
        return False, "signature verifies, but the key is not enrolled"
    return True, f"signed by {enrolled[st['key_id']]['name']}"
