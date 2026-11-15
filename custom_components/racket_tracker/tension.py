"""Estimate how much tension the current strings have lost.

Strings drop tension in two ways: a static loss in the first day after stringing,
whether you play or not, and a steady loss while you play. The model is kept
simple and transparent so users can tune it per racket:

    hours played  = hours per week × days since the restring ÷ 7
    loss %        = initial loss + loss per hour × hours played   (capped at 50 %)
    tension       = strung tension × (1 − loss %)

Defaults (10 % initial, 1 % per hour) are typical of polyester; multifilament
and gut hold tension better, so lower them for those.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .const import ATTR_CROSS_TENSION, ATTR_DATE, ATTR_MAIN_TENSION

CONF_PLAY = "play"
CONF_HOURS_PER_WEEK = "hours_per_week"
CONF_INITIAL_LOSS = "initial_tension_loss"
CONF_LOSS_PER_HOUR = "tension_loss_per_hour"

DEFAULT_INITIAL_LOSS = 10.0
DEFAULT_LOSS_PER_HOUR = 1.0
MAX_LOSS = 50.0


@dataclass(frozen=True)
class PlaySettings:
    """How much a racket is played and how fast its strings lose tension."""

    hours_per_week: float
    initial_loss: float
    loss_per_hour: float


@dataclass(frozen=True)
class Estimate:
    """Estimated state of the current strings."""

    hours_played: float
    loss_percent: float
    main_tension: float | None
    cross_tension: float | None


def play_settings(options: dict[str, Any]) -> PlaySettings | None:
    """The racket's play settings, or None if hours per week isn't set."""
    play = options.get(CONF_PLAY) or {}
    hours = play.get(CONF_HOURS_PER_WEEK)
    if hours is None:
        return None
    initial = play.get(CONF_INITIAL_LOSS)
    per_hour = play.get(CONF_LOSS_PER_HOUR)
    return PlaySettings(
        hours_per_week=float(hours),
        initial_loss=DEFAULT_INITIAL_LOSS if initial is None else float(initial),
        loss_per_hour=DEFAULT_LOSS_PER_HOUR if per_hour is None else float(per_hour),
    )


def _reduce(tension: Any, loss_percent: float) -> float | None:
    if not isinstance(tension, (int, float)) or isinstance(tension, bool):
        return None
    return round(tension * (1 - loss_percent / 100), 1)


def estimate(
    record: dict[str, Any] | None, settings: PlaySettings, today: date
) -> Estimate | None:
    """Estimate for the given restring as of today, or None without a restring."""
    if not record or not record.get(ATTR_DATE):
        return None
    days = max((today - date.fromisoformat(record[ATTR_DATE])).days, 0)
    hours = settings.hours_per_week * days / 7
    loss = min(settings.initial_loss + settings.loss_per_hour * hours, MAX_LOSS)
    loss = round(loss, 1)
    return Estimate(
        hours_played=round(hours, 1),
        loss_percent=loss,
        main_tension=_reduce(record.get(ATTR_MAIN_TENSION), loss),
        cross_tension=_reduce(record.get(ATTR_CROSS_TENSION), loss),
    )
