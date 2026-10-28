"""The second-reader rule: a decisive reading counts only when a second model explicitly agrees with it."""
from atlas.agents.existence import confirm, cross_read
from atlas.verdict import Finding, decide


class Chip:
    def with_line(self, reach) -> bytes:
        return b"jpeg"


class Meta:
    def __init__(self, answer=None, fail=False):
        self.answer, self.fail, self.calls = answer, fail, 0

    def structured(self, model, prompt, content, schema, **kw):
        self.calls += 1
        if self.fail:
            raise TimeoutError("host down")
        return {"data": self.answer}


class Case:
    record = {"desc": "Construction of river wall"}

    def __init__(self, meta):
        self.meta, self.entries = meta, []

    def record_entry(self, agent, kind, payload):
        self.entries.append((kind, payload))
        return f"h{len(self.entries)}"


def frames():
    return [{"captured": "2020-01-30", "window": "before_award", "chip": Chip()},
            {"captured": "2025-04-07", "window": "after_completion", "chip": Chip()}]


def test_agreement_keeps_the_claim():
    for claim, said in (("present", "yes"), ("present", "partly"), ("absent", "no")):
        c, why, q = confirm(claim, "reading", 0.9, {"structure": said, "what_i_see": "", "model": "B"}, None, "A")
        assert (c, q) == (claim, 0.9) and why.endswith("B agrees")


def test_contradiction_cannot_tell_and_no_reading_all_leave_it_inconclusive():
    cases = [({"structure": "no", "what_i_see": "bare bank", "model": "B"}, None, "readers disagree"),
             ({"structure": "cannot tell", "what_i_see": "haze", "model": "B"}, None, "B cannot tell"),
             (None, "the second reading failed (TimeoutError)", "failed"),
             (None, "no second reader is configured", "no second reader")]
    for x, missing, said in cases:
        c, why, q = confirm("present", "reading", 0.9, x, missing, "A")
        assert (c, q) == ("inconclusive", 0.0) and said in why


def test_a_failed_second_reading_is_sealed_and_explained():
    case = Case(Meta(fail=True))
    fr = frames()
    cross, missing = cross_read(case, "open", fr, fr, reach=None)
    assert cross == {}
    assert set(missing) == {"2020-01-30", "2025-04-07"}
    assert [k for k, _ in case.entries] == ["cross_reading_failed", "cross_reading_failed"]


def test_without_a_second_reader_nothing_is_called_and_every_claim_is_unconfirmed():
    meta = Meta({"structure": "yes", "what_i_see": ""})
    fr = frames()
    cross, missing = cross_read(Case(meta), None, fr, fr, reach=None)
    assert (cross, meta.calls) == ({}, 0)
    assert all(m == "no second reader is configured" for m in missing.values())


def test_the_capture_after_an_earlier_one_is_read_beside_it():
    case = Case(Meta({"structure": "yes", "what_i_see": "wall"}))
    fr = frames()
    cross, missing = cross_read(case, "open", fr, fr, reach=None)
    assert missing == {}
    assert cross["2020-01-30"]["reference"] is None and cross["2025-04-07"]["reference"] == "2020-01-30"


def test_an_unconfirmed_reading_cannot_carry_a_verdict():
    """A first reading that sees the wall after completion, with a second reader that cannot tell: not 'exists'."""
    c, why, q = confirm("present", "reading: structure along 90% of the reach", 0.9,
                        {"structure": "cannot tell", "what_i_see": "haze", "model": "B"}, None, "A")
    f = Finding("existence", "Wayback 2025-04-07", "optical_vhr", "maxar", "2025-04-07", c, q, note=why)
    v = decide([f], award="2024-02-01", completion="2024-08-01", length_m=200, located=True)
    assert (v.outcome, v.reason) == ("cant_verify", "NO_DECISIVE_OBSERVATION")
