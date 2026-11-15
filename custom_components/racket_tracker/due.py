"""When the current strings are due to be replaced.

A racket can have up to three rules (options["due"]); the earliest one wins:

- ``days``: restring after this many days.
- ``hours_played``: restring after this many hours of play (needs hours per week).
- ``min_tension``: restring when the estimated tension of the mains drops to this
  (needs hours per week; uses the same model as the estimated tension sensor).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .const import ATTR_DATE, ATTR_MAIN_TENSION
from .tension import MAX_LOSS, PlaySettings, play_settings

CONF_DUE = "due"
CONF_DUE_DAYS = "days"
CONF_DUE_HOURS = "hours_played"
CONF_DUE_TENSION = "min_tension"

# Rules that need hours of play per week
PLAY_RULES = (CONF_DUE_HOURS, CONF_DUE_TENSION)


@dataclass(frozen=True)
class Due:
    """When the current strings are due, and which rule decided it."""

    date: date
    reason: str


def due_rules(options: Mapping[str, Any]) -> dict[str, float]:
    """The racket's restring rules that are set."""
    return {k: v for k, v in (options.get(CONF_DUE) or {}).items() if v is not None}


def _days_for_hours(hours: float, settings: PlaySettings) -> int | None:
    if settings.hours_per_week <= 0:
        return None
    return max(math.ceil(round(hours * 7 / settings.hours_per_week, 6)), 0)


def _days_for_tension(
    strung: Any, minimum: float, settings: PlaySettings
) -> int | None:
    if not isinstance(strung, (int, float)) or isinstance(strung, bool) or strung <= 0:
        return None
    needed_loss = (1 - minimum / strung) * 100
    if needed_loss <= settings.initial_loss:
        return 0
    if needed_loss > MAX_LOSS or settings.loss_per_hour <= 0:
        return None  # The estimate never gets that low
    return _days_for_hours(
        (needed_loss - settings.initial_loss) / settings.loss_per_hour, settings
    )


def next_due(record: dict[str, Any] | None, options: Mapping[str, Any]) -> Due | None:
    """When the given restring is due, or None (no restring, no rules, never)."""
    if not record or not record.get(ATTR_DATE):
        return None
    rules = due_rules(options)
    settings = play_settings(options)
    candidates: list[tuple[int, str]] = []
    if (days := rules.get(CONF_DUE_DAYS)) is not None:
        candidates.append((int(days), CONF_DUE_DAYS))
    if settings is not None:
        if (hours := rules.get(CONF_DUE_HOURS)) is not None and (
            d := _days_for_hours(float(hours), settings)
        ) is not None:
            candidates.append((d, CONF_DUE_HOURS))
        if (minimum := rules.get(CONF_DUE_TENSION)) is not None and (
            d := _days_for_tension(
                record.get(ATTR_MAIN_TENSION), float(minimum), settings
            )
        ) is not None:
            candidates.append((d, CONF_DUE_TENSION))
    if not candidates:
        return None
    days, reason = min(candidates)
    return Due(date.fromisoformat(record[ATTR_DATE]) + timedelta(days=days), reason)
