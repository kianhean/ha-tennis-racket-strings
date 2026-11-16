"""Estimate how much tension the current strings have lost.

Strings lose tension in three ways, and the model adds them up (as % of the
strung tension, capped at 50 %):

    loss = initial                                   first day after stringing
         + relaxation × log10(days since stringing)  from day 1, played or not
         + first hour × log2(1 + hours played)        from play
    hours played = hours per week × days ÷ 7

Where the shape and the numbers come from:

- Stress relaxation is linear in log(time), indefinitely, so the loss from
  sitting still grows by the same amount each time the age multiplies by 10.
  Cross, Lindsey & Andruczyk, "Laboratory testing of tennis strings", Sports
  Engineering 3 (2000) 219-230: "a plot of tension vs. log(time) is linear
  after the first 100 s, even over a period of several days".
  Cross & Bower, "Measurements of string tension in a tennis racket", Sports
  Engineering 4 (2001) 165-175: 28 kg -> 24.8 kg after 1000 s, 21.9 kg after
  72 h, 19.1 kg extrapolated to a year. That is ~4.3 % of the strung tension
  per tenfold time, which is the polyester default here.
- Play loss is front-loaded: "successive impacts result in successively
  smaller drops in tension" and about half of the drop over ten impacts came
  on the first (Cross & Bower 2001). After "one or two sets, the tension will
  drop a further one or two kg" from about 20 kg (Cross et al. 2000), i.e.
  ~3.5-7 % of the strung tension. A logarithm of hours gives that shape; the
  polyester default costs 3 % in the first hour and 3 % more for each doubling
  of (1 + hours), so ~9.5 % after 8 hours.
- Without a string type set for the racket, the main string's material comes
  from the bundled string catalog (string_catalog.py), else polyester.
- Materials: "Natural gut has one of the lowest rates of tension loss ...
  while all polyester strings lose tension rapidly" (Cross et al. 2000);
  "Polyester loses more than nylon which loses more than gut" (Lindsey, "How
  Tennis Strings Go Dead - Part 1", Tennis Warehouse University, 2013). The
  nylon and gut presets scale the polyester one by roughly the ratio of the
  median losses in TWU's string database (polyester 41 %, nylon 21 %,
  gut 15 %).
- A string's own measured tension loss can replace the median: TWU's String
  Performance Database (twu.tennis-warehouse.com/learning_center/reporter2.php)
  lists a "Tension Loss (%)" per string from the same impact test. When it is
  set (twu_tension_loss), the string type's rates are scaled by that value over
  the type's median, e.g. a polyester measured at 30 % loses 30/41 of the
  polyester defaults. Rates entered by hand, or set by calibrate_tension, win.
- The initial 10 % is relative to the tension right after stringing, as a
  stringbed tension meter shows it; measured against the machine's pull
  tension the first-day loss is larger (28 kg -> ~20 kg in a day, Cross
  et al. 2000).

These are averages from a few lab strings, so the estimate is a guide. A
measured tension (calibrate_tension) scales the whole model to the player's
own strings.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from .const import ATTR_CROSS_TENSION, ATTR_DATE, ATTR_MAIN_STRING, ATTR_MAIN_TENSION
from .string_catalog import material

CONF_PLAY = "play"
CONF_HOURS_PER_WEEK = "hours_per_week"
CONF_STRING_TYPE = "string_type"
CONF_INITIAL_LOSS = "initial_tension_loss"
CONF_FIRST_HOUR_LOSS = "first_hour_loss"
CONF_RELAXATION_LOSS = "relaxation_loss"
CONF_TWU_LOSS = "twu_tension_loss"
# Removed in 0.4.0 (linear model); migrated to first_hour_loss
CONF_LOSS_PER_HOUR = "tension_loss_per_hour"

STRING_POLYESTER = "polyester"
STRING_NYLON = "nylon"
STRING_GUT = "gut"


@dataclass(frozen=True)
class LossRates:
    """How fast a string type loses tension (each in % of strung tension)."""

    initial: float
    first_hour: float
    relaxation: float


# See the module docstring for the sources.
STRING_TYPES: dict[str, LossRates] = {
    STRING_POLYESTER: LossRates(initial=10, first_hour=3, relaxation=4),
    STRING_NYLON: LossRates(initial=6, first_hour=1.5, relaxation=2),
    STRING_GUT: LossRates(initial=4, first_hour=1, relaxation=1.5),
}
# Median "Tension Loss (%)" per material in TWU's string database; see above.
TWU_MEDIAN_LOSS: dict[str, float] = {
    STRING_POLYESTER: 41,
    STRING_NYLON: 21,
    STRING_GUT: 15,
}
DEFAULT_STRING_TYPE = STRING_POLYESTER

# Where the string type came from
SOURCE_RACKET = "racket"  # set in the racket's play options
SOURCE_STRING = "string"  # the current main string's material (string catalog)
SOURCE_DEFAULT = "default"
MAX_LOSS = 50.0


@dataclass(frozen=True)
class PlaySettings:
    """How much a racket is played and how fast its strings lose tension."""

    hours_per_week: float
    string_type: str
    rates: LossRates
    string_type_source: str = SOURCE_DEFAULT
    twu_tension_loss: float | None = None


@dataclass(frozen=True)
class Estimate:
    """Estimated state of the current strings."""

    hours_played: float
    loss_percent: float
    main_tension: float | None
    cross_tension: float | None


def play_settings(
    options: Mapping[str, Any], record: Mapping[str, Any] | None = None
) -> PlaySettings | None:
    """The racket's play settings, or None if hours per week isn't set.

    Without a string type in the options, the material of the given restring's
    main string is used if the string catalog knows it, else polyester.
    """
    play = options.get(CONF_PLAY) or {}
    hours = play.get(CONF_HOURS_PER_WEEK)
    if hours is None:
        return None
    if (string_type := play.get(CONF_STRING_TYPE)) in STRING_TYPES:
        source = SOURCE_RACKET
    elif (
        record
        and (string_type := material(record.get(ATTR_MAIN_STRING))) in STRING_TYPES
    ):
        source = SOURCE_STRING
    else:
        string_type, source = DEFAULT_STRING_TYPE, SOURCE_DEFAULT
    preset = STRING_TYPES[string_type]
    twu = play.get(CONF_TWU_LOSS)
    if twu:
        scale = float(twu) / TWU_MEDIAN_LOSS[string_type]
        preset = LossRates(
            initial=round(preset.initial * scale, 2),
            first_hour=round(preset.first_hour * scale, 2),
            relaxation=round(preset.relaxation * scale, 2),
        )
    rates = LossRates(
        *(
            preset_value if (value := play.get(key)) is None else float(value)
            for key, preset_value in (
                (CONF_INITIAL_LOSS, preset.initial),
                (CONF_FIRST_HOUR_LOSS, preset.first_hour),
                (CONF_RELAXATION_LOSS, preset.relaxation),
            )
        )
    )
    return PlaySettings(
        float(hours),
        string_type,
        rates,
        string_type_source=source,
        twu_tension_loss=float(twu) if twu else None,
    )


def loss_percent(rates: LossRates, days: float, hours: float) -> float:
    """Tension lost after this many days and hours of play (uncapped)."""
    return (
        rates.initial
        + rates.relaxation * math.log10(max(days, 1))
        + rates.first_hour * math.log2(1 + max(hours, 0))
    )


def _reduce(tension: Any, loss: float) -> float | None:
    if not isinstance(tension, (int, float)) or isinstance(tension, bool):
        return None
    return round(tension * (1 - loss / 100), 1)


def _days(record: dict[str, Any], today: date) -> int:
    return max((today - date.fromisoformat(record[ATTR_DATE])).days, 0)


def estimate(
    record: dict[str, Any] | None, settings: PlaySettings, today: date
) -> Estimate | None:
    """Estimate for the given restring as of today, or None without a restring."""
    if not record or not record.get(ATTR_DATE):
        return None
    days = _days(record, today)
    hours = settings.hours_per_week * days / 7
    loss = round(min(loss_percent(settings.rates, days, hours), MAX_LOSS), 1)
    return Estimate(
        hours_played=round(hours, 1),
        loss_percent=loss,
        main_tension=_reduce(record.get(ATTR_MAIN_TENSION), loss),
        cross_tension=_reduce(record.get(ATTR_CROSS_TENSION), loss),
    )


def calibrate(
    record: dict[str, Any], settings: PlaySettings, measured: float, on: date
) -> PlaySettings:
    """Scale the loss rates so the model matches a measured mains tension.

    One measurement can't separate the three parts of the loss, so all three
    are scaled by the same factor. Raises ValueError if it can't be matched.
    """
    strung = record.get(ATTR_MAIN_TENSION)
    if not isinstance(strung, (int, float)) or strung <= 0:
        raise ValueError("no strung tension")
    measured_loss = (1 - measured / strung) * 100
    days = _days(record, on)
    model_loss = loss_percent(settings.rates, days, settings.hours_per_week * days / 7)
    if measured_loss <= 0 or model_loss <= 0 or measured_loss >= MAX_LOSS:
        raise ValueError("out of range")
    factor = measured_loss / model_loss
    r = settings.rates
    return replace(
        settings,
        rates=LossRates(
            initial=round(r.initial * factor, 2),
            first_hour=round(r.first_hour * factor, 2),
            relaxation=round(r.relaxation * factor, 2),
        ),
    )


def migrate_play_options(play: Mapping[str, Any]) -> dict[str, Any]:
    """Convert the linear model's loss per hour (0.3 and older) to the log model.

    The old default of 1 %/h maps to the new default of 3 % in the first hour,
    so a customised rate keeps its proportion to the default.
    """
    new = dict(play)
    if (per_hour := new.pop(CONF_LOSS_PER_HOUR, None)) is not None:
        new[CONF_FIRST_HOUR_LOSS] = round(float(per_hour) * 3, 2)
    return new
