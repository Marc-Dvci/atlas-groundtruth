"""Case builder: the file an investigator signs.

Muse Wonder reads everything the fleet sealed for one contract (the record,
the located site, every capture reading, the time series, the timeline, the
money, the people behind the reach) and the verdict that code computed. It
writes the narrative; it cannot change the verdict. Every paragraph must cite
ledger entries, and code removes any paragraph whose citations don't resolve.
"""
from __future__ import annotations

import base64
import json

from ..case import Case
from ..meta import WONDER, image_edit
from ..verdict import Verdict

AGENT = "casebuilder"

INSTRUCTIONS = """You write the case file for one public-works contract in an audit of flood-control projects.
You receive the contract record, every sealed finding (with its ledger sequence number) and the verdict.
The verdict was computed by fixed rules; you may not change it, soften it or go beyond it.

Write for an investigator who will sign the file and may hand it to a prosecutor:
- Plain, short sentences. Dates as YYYY-MM-DD. Money in pesos.
- Every paragraph cites the ledger entries it rests on, by sequence number, in "cites".
- Describe observations and exceptions. Never write that anyone committed a crime, never use "fraud",
  "corrupt" or "stole", and never guess at intent. Name the contractor only as the party to the contract.
- Say what the evidence cannot show (resolution, cloud, misaligned captures, missing dates).
- Write like an experienced audit investigator, not like a log: lead with what the evidence shows, then
  how it was established, then what it cannot show. Four to six paragraphs. Never echo internal codes,
  field names, ids such as R1 or w945343789, or quality scores; say "the 2025 capture" not "finding 122".
  Say "Atlas" for the system.
- "open_questions" are things only a site visit or the agency's documents can settle.
- "requests" are documents to ask the agency or contractor for (as-built plans, inspection reports,
  geotagged progress photos, payment vouchers)."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "headline": {"type": "string"},
        "paragraphs": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"text": {"type": "string"}, "cites": {"type": "array", "items": {"type": "integer"}}},
            "required": ["text", "cites"]}},
        "limits": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "requests": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "paragraphs", "limits", "open_questions", "requests"],
}


def build(case: Case, verdict: Verdict, frames: list[dict]) -> dict:
    entries = [e.as_dict() for e in case.ledger.entries() if e.case == case.id]
    seqs = {e["seq"] for e in entries}
    slim = []
    for e in entries:
        p = dict(e["payload"])
        p.pop("ticks", None)
        if "reach" in p:
            p["reach"] = "(geometry)"
        slim.append({"seq": e["seq"], "agent": e["actor"], "kind": e["kind"], "payload": p})
    content = [{"type": "input_text", "text": json.dumps({
        "contract": case.record, "verdict": verdict.as_dict(), "ledger": slim}, ensure_ascii=False, default=str)[:400000]}]
    # the two captures that matter most, as pixels
    from ..agents.existence import wayback  # noqa: F401  (imagery already cached)
    from ..case import DATA
    key = [f for f in frames if f["window"] == "before_award"][-1:] + [f for f in frames if f["window"] != "before_award"][-1:]
    for f in key:
        p = DATA / "evidence" / f["blob"]
        if p.exists():
            content.append({"type": "input_text", "text": f"Capture {f['captured']} (ledger #{_seq(entries, f['entry'])})"})
            content.append({"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()})
    writer = case.facts.get("writer", WONDER)
    res = case.meta.structured(writer, INSTRUCTIONS, content, SCHEMA, schema_name="case_file",
                               effort="high" if writer == WONDER else "medium", est_usd=0.6)
    ans = res["data"]
    kept, dropped = [], []
    for para in ans.get("paragraphs", []):
        good = [c for c in para.get("cites", []) if c in seqs]
        (kept if good else dropped).append({**para, "cites": good})
    ans["paragraphs"] = kept
    ans["dropped_uncited"] = len(dropped)
    ans["model"] = writer
    case.record_entry(AGENT, "case_file", {"model": writer, "file": ans})
    case.say(AGENT, "case_file", **ans)
    return ans


def _seq(entries: list[dict], h: str) -> int | None:
    return next((e["seq"] for e in entries if e["hash"] == h), None)


def illustrate(case: Case, frames: list[dict], structure: str, length_m: float | None) -> dict | None:
    """Muse Image: the declared structure drawn onto the newest capture. An illustration, never evidence."""
    from shapely.geometry import shape

    from ..agents.existence import chip_for
    loc = case.facts["locator"]
    after = [f for f in frames if f["window"] == "after_completion"] or frames[-1:]
    if not after:
        return None
    f = after[-1]
    chip = chip_for(f["release"], f["bbox"])
    guide = chip.with_line(shape(loc["reach"]))
    prompt = (f"This is an overhead satellite photo of a riverbank. Along the cyan line, draw what this public-works "
              f"contract paid for: {structure}"
              + (f", about {int(length_m)} metres long" if length_m else "")
              + ". Make it a straight, light-grey reinforced-concrete wall on the bank, seen from above, at the same scale "
                "and lighting as the photo. Remove the cyan line. Change nothing else in the image.")
    png = image_edit(case.meta, guide, prompt, "image/jpeg")
    blob = case.blob(png, "png")
    out = {"blob": blob, "base_capture": f["captured"], "prompt": prompt, "label": "Illustration: what the contract describes"}
    case.record_entry(AGENT, "illustration", out)
    case.say(AGENT, "illustration", **out)
    return out
