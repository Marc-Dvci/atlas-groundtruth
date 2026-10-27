"""The evidence calculus: each rule in atlas/verdict.py, on hand-built findings."""
from atlas.verdict import Finding, decide

AWARD, DONE = "2024-02-01", "2024-08-01"


def vhr(day: str, claim: str, root: str = "maxar", q: float = 0.9, site: str = "declared") -> Finding:
    return Finding("existence", f"Wayback {day}", "optical_vhr", root, day, claim, q, site=site)


def s2(day: str, claim: str, q: float = 0.8) -> Finding:
    return Finding("existence", f"Sentinel-2 {day}", "optical_hr", "s2", day, claim, q)


def street(day: str, claim: str, who: str = "a") -> Finding:
    return Finding("ground", f"Mapillary {day}", "street", f"mapillary:{who}", day, claim, 0.8)


def run(findings, length=200.0, located=True):
    return decide(findings, award=AWARD, completion=DONE, length_m=length, located=located)


def test_two_independent_chains_absent_is_a_probable_ghost():
    v = run([vhr("2025-01-10", "absent"), s2("2025-06-01", "absent")])
    assert v.outcome == "probable_ghost"
    assert v.counted_roots == ["maxar", "s2"]


def test_one_chain_is_a_lead_not_a_finding():
    v = run([vhr("2025-01-10", "absent")])
    assert (v.outcome, v.reason) == ("cant_verify", "SINGLE_SOURCE_ONLY")


def test_two_captures_from_the_same_constellation_are_one_source():
    v = run([vhr("2025-01-10", "absent"), vhr("2025-05-02", "absent")])
    assert v.outcome == "cant_verify"


def test_a_street_photo_is_its_own_chain():
    v = run([vhr("2025-01-10", "absent"), street("2025-03-01", "absent")])
    assert v.outcome == "probable_ghost"


def test_ten_metre_pixels_cannot_establish_presence():
    v = run([s2("2025-01-10", "present")])
    assert v.outcome == "cant_verify"
    assert all(not d.counted for d in v.decisions)


def test_ten_metre_pixels_cannot_testify_about_a_short_wall():
    v = run([vhr("2025-01-10", "absent"), s2("2025-06-01", "absent")], length=60)
    assert v.outcome == "cant_verify"


def test_low_quality_readings_do_not_count():
    v = run([vhr("2025-01-10", "absent", q=0.4), s2("2025-06-01", "absent")])
    assert v.outcome == "cant_verify"


def test_present_after_completion_exists():
    v = run([vhr("2023-01-10", "absent"), vhr("2025-01-10", "present")])
    assert v.outcome == "exists"


def test_present_before_the_award_existed_before_the_contract():
    v = run([vhr("2023-01-10", "present"), vhr("2025-01-10", "present")])
    assert v.outcome == "exists_before_contract"


def test_ten_metre_series_can_date_a_wall_seen_later_to_before_the_award():
    v = run([vhr("2025-01-10", "present"), s2("2023-03-01", "present")])
    assert (v.outcome, v.reason) == ("exists_before_contract", "PRESENT_AFTER_DATED_BEFORE_AWARD")


def test_independent_chains_that_disagree_go_to_a_human():
    v = run([vhr("2025-01-10", "present"), street("2025-03-01", "absent")])
    assert (v.outcome, v.reason) == ("cant_verify", "CONFLICTING_SOURCES")


def test_bare_after_completion_then_a_later_change_was_declared_before_built():
    v = run([vhr("2025-01-10", "absent"), s2("2025-09-01", "present")])
    assert (v.outcome, v.reason) == ("built_late", "BARE_AFTER_DECLARED_CHANGED_LATER")
    assert v.counted_roots == ["maxar", "s2"]


def test_a_change_before_the_bare_capture_is_not_late_work():
    v = run([vhr("2025-01-10", "absent"), s2("2024-09-01", "present")])
    assert v.outcome == "cant_verify"


def test_absent_here_and_new_elsewhere_is_relocated():
    v = run([vhr("2025-01-10", "absent"), s2("2025-06-01", "absent"),
             vhr("2025-01-10", "present", site="elsewhere:600 m from the declared reach")])
    assert v.outcome == "relocated"


def test_unlocatable_site_cannot_be_verified():
    v = run([], located=False)
    assert (v.outcome, v.reason) == ("cant_verify", "SITE_NOT_LOCATABLE")


def test_every_finding_gets_a_decision_with_a_reason():
    fs = [vhr("2020-01-10", "absent"), vhr("2025-01-10", "absent"), s2("2025-06-01", "absent"), street("2025-02-01", "inconclusive")]
    v = run(fs)
    assert len(v.decisions) == len(fs)
    assert all(d.why for d in v.decisions)


def test_readers_that_disagree_are_not_missing_imagery():
    f = Finding("existence", "Wayback 2025-01-10", "optical_vhr", "maxar", "2025-01-10", "inconclusive", 0.0,
                note="readers disagree")
    v = run([f])
    assert (v.outcome, v.reason) == ("cant_verify", "NO_DECISIVE_OBSERVATION")
    assert "readers disagree" in v.explanation[0]


def test_nothing_after_completion_is_missing_imagery():
    v = run([vhr("2023-05-01", "absent")])
    assert (v.outcome, v.reason) == ("cant_verify", "NO_POST_COMPLETION_IMAGERY")
