"""The evidence ledger: an edit anywhere breaks every seal after it; pixels are sealed by their own hash."""
import json

from atlas.ledger import Ledger


def make(tmp_path, n=5):
    lg = Ledger(tmp_path / "ledger.jsonl", tmp_path / "blobs")
    blob = lg.put_blob(b"\xff\xd8 pixels", "jpg")
    for i in range(n):
        lg.append("C1", "existence", "finding", {"finding": {"claim": "absent", "i": i}, "blob": blob})
    return lg, blob


def test_a_fresh_chain_verifies(tmp_path):
    lg, _ = make(tmp_path)
    assert lg.verify() == (True, None, "chain intact")


def test_editing_one_claim_breaks_the_chain_at_that_entry(tmp_path):
    lg, _ = make(tmp_path)
    lines = lg.path.read_text(encoding="utf-8").splitlines()
    e = json.loads(lines[2])
    e["payload"]["finding"]["claim"] = "present"
    lines[2] = json.dumps(e, ensure_ascii=False)
    lg.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, bad, why = Ledger(lg.path, lg.blob_dir).verify()
    assert (ok, bad) == (False, 2)
    assert "changed" in why


def test_rehashing_an_edited_entry_still_breaks_the_next_link(tmp_path):
    from atlas.ledger import entry_hash
    lg, _ = make(tmp_path)
    lines = lg.path.read_text(encoding="utf-8").splitlines()
    e = json.loads(lines[1])
    e["payload"]["finding"]["claim"] = "present"
    e["hash"] = entry_hash(e["seq"], e["ts"], e["case"], e["actor"], e["kind"], e["payload"], e["prev"])
    lines[1] = json.dumps(e, ensure_ascii=False)
    lg.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, bad, why = Ledger(lg.path, lg.blob_dir).verify()
    assert (ok, bad, why) == (False, 2, "broken link to previous entry")


def test_changing_one_pixel_of_sealed_evidence_is_caught(tmp_path):
    lg, blob = make(tmp_path)
    (lg.blob_dir / blob).write_bytes(b"\xff\xd8 pixelz")
    ok, bad, why = lg.verify()
    assert (ok, bad) == (False, 0)
    assert "altered" in why


def test_a_reopened_ledger_continues_the_chain(tmp_path):
    lg, _ = make(tmp_path, 3)
    lg2 = Ledger(lg.path, lg.blob_dir)
    e = lg2.append("C1", "human:investigator", "signature", {"decision": "concur"})
    assert e.seq == 3 and e.prev == lg.head
    assert lg2.verify()[0]
