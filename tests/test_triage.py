"""Triage: a structure that predates its contract is a lead only when nothing else explains it."""
from atlas.triage import assess, concurrent_on_reach, scope, visible_addition

AWARD, DONE = "2024-02-01", "2024-08-01"


def frame(day: str, banks: list[tuple[str, str, float]]) -> dict:
    return {"captured": day, "reading": {"quality": "good", "structure_visible": "yes" if any(b[1] == "yes" for b in banks) else "no",
                                         "banks": [{"side": s, "structure": st, "extent_fraction": x} for s, st, x in banks]}}


def case(desc="Construction of Flood Control Structure along Angat River", reason="PRESENT_BEFORE_AWARD", frames=None,
         s2=None, prior=None, outcome="exists_before_contract") -> dict:
    return {"record": {"desc": desc}, "award": AWARD, "completion": DONE, "verdict": {"outcome": outcome, "reason": reason},
            "frames": frames if frames is not None else [frame("2020-01-30", [("west", "yes", 0.9), ("east", "no", 0)]),
                                                         frame("2025-04-20", [("west", "yes", 0.9), ("east", "no", 0)])],
            "s2": s2 or {}, "valuation": {"prior": prior or []}}


SAME = {"agree": True, "overlap": 1.0, "why": "the reaches overlap along 100% of their length"}
codes = lambda t: [r["code"] for r in t["reasons"]]  # noqa: E731


def test_billed_as_new_with_nothing_added_is_a_lead():
    t = assess(case(), SAME)
    assert t["tier"] == "lead"
    assert "BILLED_AS_NEW_NOTHING_ADDED" in codes(t)


def test_repair_words_need_the_plans():
    t = assess(case(desc="Rehabilitation of River Protection Structure along Bulusan"), SAME)
    assert t["tier"] == "needs_plans"
    assert "SCOPE_ADMITS_EXISTING" in codes(t)


def test_a_later_phase_needs_the_plans():
    assert scope("Construction of Riverbank Protection Structure at Malis (Phase III)")["scope"] == "later_phase"


def test_a_new_bank_after_the_award_is_visible_work():
    fr = [frame("2020-01-30", [("west", "yes", 0.9), ("east", "no", 0)]),
          frame("2025-04-20", [("west", "yes", 0.9), ("east", "yes", 0.7)])]
    assert visible_addition(fr, AWARD)["added"] is True
    assert assess(case(frames=fr), SAME)["tier"] == "needs_plans"


def test_a_structure_that_grew_a_quarter_of_the_reach_is_visible_work():
    fr = [frame("2020-01-30", [("west", "yes", 0.5)]), frame("2025-04-20", [("west", "yes", 0.8)])]
    assert visible_addition(fr, AWARD)["added"] is True


def test_dated_by_ten_metre_pixels_alone_needs_the_plans():
    t = assess(case(reason="PRESENT_AFTER_DATED_BEFORE_AWARD"), SAME)
    assert "DATED_BY_10M_ONLY" in codes(t) and t["tier"] == "needs_plans"


def test_sentinel2_work_in_the_contract_window_needs_the_plans():
    s2 = {"disturbance": {"date": "2024-03-10", "last": "2024-05-01", "bank": "west bank"}}
    t = assess(case(s2=s2), SAME)
    assert "CHANGE_IN_CONTRACT_WINDOW" in codes(t) and t["tier"] == "needs_plans"


def test_a_change_years_before_the_award_is_not_in_the_window():
    s2 = {"first_change": {"date": "2020-06-01", "last": "2020-09-01", "bank": "west bank"}}
    assert assess(case(s2=s2), SAME)["tier"] == "lead"


def test_a_disputed_site_outranks_everything():
    t = assess(case(outcome="probable_ghost", reason="TWO_INDEPENDENT_ABSENT"), {"agree": False, "why": "the reaches are 240 m apart"})
    assert t["tier"] == "site_disputed"


def test_reaches_that_only_touch_are_a_disputed_site():
    t = assess(case(), {"agree": True, "gap_m": 0, "overlap": 0.13, "why": "the reaches overlap along 13% of their length"})
    assert t["tier"] == "site_disputed"


def test_an_unchecked_site_is_said_so():
    assert assess(case(outcome="probable_ghost", reason="TWO_INDEPENDENT_ABSENT"), None)["tier"] == "site_unchecked"


def test_earlier_contracts_are_listed_but_do_not_decide():
    t = assess(case(prior=[{"id": "22CC0001", "cost": 40e6}]), SAME)
    assert "EARLIER_CONTRACTS_NEARBY" in codes(t) and t["tier"] == "lead"


def test_unflagged_outcomes_are_not_triaged():
    assert assess(case(outcome="exists", reason="PRESENT_AFTER_COMPLETION"), SAME)["tier"] is None


def test_exists_is_dated_when_the_reach_was_bare_shortly_before_the_award():
    fr = [frame("2023-06-01", [("west", "no", 0)]), frame("2025-04-20", [("west", "yes", 0.9)])]
    t = assess(case(outcome="exists", reason="PRESENT_AFTER_COMPLETION", frames=fr), SAME)
    assert t["tier"] is None and t["exists_dated"] is True


def test_exists_is_not_dated_when_the_last_bare_capture_is_years_before():
    fr = [frame("2020-01-30", [("west", "no", 0)]), frame("2025-04-20", [("west", "yes", 0.9)])]
    t = assess(case(outcome="exists", reason="PRESENT_AFTER_COMPLETION", frames=fr), SAME)
    assert t["exists_dated"] is False and "NOT_DATED_TO_CONTRACT" in codes(t) and t["cleared"] is False


BARE_THEN_WALL = [frame("2023-06-01", [("west", "no", 0)]), frame("2025-04-20", [("west", "yes", 0.9)])]


def test_exists_dated_alone_on_a_confirmed_site_is_cleared():
    t = assess(case(outcome="exists", reason="PRESENT_AFTER_COMPLETION", frames=BARE_THEN_WALL), SAME)
    assert t["cleared"] is True and "CLEARED" in codes(t)


def test_one_wall_cannot_clear_two_concurrent_contracts():
    other = [{"id": "24CC0155", "award": "2024-03-01", "completion": "2024-10-27", "overlap": 0.9}]
    t = assess(case(outcome="exists", reason="PRESENT_AFTER_COMPLETION", frames=BARE_THEN_WALL), SAME, other)
    assert t["cleared"] is False and "SHARED_REACH" in codes(t) and t["shared_with"] == ["24CC0155"]


def test_exists_on_an_unchecked_site_is_not_cleared():
    t = assess(case(outcome="exists", reason="PRESENT_AFTER_COMPLETION", frames=BARE_THEN_WALL), None)
    assert t["cleared"] is False and "SITE_UNCHECKED" in codes(t)


def test_concurrent_contracts_on_the_same_reach_are_found():
    line = {"type": "LineString", "coordinates": [[120.90, 14.80], [120.902, 14.80]]}  # about 215 m
    near = {"type": "LineString", "coordinates": [[120.9002, 14.8001], [120.9021, 14.8001]]}
    far = {"type": "LineString", "coordinates": [[120.91, 14.80], [120.912, 14.80]]}
    me = {"id": "A", "award": "2024-02-01", "completion": "2024-08-01", "locator": {"reach": line}}
    others = [{"id": "B", "award": "2024-05-01", "completion": "2024-12-01", "locator": {"reach": near}},  # same reach, same time
              {"id": "C", "award": "2022-01-01", "completion": "2022-06-01", "locator": {"reach": near}},  # same reach, earlier
              {"id": "D", "award": "2024-05-01", "completion": "2024-12-01", "locator": {"reach": far}}]  # same time, 1 km away
    assert [o["id"] for o in concurrent_on_reach(me, others)] == ["B"]
