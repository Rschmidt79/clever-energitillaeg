"""The calculation against Clever's published rates (clever.dk, read 2026-11-06)."""

from datetime import date
from statistics import fmean

import pytest

from custom_components.clever_energitillaeg.calc import calculate, expected_intervals, next_month

from .conftest import month_records

CLEVER = {
    "2025-10": 0.00,
    "2025-11": 0.00,
    "2025-12": 0.00,
    "2026-01": 0.12,
    "2026-02": 0.09,
    "2026-03": 0.02,
    "2026-04": 0.00,
    "2026-05": 0.04,
    "2026-06": 0.13,
    "2026-07": 0.07,
    "2026-08": 0.29,
    "2026-09": 0.44,
    "2026-10": 0.62,
}


def end_of(month: str) -> date:
    y, m = map(int, next_month(month).split("-"))
    return date.fromordinal(date(y, m, 1).toordinal() - 1)


@pytest.mark.parametrize("month", list(CLEVER))
def test_completed_months_equal_clever(month):
    recs = month_records(month)
    res = calculate(recs, month, end_of(month), 0.89, 25.0)
    assert res.rate == CLEVER[month]
    assert len(res.included_days) == res.days_in_month and not res.missing_days
    ref = [
        fmean(r["DayAheadPriceDKK"] for r in recs if r["PriceArea"] == a) * 1.25 / 1000
        for a in ("DK1", "DK2")
    ]
    assert res.raw_rate == pytest.approx((ref[0] + ref[1]) / 2 - 0.89, abs=6e-5)


@pytest.mark.parametrize(
    "day,n",
    [
        (date(2025, 10, 26), 100),
        (date(2026, 3, 29), 92),
        (date(2026, 10, 25), 100),
        (date(2026, 10, 24), 96),
    ],
)
def test_dst_intervals(day, n):
    assert expected_intervals(day) == n
    res = calculate(month_records(day.strftime("%Y-%m")), day.strftime("%Y-%m"), day, 0.89, 25)
    assert day.isoformat() in res.included_days


def test_one_area_only_is_no_data():
    """Both areas are required; a missing area is never treated as 0."""
    recs = month_records("2026-02")
    dk1 = calculate(
        [r for r in recs if r["PriceArea"] == "DK1"], "2026-02", date(2026, 2, 28), 0.89, 25
    )
    assert dk1.rate is None  # DK2 missing -> no complete day, never 0


def test_incomplete_null_and_duplicate_days_excluded():
    recs = month_records("2026-11")
    recs = [
        r for r in recs if not (r["TimeDK"] == "2026-11-03T10:15:00" and r["PriceArea"] == "DK2")
    ]
    for r in recs:
        if r["TimeDK"] == "2026-11-02T08:00:00" and r["PriceArea"] == "DK1":
            r["DayAheadPriceDKK"] = None
    recs.append(dict(next(r for r in recs if r["TimeDK"] == "2026-11-04T08:00:00")))
    res = calculate(recs, "2026-11", date(2026, 11, 6), 0.89, 25)
    assert res.missing_days == ["2026-11-02", "2026-11-03", "2026-11-04"]
    assert res.included_days == ["2026-11-01", "2026-11-05", "2026-11-06", "2026-11-07"]
    assert res.pending_days == 23 and res.includes_future_days
    assert res.intervals == {"DK1": 4 * 96, "DK2": 4 * 96}


def test_negative_prices_unfloored_rate_never_negative():
    recs = [dict(r, DayAheadPriceDKK=-100.0) for r in month_records("2026-11")]
    res = calculate(recs, "2026-11", date(2026, 11, 6), 0.89, 25)
    assert res.raw_rate == pytest.approx(-0.125 - 0.89, abs=1e-4) and res.rate == 0.0


def test_other_month_and_area_ignored_and_options_used():
    recs = month_records("2026-10") + [
        {"TimeDK": "2026-10-01T00:00:00", "PriceArea": "SE4", "DayAheadPriceDKK": 1e9}
    ]
    base = calculate(recs, "2026-10", date(2026, 10, 31), 0.89, 25)
    assert base.rate == 0.62
    assert calculate(recs, "2026-10", date(2026, 10, 31), 1.0, 25).rate == round(
        base.raw_rate + 0.89 - 1.0, 2
    )
    no_vat = calculate(recs, "2026-10", date(2026, 10, 31), 0.89, 0)
    assert no_vat.national_average == pytest.approx(base.national_average / 1.25, abs=1e-4)
    assert calculate(month_records("2026-11"), "2026-10", date(2026, 10, 31), 0.89, 25).rate is None


def test_daily_series_matches_reference_and_dst():
    recs = month_records("2026-10")
    res = calculate(recs, "2026-10", date(2026, 10, 31), 0.89, 25)
    assert len(res.days) == 31
    dst = next(d for d in res.days if d["dato"] == "2026-10-25")
    ref = [
        fmean(
            r["DayAheadPriceDKK"]
            for r in recs
            if r["PriceArea"] == a and r["TimeDK"][:10] == "2026-10-25"
        )
        * 1.25
        / 1000
        for a in ("DK1", "DK2")
    ]
    assert dst["dagsgennemsnit"] == pytest.approx(sum(ref) / 2, abs=6e-5)
    assert res.days[-1]["maanedsgennemsnit"] == res.national_average
    assert res.days[-1]["sats"] == res.rate == 0.62


def test_daily_series_skips_missing_day():
    recs = [r for r in month_records("2026-11") if r["TimeDK"][:10] != "2026-11-03"]
    res = calculate(recs, "2026-11", date(2026, 11, 6), 0.89, 25)
    assert [d["dato"] for d in res.days] == [
        "2026-11-01",
        "2026-11-02",
        "2026-11-04",
        "2026-11-05",
        "2026-11-06",
        "2026-11-07",
    ]


def test_previous_month():
    from custom_components.clever_energitillaeg.calc import previous_month

    assert previous_month("2026-01") == "2025-12" and previous_month("2026-11") == "2026-10"
