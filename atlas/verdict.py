"""Deterministic evidence calculus.

Agents never decide the outcome. They file typed findings; this module counts
them. The rules are plain code so an investigator (or a court) can read them:

* A finding only counts if its quality clears QUALITY_FLOOR.
* "Probable ghost" needs the structure to be absent after the completion date
  in at least two INDEPENDENT sources. Two sources are independent only if the
  pixels come from different capture chains: two Maxar scenes are one source,
  and a canopy map computed from Maxar imagery is the same source as Maxar.
* A 10 m sensor cannot testify about a structure shorter than it can resolve.
* One source is a lead, not a finding: it yields "can't verify", with the reason.
* 10 m pixels can date a change and testify to absence, but they cannot say a
  wall is there: only sub-metre or street-level imagery establishes presence.
* "Declared before it was built" needs two chains too: sub-metre imagery shows
  the reach bare after the declared completion, and a 10 m series that was
  unchanged until then dates a lasting change only afterwards.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Literal

Claim = Literal["present", "absent", "inconclusive"]
Window = Literal["before_award", "during_contract", "after_completion"]
Outcome = Literal["exists", "exists_before_contract", "built_late", "relocated", "probable_ghost", "cant_verify"]

QUALITY_FLOOR = 0.6
# Shortest structure (m) a sensor family may testify about, from pixel size.
MIN_RESOLVABLE_M = {
    "optical_vhr": 10,  # sub-metre basemap imagery
    "street": 0,  # a photo from the bank sees what it sees
    "optical_hr": 150,  # Sentinel-2, 10 m: at least ~15 pixels along the bank
    "radar": 200,  # Sentinel-1, 10 m speckled: longer still
    "canopy": 20,  # 1 m canopy height
    "document": 0,
}
# Families whose pixels can identify a structure, not just a change.
PRESENCE_FAMILIES = {"optical_vhr", "street"}


@dataclass(frozen=True)
class Finding:
    agent: str
    source: str  # human-readable, e.g. "Wayback 2024-02-11 (Maxar WV3, 0.3 m)"
    family: str  # key of MIN_RESOLVABLE_M
    capture_root: str  # physical capture chain: "maxar", "s2", "s1", "mapillary:<user>", ...
    observed: str  # ISO date of the pixels
    claim: Claim
    quality: float
    note: str = ""
    entry: str = ""  # ledger hash of the entry that holds the evidence
    site: str = "declared"  # "declared" reach, or "elsewhere:<label>" for a relocation candidate


@dataclass
class SourceDecision:
    finding: Finding
    counted: bool
    why: str


@dataclass
class Verdict:
    outcome: Outcome
    reason: str  # stable code, e.g. "TWO_INDEPENDENT_ABSENT"
    headline: str
    explanation: list[str]
    counted_roots: list[str]
    decisions: list[SourceDecision] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["decisions"] = [
            {"finding": asdict(x.finding), "counted": x.counted, "why": x.why} for x in self.decisions
        ]
        return d


def window_of(observed: str, award: str, completion: str) -> Window:
    d = date.fromisoformat(observed[:10])
    if d < date.fromisoformat(award[:10]):
        return "before_award"
    if d <= date.fromisoformat(completion[:10]):
        return "during_contract"
    return "after_completion"


def decide(
    findings: list[Finding],
    *,
    award: str,
    completion: str,
    length_m: float | None,
    located: bool,
    locate_note: str = "",
) -> Verdict:
    if not located:
        return Verdict(
            "cant_verify",
            "SITE_NOT_LOCATABLE",
            "Can't verify: the site could not be located from the contract text.",
            [locate_note or "No river reach matched the description inside the stated barangay."],
            [],
        )

    decisions: list[SourceDecision] = []
    usable: list[tuple[Finding, Window]] = []
    dating: list[tuple[Finding, Window]] = []  # 10 m "present" findings: they date a change, they don't prove a wall
    for f in findings:
        w = window_of(f.observed, award, completion)
        min_len = MIN_RESOLVABLE_M.get(f.family, 0)
        if f.claim == "inconclusive":
            decisions.append(SourceDecision(f, False, f.note or "inconclusive"))
        elif f.quality < QUALITY_FLOOR:
            decisions.append(SourceDecision(f, False, f"quality {f.quality:.2f} below {QUALITY_FLOOR}"))
        elif f.claim == "absent" and length_m is not None and length_m < min_len:
            decisions.append(
                SourceDecision(f, False, f"a {length_m:.0f} m structure is below what {f.family} can resolve ({min_len} m)")
            )
        elif f.claim == "present" and f.family not in PRESENCE_FAMILIES:
            dating.append((f, w))
        else:
            usable.append((f, w))

    def roots(claim: Claim, window: Window, site: str = "declared") -> dict[str, Finding]:
        out: dict[str, Finding] = {}
        for f, w in usable:
            if f.claim == claim and w == window and f.site == site:
                out.setdefault(f.capture_root, f)
        return out

    present_before = roots("present", "before_award")
    present_after = roots("present", "after_completion")
    absent_after = roots("absent", "after_completion")
    elsewhere = {
        f.site: f
        for f, w in usable
        if f.claim == "present" and f.site.startswith("elsewhere") and w in ("during_contract", "after_completion")
    }

    def mark(counted: dict[str, Finding], why: str) -> None:
        ids = {id(f) for f in counted.values()}
        for f, w in usable:
            if id(f) in ids:
                decisions.append(SourceDecision(f, True, why))

    def mark_rest() -> None:
        seen = {id(d.finding) for d in decisions}
        for f, w in usable:
            if id(f) not in seen:
                same = [d for d in decisions if d.counted and d.finding.capture_root == f.capture_root]
                if same:
                    why = f"same capture chain as {same[0].finding.source}; not an independent source"
                else:
                    why = f"{w.replace('_', ' ')} observation; not decisive for this outcome"
                decisions.append(SourceDecision(f, False, why))

    # 1. A structure already standing before the award: an existing asset billed again.
    if present_before and not absent_after:
        mark(present_before, "structure visible before the award date")
        mark_rest()
        first = min(present_before.values(), key=lambda f: f.observed)
        return Verdict(
            "exists_before_contract",
            "PRESENT_BEFORE_AWARD",
            f"Exists, but it was already there on {first.observed}, before the contract was awarded on {award}.",
            [
                f"{first.source} shows the structure at the located reach before the award.",
                "An asset that predates its contract cannot be the work the contract paid for.",
            ],
            sorted(present_before),
            decisions,
        )

    # 1b. Sub-metre imagery shows the structure after completion, and a 10 m time series dates the
    # bank's change before the award, with no sub-metre capture showing the bank bare in between.
    dated_before = sorted((f for f, w in dating if w == "before_award"), key=lambda f: f.observed)
    if present_after and dated_before and not absent_after:
        first = dated_before[0]
        bare_between = [f for f, w in usable if f.claim == "absent" and f.family in PRESENCE_FAMILIES
                        and first.observed <= f.observed < award]
        if not bare_between:
            mark(present_after, "structure visible after completion")
            decisions.append(SourceDecision(first, True, f"dates the bank's change to {first.observed}, before the award"))
            mark_rest()
            return Verdict(
                "exists_before_contract",
                "PRESENT_AFTER_DATED_BEFORE_AWARD",
                f"Exists, but the bank changed around {first.observed}, before the contract was awarded on {award}.",
                [f"{next(iter(present_after.values())).source} shows the structure along the reach.",
                 f"{first.source}: {first.note}.",
                 "No sub-metre capture between that change and the award shows the bank bare."],
                sorted({*present_after, first.capture_root}),
                decisions,
            )

    # 1c. Bare after the declared completion in sub-metre imagery, and the bank changes only later: the work was
    # certified complete before it was done (if it was done at all).
    vhr_bare = [f for f, w in usable if f.claim == "absent" and w == "after_completion" and f.site == "declared"
                and f.family in PRESENCE_FAMILIES]
    if vhr_bare and not present_after and not elsewhere:
        last_bare = max(vhr_bare, key=lambda f: f.observed)
        later = sorted((f for f, w in dating if f.observed > last_bare.observed), key=lambda f: f.observed)
        if later:
            first = later[0]
            gap = (date.fromisoformat(last_bare.observed[:10]) - date.fromisoformat(completion[:10])).days // 30
            mark({last_bare.capture_root: last_bare}, "bare after the declared completion")
            decisions.append(SourceDecision(first, True, f"dates the first lasting change on the bank to {first.observed}, "
                                                         f"after the bare capture"))
            for f, w in dating:
                if f is not first:
                    decisions.append(SourceDecision(f, False, "dates a change on the bank; corroborates only"))
            mark_rest()
            return Verdict(
                "built_late",
                "BARE_AFTER_DECLARED_CHANGED_LATER",
                f"Declared complete on {completion}; still bare on {last_bare.observed}, {gap} months later. "
                f"The bank changed only around {first.observed}.",
                [f"{last_bare.source}: no structure at the located reach, after the completion date.",
                 f"{first.source}: {first.note}.",
                 "Two independent capture chains agree the works were not there when they were certified complete. "
                 "A 10 m change dates work; it does not show what was built."],
                sorted({last_bare.capture_root, first.capture_root}),
                decisions,
            )

    for f, w in dating:
        decisions.append(SourceDecision(
            f, False, "dates a change on the bank; 10 m pixels cannot identify a wall, so it corroborates only"))

    # 2. Independent sources disagree after completion.
    if present_after and absent_after and set(present_after) != set(absent_after):
        mark({**present_after, **absent_after}, "conflicting post-completion observations")
        mark_rest()
        return Verdict(
            "cant_verify",
            "CONFLICTING_SOURCES",
            "Can't verify: independent sources disagree after the completion date.",
            ["Present in " + ", ".join(f.source for f in present_after.values()) + ".",
             "Absent in " + ", ".join(f.source for f in absent_after.values()) + ".",
             "Sent to a human investigator for a site visit."],
            sorted({*present_after, *absent_after}),
            decisions,
        )

    # 3. The structure is there after completion.
    if present_after:
        mark(present_after, "structure visible after the completion date")
        mark_rest()
        best = max(present_after.values(), key=lambda f: f.quality)
        return Verdict(
            "exists",
            "PRESENT_AFTER_COMPLETION",
            f"Exists: visible after completion in {len(present_after)} source(s).",
            [f"{best.source} shows the structure at the located reach."],
            sorted(present_after),
            decisions,
        )

    # 4. Absent after completion.
    if len(absent_after) >= 2:
        if elsewhere:
            label, f_else = next(iter(elsewhere.items()))
            mark(absent_after, "absent at the declared reach after completion")
            decisions.append(SourceDecision(f_else, True, "new structure at another reach during the contract window"))
            mark_rest()
            return Verdict(
                "relocated",
                "ABSENT_HERE_PRESENT_ELSEWHERE",
                "Exists elsewhere: nothing at the declared reach, a new structure at another one.",
                [f"Absent at the declared reach in {len(absent_after)} independent sources.",
                 f"{f_else.source} shows a new structure at {label.split(':', 1)[-1]}."],
                sorted(absent_after),
                decisions,
            )
        mark(absent_after, "independent source: absent after the completion date")
        mark_rest()
        srcs = sorted(absent_after.values(), key=lambda f: f.observed)
        return Verdict(
            "probable_ghost",
            "TWO_INDEPENDENT_ABSENT",
            f"Probable ghost: absent after completion in {len(absent_after)} independent sources.",
            [f"{f.source}: no structure at the located reach." for f in srcs]
            + ["Two independent capture chains agree. A human investigator must sign before this leaves the system."],
            sorted(absent_after),
            decisions,
        )

    if len(absent_after) == 1:
        mark(absent_after, "absent after completion (one source only)")
        mark_rest()
        only = next(iter(absent_after.values()))
        return Verdict(
            "cant_verify",
            "SINGLE_SOURCE_ONLY",
            "Can't verify yet: one source shows nothing; the standard needs two independent ones.",
            [f"{only.source}: no structure at the located reach.",
             "Next: request a street-level photo or a new tasking over the site."],
            sorted(absent_after),
            decisions,
        )

    mark_rest()
    return Verdict(
        "cant_verify",
        "NO_POST_COMPLETION_IMAGERY",
        "Can't verify: no usable observation after the completion date.",
        ["Every observation after completion was cloudy, too coarse or missing."],
        [],
        decisions,
    )
