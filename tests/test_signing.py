"""Signed decisions: a decision verifies only with its own key, its own words and an enrolled key."""
import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from atlas.signing import check_entry, key_id, message
from scripts.anchor import query


def keypair():
    sk = Ed25519PrivateKey.generate()
    pk = base64.b64encode(sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    return sk, pk


def signed(sk, pk, **over):
    st = {"run": "bulacan", "case": "24CC0055", "decision": "concur", "challenge": "", "note": "",
          "verdict": "exists_before_contract", "verdict_reason": "PRESENT_BEFORE_AWARD", "verdict_entry": "ab" * 32,
          "ledger_head": "cd" * 32, "key_id": key_id(pk), "signed_at": "2026-10-28T19:00:00Z", "site": ""} | over
    return {"statement": st, "public_key": pk, "signature": base64.b64encode(sk.sign(message(st))).decode()}


def test_an_enrolled_signature_verifies():
    sk, pk = keypair()
    ok, why = check_entry(signed(sk, pk), {key_id(pk): {"name": "Investigator A"}})
    assert ok and "Investigator A" in why


def test_changing_the_decision_after_signing_fails():
    sk, pk = keypair()
    e = signed(sk, pk)
    e["statement"]["decision"] = "dissent"
    assert check_entry(e, {key_id(pk): {"name": "A"}}) == (False, "signature does not verify")


def test_moving_a_signature_to_another_verdict_fails():
    sk, pk = keypair()
    e = signed(sk, pk)
    e["statement"]["verdict_entry"] = "ef" * 32
    assert not check_entry(e, {key_id(pk): {"name": "A"}})[0]


def test_another_key_cannot_sign_in_an_enrolled_name():
    sk, pk = keypair()
    sk2, pk2 = keypair()
    e = signed(sk2, pk2, key_id=key_id(pk))
    assert check_entry(e, {key_id(pk): {"name": "A"}}) == (False, "the statement names another key")


def test_a_valid_signature_from_an_unenrolled_key_is_not_accepted():
    sk, pk = keypair()
    ok, why = check_entry(signed(sk, pk), {})
    assert not ok and "not enrolled" in why


def test_the_timestamp_request_carries_the_ledger_head():
    head = "ab" * 32
    q = query(head)
    assert q[0] == 0x30 and q[1] == len(q) - 2
    assert bytes.fromhex(head) in q
    assert bytes.fromhex("608648016503040201") in q  # SHA-256
