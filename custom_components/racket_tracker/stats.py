"""Statistics over a racket's restring history: string life, breakages, costs.

Pure functions over the stored records (sorted oldest first), so sensors,
get_history and diagnostics all report the same numbers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .const import (
    ATTR_BROKEN_DATE,
    ATTR_COST,
    ATTR_CROSS_STRING,
    ATTR_DATE,
    ATTR_MAIN_STRING,
    ATTR_RATING,
)
from .tension import TRACKING_LOGGED, PlaySettings, hours_played


@dataclass(frozen=True)
class StringLife:
    """How long one string bed lasted."""

    record: dict[str, Any]
    days: int
    broken: bool


def strings_label(record: dict[str, Any]) -> str | None:
    """ "Main" or "Main / Cross" for a hybrid."""
    main = record.get(ATTR_MAIN_STRING)
    if not main:
        return None
    cross = record.get(ATTR_CROSS_STRING)
    return main if not cross or cross == main else f"{main} / {cross}"


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def string_lives(records: list[dict[str, Any]]) -> list[StringLife]:
    """String beds that are finished: replaced by the next restring, or broken.

    A bed ends on the day it broke, else on the next restring's date. The
    current bed counts only once it has broken.
    """
    lives = []
    for i, record in enumerate(records):
        if (start := _date(record.get(ATTR_DATE))) is None:
            continue
        broken = _date(record.get(ATTR_BROKEN_DATE))
        end = broken
        if end is None and i + 1 < len(records):
            end = _date(records[i + 1].get(ATTR_DATE))
        if end is None:
            continue
        lives.append(StringLife(record, max((end - start).days, 0), broken is not None))
    return lives


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def average_life_days(records: list[dict[str, Any]]) -> float | None:
    """Average days a finished string bed lasted."""
    return _average([life.days for life in string_lives(records)])


def average_days_to_break(records: list[dict[str, Any]]) -> float | None:
    """Average days until the strings broke, over the beds that broke."""
    return _average([life.days for life in string_lives(records) if life.broken])


def breakages(records: list[dict[str, Any]]) -> int:
    """How many string beds broke."""
    return sum(1 for r in records if _date(r.get(ATTR_BROKEN_DATE)))


def breakage_rate(records: list[dict[str, Any]]) -> float | None:
    """Share of finished string beds that broke, in %."""
    if not (lives := string_lives(records)):
        return None
    return round(100 * sum(life.broken for life in lives) / len(lives), 1)


def last_broken(records: list[dict[str, Any]]) -> str | None:
    """Most recent date strings broke."""
    dates = [d for r in records if (d := r.get(ATTR_BROKEN_DATE))]
    return max(dates) if dates else None


def cost_in_year(records: list[dict[str, Any]], year: int) -> float:
    """Spent on restrings dated in the given year."""
    return round(
        sum(
            r.get(ATTR_COST) or 0
            for r in records
            if (d := _date(r.get(ATTR_DATE))) and d.year == year
        ),
        2,
    )


def restrings_in_year(records: list[dict[str, Any]], year: int) -> int:
    """Restrings dated in the given year."""
    return sum(1 for r in records if (d := _date(r.get(ATTR_DATE))) and d.year == year)


def hours_played_total(
    records: list[dict[str, Any]], settings: PlaySettings, today: date
) -> float:
    """Hours played (estimated or logged) since the first restring."""
    if not records or (first := _date(records[0].get(ATTR_DATE))) is None:
        return 0.0
    return hours_played(settings, first, today)


def average_life_hours(
    records: list[dict[str, Any]], settings: PlaySettings
) -> float | None:
    """Average hours a finished string bed was played (estimated or logged).

    A session on the day of the next restring counts for the new strings; one
    on the day the strings broke, for the broken ones.
    """
    hours = []
    for life in string_lives(records):
        start = date.fromisoformat(life.record[ATTR_DATE])
        end = start + timedelta(days=life.days)
        if settings.tracking == TRACKING_LOGGED:
            hours.append(
                sum(
                    h
                    for d, h in settings.sessions
                    if start <= d < end or (d == end and (life.broken or d == start))
                )
            )
        else:
            hours.append(hours_played(settings, start, end))
    return _average(hours)


def cost_per_hour(
    records: list[dict[str, Any]], settings: PlaySettings, today: date
) -> float | None:
    """Restring spend per estimated hour of play since the first restring."""
    hours = hours_played_total(records, settings, today)
    total = float(sum(r.get(ATTR_COST) or 0 for r in records))
    if hours <= 0 or not total:
        return None
    return round(total / hours, 2)


def string_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    """How often each string setup was used, most used first."""
    counts = Counter(label for r in records if (label := strings_label(r)))
    return dict(counts.most_common())


def most_used_string(records: list[dict[str, Any]]) -> tuple[str, int] | None:
    """The string setup used most often; on a tie, the one used most recently."""
    counts = string_counts(records)
    if not counts:
        return None
    top = max(counts.values())
    for record in reversed(records):
        if (label := strings_label(record)) and counts[label] == top:
            return label, top
    return None  # pragma: no cover


def best_rated_string(records: list[dict[str, Any]]) -> tuple[str, float, int] | None:
    """Setup with the best average rating: (label, average, ratings).

    On a tie, the one rated more often, then the most recent.
    """
    ratings: dict[str, list[int]] = {}
    for record in records:
        if (label := strings_label(record)) and record.get(ATTR_RATING):
            ratings.setdefault(label, []).append(record[ATTR_RATING])
    if not ratings:
        return None
    order = {label: i for i, r in enumerate(records) if (label := strings_label(r))}
    label = max(
        ratings,
        key=lambda k: (sum(ratings[k]) / len(ratings[k]), len(ratings[k]), order[k]),
    )
    values = ratings[label]
    return label, round(sum(values) / len(values), 2), len(values)


def summary(
    records: list[dict[str, Any]], settings: PlaySettings | None, today: date
) -> dict[str, Any]:
    """All the statistics, for get_history and diagnostics."""
    most = most_used_string(records)
    best = best_rated_string(records)
    out: dict[str, Any] = {
        "average_string_life_days": average_life_days(records),
        "average_days_to_break": average_days_to_break(records),
        "breakages": breakages(records),
        "breakage_rate": breakage_rate(records),
        "last_broken": last_broken(records),
        "cost_this_year": cost_in_year(records, today.year),
        "restrings_this_year": restrings_in_year(records, today.year),
        "most_used_string": most[0] if most else None,
        "best_rated_string": best[0] if best else None,
        "best_rating": best[1] if best else None,
        "string_counts": string_counts(records),
    }
    if settings is not None:
        out["cost_per_hour"] = cost_per_hour(records, settings, today)
        out["average_string_life_hours"] = average_life_hours(records, settings)
    return out
