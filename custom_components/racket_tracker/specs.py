"""Racket specs: values from a reference dataset, overridden by your own measurements.

`options["specs"]` holds what the user entered (measured themselves); it always
wins. `options["dataset_specs"]` is reserved for values looked up from a racket
dataset; nothing fills it yet, but the merge already treats it as the base layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength, UnitOfMass

from .const import CONF_TENSION_UNIT, TENSION_UNIT_LBS

CONF_SPECS = "specs"
CONF_DATASET_SPECS = "dataset_specs"

SOURCE_MEASURED = "measured"
SOURCE_DATASET = "dataset"


@dataclass(frozen=True, kw_only=True)
class Spec:
    """One racket spec."""

    key: str
    unit: str | None
    min: float
    max: float
    step: float
    device_class: SensorDeviceClass | None = None
    tension_unit: bool = False  # unit follows the racket's tension unit


SPECS: tuple[Spec, ...] = (
    Spec(
        key="strung_weight",
        unit=UnitOfMass.GRAMS,
        min=150,
        max=450,
        step=0.1,
        device_class=SensorDeviceClass.WEIGHT,
    ),
    Spec(
        key="unstrung_weight",
        unit=UnitOfMass.GRAMS,
        min=150,
        max=450,
        step=0.1,
        device_class=SensorDeviceClass.WEIGHT,
    ),
    Spec(
        key="balance",
        unit=UnitOfLength.MILLIMETERS,
        min=250,
        max=400,
        step=0.5,
        device_class=SensorDeviceClass.DISTANCE,
    ),
    Spec(key="swingweight", unit="kg·cm²", min=200, max=450, step=1),
    Spec(key="stiffness", unit="RA", min=40, max=85, step=1),
    Spec(
        key="length",
        unit=UnitOfLength.INCHES,
        min=19,
        max=29.5,
        step=0.25,
        device_class=SensorDeviceClass.DISTANCE,
    ),
    Spec(key="tension_min", unit=None, min=10, max=80, step=0.5, tension_unit=True),
    Spec(key="tension_max", unit=None, min=10, max=80, step=0.5, tension_unit=True),
)
SPEC_KEYS = tuple(s.key for s in SPECS)


def spec_unit(entry: ConfigEntry, spec: Spec) -> str | None:
    """Unit of a spec for this racket."""
    if spec.tension_unit:
        return entry.options.get(CONF_TENSION_UNIT, TENSION_UNIT_LBS)
    return spec.unit


def effective_specs(entry: ConfigEntry) -> dict[str, dict[str, Any]]:
    """Merged specs: {key: {"value": v, "source": "measured" | "dataset"}}."""
    out: dict[str, dict[str, Any]] = {}
    for layer, source in (
        (entry.options.get(CONF_DATASET_SPECS) or {}, SOURCE_DATASET),
        (entry.options.get(CONF_SPECS) or {}, SOURCE_MEASURED),
    ):
        for key, value in layer.items():
            if key in SPEC_KEYS and value not in (None, ""):
                out[key] = {"value": value, "source": source}
    return out
