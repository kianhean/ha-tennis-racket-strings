"""Statistics over a racket's restring history: string life, breakages, costs.

Pure functions over the stored records (sorted oldest first), so sensors,
get_history and diagnostics all report the same numbers.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .const import (
    ATTR_BROKEN_DATE,
    ATTR_COST,
    ATTR_CROSS_STRING,
    ATTR_CROSS_TENSION,
    ATTR_DATE,
    ATTR_MAIN_STRING,
    ATTR_MAIN_TENSION,
    ATTR_NOTES,
    ATTR_RATING,
    CONF_BRAND,
    CONF_MODEL,
    CONF_TENSION_UNIT,
    TENSION_UNIT_LBS,
)
from .due import Due
from .tension import (
    CONF_SESSION_HOURS,
    DEFAULT_SESSION_HOURS,
    TRACKING_LOGGED,
    Estimate,
    PlaySettings,
    estimate,
    hours_played,
)


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


@dataclass(frozen=True)
class RacketSnapshot:
    """Inputs for cross-racket bag analytics and readiness ranking."""

    entry_id: str
    name: str
    options: Mapping[str, Any]
    restrings: list[dict[str, Any]]
    sessions: list[dict[str, Any]]
    play_settings: PlaySettings | None
    due: Due | None
    image_url: str | None = None


def freshness_score(
    latest: dict[str, Any] | None,
    est: Estimate | None,
    due: Due | None,
    today: date,
) -> int | None:
    """0-100% stringbed freshness from tension loss, due rules, or string age."""
    if latest is None:
        return None
    if latest.get(ATTR_BROKEN_DATE):
        return 0
    strung = _date(latest.get(ATTR_DATE))
    scores: list[float] = []
    if est is not None:
        # 0% loss -> 100, 15% loss -> 70 (match ready), 50% cap -> 0
        scores.append(max(0.0, min(100.0, 100.0 - est.loss_percent * 2.0)))
    if due is not None and strung is not None:
        total = max((due.date - strung).days, 1)
        left = (due.date - today).days
        scores.append(max(0.0, min(100.0, 100.0 * left / total)))
    if not scores and strung is not None:
        age = max((today - strung).days, 0)
        scores.append(max(0.0, min(100.0, 100.0 * (1.0 - age / 90.0))))
    return round(min(scores)) if scores else 100


def _racket_status(
    latest: dict[str, Any] | None,
    due: Due | None,
    freshness: int | None,
    today: date,
) -> str:
    if latest is None:
        return "unstrung"
    if latest.get(ATTR_BROKEN_DATE):
        return "broken"
    if due is not None and due.date <= today:
        return "due"
    if freshness is not None and freshness >= 70:
        return "ready"
    return "practice"


def setup_comparison(
    rackets: list[RacketSnapshot], today: date
) -> list[dict[str, Any]]:
    """Compare string setups across every racket in the bag."""
    grouped: dict[str, dict[str, Any]] = {}

    for snap in rackets:
        records = snap.restrings
        settings = snap.play_settings
        lives_by_id = {life.record["id"]: life for life in string_lives(records)}

        for record in records:
            label = strings_label(record)
            if not label:
                continue
            bucket = grouped.setdefault(
                label,
                {
                    "setup": label,
                    "jobs": 0,
                    "ratings": [],
                    "life_days": [],
                    "life_hours": [],
                    "breakages": 0,
                    "finished": 0,
                    "total_cost": 0.0,
                    "total_hours": 0.0,
                },
            )
            bucket["jobs"] += 1
            if record.get(ATTR_RATING):
                bucket["ratings"].append(int(record[ATTR_RATING]))
            if record.get(ATTR_COST) is not None:
                bucket["total_cost"] += float(record[ATTR_COST])

            life = lives_by_id.get(record["id"])
            if life is not None:
                bucket["finished"] += 1
                bucket["life_days"].append(life.days)
                if life.broken:
                    bucket["breakages"] += 1
                if settings is not None:
                    start = date.fromisoformat(record[ATTR_DATE])
                    end = start + timedelta(days=life.days)
                    if settings.tracking == TRACKING_LOGGED:
                        hrs = sum(
                            h
                            for d, h in settings.sessions
                            if start <= d < end
                            or (d == end and (life.broken or d == start))
                        )
                    else:
                        hrs = hours_played(settings, start, end)
                    bucket["life_hours"].append(hrs)
                    bucket["total_hours"] += hrs
            elif settings is not None and (rec_start := _date(record.get(ATTR_DATE))):
                bucket["total_hours"] += hours_played(settings, rec_start, today)

    rows: list[dict[str, Any]] = []
    for bucket in grouped.values():
        ratings: list[int] = bucket["ratings"]
        finished: int = bucket["finished"]
        total_hours: float = bucket["total_hours"]
        total_cost: float = bucket["total_cost"]
        rows.append(
            {
                "setup": bucket["setup"],
                "jobs": bucket["jobs"],
                "average_rating": (
                    round(sum(ratings) / len(ratings), 2) if ratings else None
                ),
                "ratings": len(ratings),
                "average_life_days": _average(bucket["life_days"]),
                "average_life_hours": _average(bucket["life_hours"]),
                "breakages": bucket["breakages"],
                "breakage_rate": (
                    round(100 * bucket["breakages"] / finished, 1) if finished else None
                ),
                "cost_per_hour": (
                    round(total_cost / total_hours, 2)
                    if total_hours > 0 and total_cost > 0
                    else None
                ),
            }
        )

    rows.sort(
        key=lambda r: (
            r["average_rating"] if r["average_rating"] is not None else -1.0,
            r["jobs"],
            r["setup"].lower(),
        ),
        reverse=True,
    )
    return rows


def bag_summary(rackets: list[RacketSnapshot], today: date) -> dict[str, Any]:
    """Cross-racket readiness ranking, bag KPIs and string setup showdown."""
    since_30d = today - timedelta(days=30)
    racket_rows: list[dict[str, Any]] = []
    restrings_total = 0
    restrings_year = 0
    cost_year = 0.0
    total_cost = 0.0
    total_hours_all = 0.0
    hours_30d = 0.0
    ready_count = 0
    due_count = 0

    for snap in rackets:
        latest = snap.restrings[-1] if snap.restrings else None
        est = (
            estimate(latest, snap.play_settings, today)
            if latest and snap.play_settings is not None
            else None
        )
        fresh = freshness_score(latest, est, snap.due, today)
        status = _racket_status(latest, snap.due, fresh, today)
        if status == "ready":
            ready_count += 1
        elif status in ("due", "broken"):
            due_count += 1

        restrings_total += len(snap.restrings)
        restrings_year += restrings_in_year(snap.restrings, today.year)
        cost_year += cost_in_year(snap.restrings, today.year)
        r_cost = round(sum(r.get(ATTR_COST) or 0 for r in snap.restrings), 2)
        total_cost += r_cost

        if snap.play_settings is not None:
            total_hours_all += hours_played_total(
                snap.restrings, snap.play_settings, today
            )
            hours_30d += hours_played(snap.play_settings, since_30d, today)

        strung = _date(latest.get(ATTR_DATE)) if latest else None
        days_since = (today - strung).days if strung else None
        play_opt = snap.options.get("play") or {}

        racket_rows.append(
            {
                "config_entry_id": snap.entry_id,
                "name": snap.name,
                "brand": snap.options.get(CONF_BRAND),
                "model": snap.options.get(CONF_MODEL),
                "tension_unit": snap.options.get(CONF_TENSION_UNIT, TENSION_UNIT_LBS),
                "strings": strings_label(latest) if latest else None,
                "main_tension": latest.get(ATTR_MAIN_TENSION) if latest else None,
                "cross_tension": latest.get(ATTR_CROSS_TENSION) if latest else None,
                "last_restrung": latest.get(ATTR_DATE) if latest else None,
                "days_since": days_since,
                "estimated_tension": est.main_tension if est else None,
                "estimated_tension_loss": est.loss_percent if est else None,
                "hours_played": est.hours_played if est else None,
                "tracking": snap.play_settings.tracking if snap.play_settings else None,
                "session_hours": play_opt.get(
                    CONF_SESSION_HOURS, DEFAULT_SESSION_HOURS
                ),
                "due": snap.due is not None and snap.due.date <= today,
                "due_date": snap.due.date.isoformat() if snap.due else None,
                "days_until_due": ((snap.due.date - today).days if snap.due else None),
                "due_reason": snap.due.reason if snap.due else None,
                "freshness": fresh,
                "status": status,
                "rating": latest.get(ATTR_RATING) if latest else None,
                "notes": latest.get(ATTR_NOTES) if latest else None,
                "broken_date": latest.get(ATTR_BROKEN_DATE) if latest else None,
                "image_url": snap.image_url,
                "restring_count": len(snap.restrings),
                "total_cost": r_cost,
            }
        )

    # Sort: highest freshness first, due/broken/unstrung last
    status_order = {"ready": 0, "practice": 1, "due": 2, "broken": 3, "unstrung": 4}
    racket_rows.sort(
        key=lambda r: (
            status_order.get(r["status"], 9),
            -(r["freshness"] if r["freshness"] is not None else -1),
            r["name"].lower(),
        )
    )

    return {
        "totals": {
            "racket_count": len(rackets),
            "ready_count": ready_count,
            "due_count": due_count,
            "restrings_total": restrings_total,
            "restrings_this_year": restrings_year,
            "cost_this_year": round(cost_year, 2),
            "total_cost": round(total_cost, 2),
            "hours_last_30d": round(hours_30d, 1),
            "cost_per_hour": (
                round(total_cost / total_hours_all, 2)
                if total_hours_all > 0 and total_cost > 0
                else None
            ),
        },
        "rackets": racket_rows,
        "setups": setup_comparison(rackets, today),
    }
