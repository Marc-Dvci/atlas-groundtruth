"""Anchor each run's ledger head outside Atlas: RFC 3161 timestamps from two independent timestamp authorities.

    .venv/Scripts/python scripts/anchor.py --runs eval eval-open bulacan
    .venv/Scripts/python scripts/anchor.py --check bulacan

A hash chain shows that nothing changed after an entry was written, but whoever holds the whole ledger could rewrite
it and every hash after the edit. A timestamp authority signs "this hash existed at this time" with its own key, so a
ledger rewritten after an anchor no longer matches the anchored head. Each token is stored as an evidence file and
sealed by an "anchor" entry on the same chain; `openssl ts -verify` checks it with no Atlas code at all:

    openssl ts -verify -digest <head> -in <token>.tsr -CAfile <authority's CA certificate>
"""
from __future__ import annotations

import argparse
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atlas.case import DATA  # noqa: E402
from atlas.ledger import Ledger  # noqa: E402

CERTS = ROOT / "docs" / "anchors"
TSAS = {
    "FreeTSA": {"url": "https://freetsa.org/tsr", "ca": "freetsa_cacert.pem",
                "ca_url": "https://freetsa.org/files/cacert.pem"},
    "DigiCert": {"url": "http://timestamp.digicert.com", "ca": "digicert_roots.pem", "ca_url": None},
}


def query(digest_hex: str) -> bytes:
    """TimeStampReq (RFC 3161) for a SHA-256 digest, asking for the authority's certificate."""
    imprint = bytes.fromhex("300d06096086480165030402010500") + b"\x04\x20" + bytes.fromhex(digest_hex)
    imprint = b"\x30" + bytes([len(imprint)]) + imprint
    nonce = b"\x02\x08" + bytes([secrets.randbelow(0x7F) + 1]) + secrets.token_bytes(7)
    body = b"\x02\x01\x01" + imprint + nonce + b"\x01\x01\xff"
    return b"\x30" + bytes([len(body)]) + body


def openssl() -> str:
    for c in (shutil.which("openssl"), r"C:\Program Files\Git\mingw64\bin\openssl.exe", "/usr/bin/openssl"):
        if c and Path(c).exists():
            return c
    raise RuntimeError("openssl not found")


def ca_file(name: str) -> Path:
    t = TSAS[name]
    p = CERTS / t["ca"]
    if not p.exists():
        CERTS.mkdir(parents=True, exist_ok=True)
        if t["ca_url"]:
            p.write_bytes(httpx.get(t["ca_url"], timeout=30, follow_redirects=True).content)
        else:  # DigiCert's TSA chains to roots every trust store carries
            import certifi
            p.write_text(Path(certifi.where()).read_text(encoding="utf-8"), encoding="utf-8")
    return p


def check(tsr: bytes, digest_hex: str, tsa: str) -> tuple[bool, str, str]:
    """(verified, generation time, serial) using openssl only."""
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "t.tsr"
        f.write_bytes(tsr)
        txt = subprocess.run([openssl(), "ts", "-reply", "-in", str(f), "-text"], capture_output=True, text=True).stdout
        v = subprocess.run([openssl(), "ts", "-verify", "-digest", digest_hex, "-in", str(f), "-CAfile", str(ca_file(tsa))],
                           capture_output=True, text=True)
    when = re.search(r"Time stamp:\s*(.+)", txt)
    serial = re.search(r"Serial number:\s*(\S+)", txt)
    return ("Verification: OK" in v.stdout + v.stderr, when.group(1).strip() if when else "",
            serial.group(1) if serial else "")


def anchor(run: str) -> list[dict]:
    lg = Ledger(DATA / "runs" / run / "ledger.jsonl", DATA / "evidence")
    entries = list(lg.entries())
    last = entries[-1]
    if last.kind == "anchor":
        print(f"{run}: head #{last.seq} is itself an anchor; nothing new to anchor")
        return []
    out = []
    for name, t in TSAS.items():
        r = httpx.post(t["url"], content=query(last.hash), headers={"Content-Type": "application/timestamp-query"},
                       timeout=60, follow_redirects=True)
        r.raise_for_status()
        ok, when, serial = check(r.content, last.hash, name)
        if not ok:
            raise RuntimeError(f"{name}: token for {last.hash[:12]} does not verify")
        blob = lg.put_blob(r.content, "tsr")
        e = lg.append("*", "anchor", "anchor", {
            "anchored_seq": last.seq, "anchored_head": last.hash, "authority": name, "authority_url": t["url"],
            "time": when, "serial": serial, "tsr_blob": blob, "ca_certificate": f"docs/anchors/{t['ca']}",
            "verify": f"openssl ts -verify -digest {last.hash} -in {blob} -CAfile {t['ca']}"})
        out.append(e.payload)
        print(f"{run}: #{last.seq} {last.hash[:16]}… anchored by {name} at {when} (sealed as #{e.seq})")
    return out


def check_run(run: str) -> bool:
    """Re-check every anchor in a run: the token verifies and the anchored hash is the chain's entry at that seq."""
    lg = Ledger(DATA / "runs" / run / "ledger.jsonl", DATA / "evidence")
    by_seq = {}
    good = True
    for e in lg.entries():
        by_seq[e.seq] = e.hash
        if e.kind != "anchor":
            continue
        p = e.payload
        ok, when, _ = check((DATA / "evidence" / p["tsr_blob"]).read_bytes(), p["anchored_head"], p["authority"])
        same = by_seq.get(p["anchored_seq"]) == p["anchored_head"]
        good &= ok and same
        print(f"{run}: #{p['anchored_seq']} by {p['authority']} at {when}: token {'verifies' if ok else 'FAILS'}, "
              f"{'matches the chain' if same else 'DOES NOT MATCH the chain'}")
    return good


def main(argv: list[str]) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="*", default=[])
    ap.add_argument("--check", nargs="*", default=[])
    a = ap.parse_args(argv)
    for run in a.runs:
        anchor(run)
    ok = all([check_run(run) for run in a.check])
    if a.check and not ok:
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
