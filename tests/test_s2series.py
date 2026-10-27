"""Dating a bank's change from 10 m NDVI: season against season, bank by bank."""
from atlas.geo.s2series import disturbance_any_bank, first_change, first_change_any_bank


def series(fn, years=range(2020, 2027)):
    """One scene a month; fn(year, month) -> (ndvi_left, ndvi_right)."""
    rows = []
    for y in years:
        for m in range(1, 13):
            if y == 2026 and m > 10:
                break
            left, right = fn(y, m)
            rows.append({"date": f"{y}-{m:02d}-15", "ndvi": round((left + right) / 2, 3), "ndvi_l": left, "ndvi_r": right,
                         "bright": 0.05})
    return rows


def monsoon(m: int) -> float:
    return 0.72 if 6 <= m <= 11 else 0.55  # greener in the wet season


def test_the_monsoon_alone_is_not_a_change():
    rows = series(lambda y, m: (monsoon(m), monsoon(m)))
    assert first_change_any_bank(rows) is None
    assert disturbance_any_bank(rows) is None


def test_a_lasting_drop_is_dated_to_its_season():
    rows = series(lambda y, m: (monsoon(m) - (0.3 if (y, m) >= (2023, 6) else 0), monsoon(m)))
    fc = first_change_any_bank(rows)
    assert fc is not None and fc["season"] == "2023-2wet"
    assert fc["date"] == "2023-06-15" and fc["last"] == "2023-11-15"


def test_a_wall_on_one_bank_is_found_on_that_bank():
    rows = series(lambda y, m: (monsoon(m), monsoon(m) - (0.25 if (y, m) >= (2023, 6) else 0)))
    assert first_change(rows, field="ndvi") is None  # diluted by the far bank on the median over both
    fc = first_change_any_bank(rows)
    assert fc is not None and fc["bank"] == "right bank"


def test_a_dip_that_regrows_is_a_disturbance_not_a_change():
    rows = series(lambda y, m: (monsoon(m) - (0.3 if (2024, 12) <= (y, m) <= (2025, 5) else 0), monsoon(m)))
    assert first_change_any_bank(rows) is None
    d = disturbance_any_bank(rows, after="2024-06-01")
    assert d is not None and d["season"] == "2025-1dry"
