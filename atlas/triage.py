"""Triage: what an investigator should do next with a flagged contract.

The verdict says what the imagery shows. Triage says whether that is a lead an investigator can take up now, or a
question the paperwork or a second look must answer first. Like the verdict, it is plain code over sealed evidence:

* Site. A second Locator, on another model and another host, re-locates the contract from its text alone. Unless its
  reach runs along at least half of the one the verdict was read on, the case is "site disputed": no lead until an
  investigator confirms which reach the contract paid for. A case nobody re-located is "site unchecked". Two Locators
  agreeing shows the contract's words point to one reach; only the approved plans show where the works were meant to be.
* A structure that predates the contract is not by itself an improper contract: the contract may have repaired,
  raised or extended it, or built another section. It becomes a lead only when all of these hold:
  - sub-metre imagery shows the structure before the award (a 10 m change date alone is not enough);
  - the contract's own words describe new construction, not rehabilitation, repair, improvement, a later phase or
    an extension;
  - nothing visibly changed between the last sub-metre capture before the award and the last one after it: no bank
    gained a structure, no structure grew by a quarter of the reach or more;
  - Sentinel-2 shows no change or work-like disturbance on the banks during the contract window.
  Otherwise it "needs the plans": the as-built plans must say what the contract added, and where.
* Probable ghost, built elsewhere, declared before built: a lead once the site is confirmed.

"Exists" is not a clearance either. It says a structure stands at the reach the text describes after completion. A
contract is cleared only when all three hold (rules added on 28 Oct 2026, after the blind test showed Atlas clearing
contracts officials had found built elsewhere or already there):
  - dated: sub-metre imagery shows the reach without the structure at most 18 months before the award and with it
    afterwards, or Sentinel-2 dates a lasting change to the contract window. Otherwise it may be older;
  - one wall, one contract: no other contract whose works ran at the same time claims the same reach (the two located
    reaches run along each other for at least half their length). One structure cannot show which of them built it;
  - site confirmed: the second Locator found the same reach.
Every other "exists" goes to an investigator with the reasons.

Earlier contracts paid for works near the same reach are listed with every case: they may explain a structure that
predates this contract, or show the same works paid twice. Either way the investigator needs to see them.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Literal

Tier = Literal["lead", "needs_plans", "site_disputed", "site_unchecked"]
FLAGGED = ("probable_ghost", "relocated", "built_late", "exists_before_contract")
GROWTH = 0.25  # share of the reach a structure must gain to count as visible work
SAME_REACH = 0.5  # share of their length two located reaches must run along each other to be one site
SAME_SITE_M = 50  # and the largest gap between them
OVERLAP_BUFFER_M = 40  # a reach runs along another where it stays within this distance of it
AFTER_WINDOW_DAYS = 365  # works often go on after the declared completion

_REPAIR = re.compile(r"\b(rehabilitat\w*|repair\w*|restor\w*|retrofit\w*|improvement|improving|upgrad\w*|rais(e|ing)\w*|"
                     r"heighten\w*|strengthen\w*|reinforc\w*|reconstruct\w*|maintenance)\b", re.I)
_LATER = re.compile(r"\b(phase\s*(ii|iii|iv|v|vi|2|3|4|5|6)\b|continuation|extension|additional|completion of)", re.I)
_YES = ("yes", "partly")
DATING_GAP_MONTHS = 18  # the last capture without the structure must be this close to the award to date it


def reach_overlap(a: dict, b: dict) -> tuple[float, float]:
    """Gap (m) between two located reaches (GeoJSON), and the share of each that runs along the other (the smaller)."""
    from shapely.geometry import shape

    from .geo.geom import to_m
    ra, rb = to_m(shape(a)), to_m(shape(b))
    ov = min(ra.intersection(rb.buffer(OVERLAP_BUFFER_M)).length / max(ra.length, 1),
             rb.intersection(ra.buffer(OVERLAP_BUFFER_M)).length / max(rb.length, 1))
    return ra.distance(rb), ov


def concurrent_on_reach(case: dict, others: list[dict]) -> list[dict]:
    """Other contracts whose works window overlaps this one's and whose located reach is the same site."""
    reach = (case.get("locator") or {}).get("reach")
    if not reach:
        return []
    out = []
    for o in others:
        r = (o.get("locator") or {}).get("reach")
        if o["id"] == case["id"] or not r or not (o["award"] <= case["completion"] and case["award"] <= o["completion"]):
            continue
        gap, ov = reach_overlap(reach, r)
        if gap < SAME_SITE_M and ov >= SAME_REACH:
            out.append({"id": o["id"], "award": o["award"], "completion": o["completion"], "overlap": round(ov, 2),
                        "outcome": (o.get("verdict") or {}).get("outcome"), "cost": (o.get("record") or {}).get("cost")})
    return out


def scope(desc: str) -> dict:
    """What the contract's own words say it paid for: new construction, or works that assume a structure exists."""
    d = desc or ""
    later = _LATER.search(d)
    repair = _REPAIR.search(d)
    if later:
        return {"scope": "later_phase", "words": later.group(0), "admits_existing": True}
    if repair:
        kind = "mixed" if re.search(r"construction of", d, re.I) else "repair"
        return {"scope": kind, "words": repair.group(0), "admits_existing": True}
    return {"scope": "new", "words": None, "admits_existing": False}


def _banks(reading: dict) -> tuple[int, float]:
    """Banks with a structure, and the largest share of the reach a structure covers."""
    bs = reading.get("banks") or []
    with_structure = [b for b in bs if b.get("structure") in _YES]
    extent = max((b.get("extent_fraction") or 0.0 for b in with_structure), default=0.0)
    if not bs and reading.get("structure_visible") in _YES:
        return 1, float(reading.get("extent_fraction") or 0.0)
    return len(with_structure), float(extent)


def visible_addition(frames: list[dict], award: str) -> dict:
    """Compare the last readable sub-metre capture before the award with the last one after it."""
    rd = [f for f in frames if f.get("reading") and f.get("site", "declared") == "declared"
          and (f["reading"].get("quality") or "good") not in ("poor", "unusable")]
    before = [f for f in rd if f["captured"] < award]
    after = [f for f in rd if f["captured"] >= award]
    if not before or not after:
        return {"known": False, "added": None,
                "why": "no readable capture " + ("before the award" if not before else "after the award") + " to compare"}
    b, a = before[-1], after[-1]
    nb, eb = _banks(b["reading"])
    na, ea = _banks(a["reading"])
    added = na > nb or ea - eb >= GROWTH
    if na > nb:
        why = f"a structure on {na} bank(s) on {a['captured']}, on {nb} on {b['captured']}"
    elif ea - eb >= GROWTH:
        why = f"the structure covers {ea:.0%} of the reach on {a['captured']}, {eb:.0%} on {b['captured']}"
    else:
        why = f"same banks and extent on {b['captured']} ({eb:.0%}) and {a['captured']} ({ea:.0%})"
    return {"known": True, "added": added, "before": b["captured"], "after": a["captured"], "why": why}


def change_in_window(s2: dict, award: str, completion: str) -> dict | None:
    """A Sentinel-2 change or work-like disturbance on the banks between the award and a year after completion."""
    lo = date.fromisoformat(award[:10])
    hi = date.fromisoformat(completion[:10]) + timedelta(days=AFTER_WINDOW_DAYS)
    for kind in ("first_change", "disturbance"):
        ev = (s2 or {}).get(kind)
        if not ev:
            continue
        first = date.fromisoformat(ev["date"][:10])
        last = date.fromisoformat((ev.get("last") or ev["date"])[:10])
        if first <= hi and last >= lo:
            return {"kind": kind, "date": ev["date"], "last": ev.get("last"), "bank": ev.get("bank")}
    return None


def dated_to_contract(case: dict) -> dict:
    """Does anything tie a standing structure to this contract's window, rather than to an earlier one?"""
    award, completion = case.get("award") or "", case.get("completion") or ""
    vis = visible_addition(case.get("frames") or [], award)
    win = change_in_window(case.get("s2") or {}, award, completion)
    if win and win["kind"] == "first_change":
        return {"dated": True, "why": f"Sentinel-2 dates a lasting change on the {win.get('bank') or 'banks'} to {win['date']}, "
                                      f"inside the contract window."}
    if vis["known"] and vis["added"]:
        gap = (date.fromisoformat(award[:10]) - date.fromisoformat(vis["before"][:10])).days / 30.4
        if gap <= DATING_GAP_MONTHS:
            return {"dated": True, "why": f"Sub-metre imagery: {vis['why']}; the earlier capture is {gap:.0f} months before "
                                          f"the award."}
        return {"dated": False, "why": f"The structure appears between {vis['before']} and {vis['after']}, but the earlier "
                                       f"capture is {gap:.0f} months before the award: it may be older than this contract."}
    return {"dated": False, "why": "No capture shows the reach without the structure before the award, and Sentinel-2 dates "
                                   "no lasting change to the contract window."}


def assess(case: dict, site_check: dict | None, concurrent: list[dict] | None = None) -> dict:
    """case: the sealed case.json of one contract; site_check: the second Locator's comparison, if any; concurrent:
    the other contracts on the same reach whose works ran at the same time (concurrent_on_reach)."""
    v = case.get("verdict") or {}
    oc = v.get("outcome")
    if oc not in FLAGGED and oc != "exists":
        return {"tier": None, "reasons": []}
    reasons: list[dict] = []
    concurrent = concurrent or []

    def say(code: str, text: str) -> None:
        reasons.append({"code": code, "text": text})

    def shared() -> None:
        if concurrent:
            say("SHARED_REACH", f"{len(concurrent)} other contract(s) whose works ran at the same time claim the same reach: "
                                + ", ".join(o["id"] for o in concurrent[:4]) + ("…" if len(concurrent) > 4 else "")
                                + ". One structure there cannot show which of them built it.")

    if site_check is None or site_check.get("agree") is None:
        site = "unchecked"
        say("SITE_UNCHECKED", "No second Locator has re-located this contract yet.")
    elif site_check["agree"] and (site_check.get("overlap") or 0) >= SAME_REACH:
        site = "confirmed"
        say("SITE_CONFIRMED", f"A second Locator ({site_check.get('model', 'Muse Spark Open')}) found the same reach: "
                              f"{site_check.get('why')}.")
    else:
        site = "disputed"
        why = (site_check.get("why") if not site_check["agree"] else
               f"the reaches touch but run along each other for only {(site_check.get('overlap') or 0):.0%} of their length")
        say("SITE_DISPUTED", f"A second Locator ({site_check.get('model', 'Muse Spark Open')}) placed the works elsewhere: "
                             f"{why}. An investigator must confirm the site first.")

    if oc == "exists":
        d = dated_to_contract(case)
        say("DATED_TO_CONTRACT" if d["dated"] else "NOT_DATED_TO_CONTRACT", d["why"])
        shared()
        cleared = d["dated"] and not concurrent and site == "confirmed"
        if cleared:
            say("CLEARED", "Dated to this contract, no concurrent contract on the reach, and both Locators agree on it.")
        return {"tier": None, "exists_dated": d["dated"], "cleared": cleared, "site": site,
                "shared_with": [o["id"] for o in concurrent], "reasons": reasons}
    shared()
    rec = case.get("record") or {}
    sc = scope(rec.get("desc") or "")
    vis = visible_addition(case.get("frames") or [], case.get("award") or rec.get("start") or "")
    win = change_in_window(case.get("s2") or {}, case.get("award") or "", case.get("completion") or "")
    prior = (case.get("valuation") or {}).get("prior") or []
    plans = False
    if oc == "exists_before_contract":
        if v.get("reason") != "PRESENT_BEFORE_AWARD":
            plans = True
            say("DATED_BY_10M_ONLY", "No sub-metre capture shows the structure before the award; only a 10 m Sentinel-2 "
                                     "change dates it before. Sub-metre imagery shows it appear between "
                                     "captures that straddle the award.")
        if sc["admits_existing"]:
            plans = True
            say("SCOPE_ADMITS_EXISTING", f"The contract's words (\"{sc['words']}\") describe work that can be done on an "
                                         f"existing structure.")
        if vis["added"] is None:
            plans = True
            say("NO_BEFORE_AFTER_PAIR", f"Can't tell whether anything was added: {vis['why']}.")
        elif vis["added"]:
            plans = True
            say("VISIBLE_ADDITION", f"Something visibly changed: {vis['why']}.")
        if win:
            plans = True
            say("CHANGE_IN_CONTRACT_WINDOW", f"Sentinel-2 shows a {'lasting change' if win['kind'] == 'first_change' else 'work-like disturbance'} "
                                             f"on the {win.get('bank') or 'banks'} from {win['date']}, inside the contract window.")
        if not plans:
            say("BILLED_AS_NEW_NOTHING_ADDED", f"Billed as new construction; the structure stands before the award and "
                                               f"nothing visibly changed ({vis['why']}).")
    if prior:
        tot = sum(p.get("cost") or 0 for p in prior)
        say("EARLIER_CONTRACTS_NEARBY", f"{len(prior)} earlier contract(s), ₱{tot / 1e6:,.1f} million, published within 200 m "
                                        f"and completed before this one started: "
                                        + ", ".join(p["id"] for p in prior[:4]) + ("…" if len(prior) > 4 else "") + ".")
    tier: Tier = ("site_disputed" if site == "disputed" else "needs_plans" if plans
                  else "site_unchecked" if site == "unchecked" else "lead")
    return {"tier": tier, "site": site, "scope": sc, "visible": vis, "change_in_window": win,
            "earlier_contracts": [p["id"] for p in prior], "shared_with": [o["id"] for o in concurrent], "reasons": reasons}


TIER_TEXT = {
    "lead": "Lead: ready for an investigator",
    "needs_plans": "Needs the plans: the as-built plans must say what was added",
    "site_disputed": "Site disputed: confirm the reach first",
    "site_unchecked": "Site not re-checked",
    "revised": "Revised after a signed challenge",
}
