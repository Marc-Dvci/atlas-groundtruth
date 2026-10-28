"""Sign a decision or a challenge on a sealed case from the command line, as the web app does with the browser's key.

    .venv/Scripts/python scripts/challenge.py --enrol "Name"            # create a key in data/keys/ and enrol it
    .venv/Scripts/python scripts/challenge.py --run bulacan --case 22CC0013 --challenge WRONG_SITE \\
        --site 120.9012,14.8034 --note "The plans put the works on the north reach"

A WRONG_SITE challenge that names a reach audits the case again there (full depth). The earlier case file is kept as
case.r<n>.json and every earlier ledger entry stays: a correction adds to the record.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from atlas import server  # noqa: E402
from atlas.audit import open_run  # noqa: E402
from atlas.case import DATA  # noqa: E402
from atlas.signing import check_entry, key_id, message, registry  # noqa: E402

KEY = DATA / "keys" / "investigator.pem"


def load_key() -> tuple[Ed25519PrivateKey, str]:
    sk = serialization.load_pem_private_key(KEY.read_bytes(), password=None)
    pk = base64.b64encode(sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    return sk, pk


def enrol(name: str) -> None:
    if not KEY.exists():
        KEY.parent.mkdir(parents=True, exist_ok=True)
        KEY.write_bytes(Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    _, pk = load_key()
    reg = json.loads(server.INVESTIGATORS.read_text(encoding="utf-8")) if server.INVESTIGATORS.exists() else {"investigators": []}
    if not any(r["key_id"] == key_id(pk) for r in reg["investigators"]):
        reg["investigators"].append({"key_id": key_id(pk), "name": name, "public_key": pk, "role": "investigator",
                                     "enrolled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        server.INVESTIGATORS.write_text(json.dumps(reg, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"enrolled {name}: key {key_id(pk)}")


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--enrol")
    ap.add_argument("--run")
    ap.add_argument("--case")
    ap.add_argument("--decision", default="challenge", choices=["concur", "refer_for_site_visit", "dissent", "challenge"])
    ap.add_argument("--challenge", default="")
    ap.add_argument("--site", default="")
    ap.add_argument("--note", default="")
    a = ap.parse_args(argv)
    if a.enrol:
        return enrol(a.enrol)
    sk, pk = load_key()
    base = server.to_sign(a.run, a.case)
    st = {"run": a.run, "case": a.case, "decision": a.decision, "challenge": a.challenge, "note": a.note,
          "verdict": base["verdict"], "verdict_reason": base["verdict_reason"], "verdict_entry": base["verdict_entry"],
          "ledger_head": base["ledger_head"], "key_id": key_id(pk),
          "signed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "site": a.site.replace(" ", "")}
    payload = {"statement": st, "public_key": pk, "signature": base64.b64encode(sk.sign(message(st))).decode()}
    enrolled = registry(server.INVESTIGATORS)
    ok, why = check_entry(payload, enrolled)
    if not ok:
        sys.exit(why)
    lg, _ = open_run(a.run)
    e = lg.append(a.case, f"human:{st['key_id']}", "challenge" if a.decision == "challenge" else "signature",
                  {**payload, "investigator": enrolled[st["key_id"]]["name"]})
    print(f"sealed #{e.seq} {e.hash[:16]}… ({why})")
    if a.decision == "challenge" and a.challenge == "WRONG_SITE" and a.site:
        lon, lat = (float(x) for x in st["site"].split(","))
        print(server.reaudit(a.run, a.case, {"lon": lon, "lat": lat, "challenge_entry": e.hash, "challenge_seq": e.seq}, wait=True))
        c = json.loads((DATA / "runs" / a.run / "cases" / a.case / "case.json").read_text(encoding="utf-8"))
        print("now:", (c.get("verdict") or {}).get("outcome"), "-", (c.get("verdict") or {}).get("headline"))


if __name__ == "__main__":
    main(sys.argv[1:])
