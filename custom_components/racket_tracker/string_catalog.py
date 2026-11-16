"""A bundled list of tennis strings, for suggestions and their material.

string_catalog.json is the Tennis Racquets and Strings Dataset by Luke Batten
(github.com/LukeBatten17/tennis-racquets-and-strings-dataset, CC0 1.0): ~780
strings with brand, model and material, as of July 2024. string_catalog_extra.json
adds newer strings in the same format. Both are read once when the module is
imported (in the executor, like the rest of the integration), so lookups never
touch the network or the disk.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent
CATALOG_SOURCE = "Tennis Racquets and Strings Dataset (CC0)"

_WORD = re.compile(r"[a-z0-9]+")
# Gauge bits that don't change the material: 16, 16L, 17, 1.25, (1.30), 130/16, 16g
_GAUGE = re.compile(r"^(1[5-9]l?g?|[0-9]+|l)$")


def _load(name: str) -> list[tuple[str, str, str | None]]:
    data: dict[str, Any] = json.loads((_HERE / name).read_text(encoding="utf-8"))
    return [
        (str(brand), str(model), kind)
        for brand, model, kind in data["strings"]
        if brand and model
    ]


CATALOG: list[tuple[str, str, str | None]] = sorted(
    {
        (brand, model, kind)
        for brand, model, kind in _load("string_catalog.json")
        + _load("string_catalog_extra.json")
    },
    key=lambda s: (s[0].lower(), s[1].lower()),
)
NAMES: list[str] = [f"{brand} {model}" for brand, model, _ in CATALOG]


def _base(text: str) -> tuple[str, ...]:
    """Words of a string name without its gauge: "Hyper-G 16L (1.25)" -> hyper g."""
    return tuple(w for w in _WORD.findall(text.lower()) if not _GAUGE.match(w))


# Base name (with and without the brand) -> materials of the strings with it
_MATERIALS: dict[tuple[str, ...], set[str | None]] = {}
for _brand, _model, _kind in CATALOG:
    for _key in (_base(f"{_brand} {_model}"), _base(_model)):
        if _key:
            _MATERIALS.setdefault(_key, set()).add(_kind)


def material(name: str | None) -> str | None:
    """polyester / nylon / gut for a string name, if the catalog knows it.

    Matches with or without the brand and ignores the gauge, so "Hyper-G 1.25",
    "Solinco Hyper-G 17" and "solinco hyper-g" all find Solinco Hyper-G. None when
    the name is unknown or its matches disagree.
    """
    if not name or not (key := _base(name)):
        return None
    kinds = _MATERIALS.get(key, set())
    return next(iter(kinds)) if len(kinds) == 1 else None


def suggestions(extra: Iterable[str] = ()) -> list[str]:
    """Names to offer: strings already used first, then the catalog."""
    seen: set[str] = set()
    out: list[str] = []
    for name in [*extra, *NAMES]:
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out
