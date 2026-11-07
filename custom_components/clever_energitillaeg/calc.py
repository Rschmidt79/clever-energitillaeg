"""Month-to-date national average and preliminary Clever energy surcharge rate.

Pure functions so the calculation can be tested against Clever's published rates.
"""

from __future__ import annotations

import calendar
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from .const import DK_TZ, PRICE_AREAS


@dataclass
class MonthResult:
    """Calculation for one Danish calendar month."""

    month: str
    days_in_month: int
    included_days: list[str] = field(default_factory=list)
    missing_days: list[str] = field(default_factory=list)
    pending_days: int = 0
    intervals: dict[str, int] = field(default_factory=dict)
    average: dict[str, float] = field(default_factory=dict)  # kr./kWh incl. VAT per area
    national_average: float | None = None
    raw_rate: float | None = None
    rate: float | None = None
    includes_future_days: bool = False
    # Per included day: the day's national average, month-to-date average and rate after that day.
    days: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MonthResult:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


def month_of(moment: datetime) -> str:
    return moment.astimezone(DK_TZ).strftime("%Y-%m")


def previous_month(month: str) -> str:
    year, mon = map(int, month.split("-"))
    return f"{year - (mon == 1)}-{(mon - 2) % 12 + 1:02d}"


def next_month(month: str) -> str:
    year, mon = map(int, month.split("-"))
    return f"{year + mon // 12}-{mon % 12 + 1:02d}"


def expected_intervals(day: date) -> int:
    """15-minute intervals in a Danish day: 96, or 92/100 on DST changes."""
    start = datetime(day.year, day.month, day.day, tzinfo=DK_TZ)
    nxt = day + timedelta(days=1)
    end = datetime(nxt.year, nxt.month, nxt.day, tzinfo=DK_TZ)
    return round((end.timestamp() - start.timestamp()) / 900)


def calculate(
    records: list[dict[str, Any]],
    month: str,
    today: date,
    threshold: float,
    vat_percent: float,
) -> MonthResult:
    """Only days where every area has exactly the expected intervals are included."""
    year, mon = map(int, month.split("-"))
    dim = calendar.monthrange(year, mon)[1]
    sums: dict[tuple[str, str], list[float]] = {}
    for rec in records:
        area, when, price = rec.get("PriceArea"), rec.get("TimeDK"), rec.get("DayAheadPriceDKK")
        if area not in PRICE_AREAS or not isinstance(when, str) or when[:7] != month:
            continue
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            continue
        acc = sums.setdefault((when[:10], area), [0, 0.0])
        acc[0] += 1
        acc[1] += price

    result = MonthResult(month=month, days_in_month=dim)
    totals = {area: [0, 0.0] for area in PRICE_AREAS}
    factor = (1 + vat_percent / 100) / 1000  # DKK/MWh -> kr./kWh incl. VAT
    for dom in range(1, dim + 1):
        day = date(year, mon, dom)
        key = day.isoformat()
        want = expected_intervals(day)
        counts = [sums.get((key, area), [0, 0.0]) for area in PRICE_AREAS]
        if all(c[0] == want for c in counts):
            result.included_days.append(key)
            for area, c in zip(PRICE_AREAS, counts, strict=True):
                totals[area][0] += c[0]
                totals[area][1] += c[1]
            day_avg = sum(c[1] / c[0] for c in counts) / len(counts) * factor
            to_date = sum(t[1] / t[0] for t in totals.values()) / len(totals) * factor
            result.days.append(
                {
                    "dato": key,
                    "dagsgennemsnit": round(day_avg, 4),
                    "maanedsgennemsnit": round(to_date, 4),
                    "sats": round(max(0.0, to_date - threshold), 2),
                }
            )
        elif day <= today:
            result.missing_days.append(key)
        else:
            result.pending_days += 1

    result.intervals = {area: totals[area][0] for area in PRICE_AREAS}
    if not result.included_days:
        return result
    avg = {area: totals[area][1] / totals[area][0] * factor for area in PRICE_AREAS}
    national = sum(avg.values()) / len(avg)
    raw = national - threshold
    result.average = {area: round(v, 4) for area, v in avg.items()}
    result.national_average = round(national, 4)
    result.raw_rate = round(raw, 4)
    result.rate = round(max(0.0, raw), 2)
    result.includes_future_days = result.included_days[-1] > today.isoformat()
    return result
