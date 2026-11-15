"""Every translation mirrors strings.json: same keys, same placeholders."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

COMPONENT = Path(__file__).parents[1] / "custom_components" / "racket_tracker"
STRINGS = json.loads((COMPONENT / "strings.json").read_text())
ICONS = json.loads((COMPONENT / "icons.json").read_text())
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _leaves(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, f"{path}/{key}")
    else:
        yield path, node


def test_english_mirrors_strings_json():
    assert json.loads((COMPONENT / "translations" / "en.json").read_text()) == STRINGS


@pytest.mark.parametrize(
    "path", sorted((COMPONENT / "translations").glob("*.json")), ids=lambda p: p.name
)
def test_translation_matches_strings_json(path: Path):
    source = dict(_leaves(STRINGS))
    translated = dict(_leaves(json.loads(path.read_text())))
    assert translated.keys() == source.keys()
    for key, text in source.items():
        assert set(_PLACEHOLDER.findall(translated[key])) == set(
            _PLACEHOLDER.findall(text)
        ), key


def test_every_action_and_field_is_translated_and_has_an_icon():
    services = yaml.safe_load((COMPONENT / "services.yaml").read_text())
    for name, spec in services.items():
        assert name in STRINGS["services"], name
        assert name in ICONS["services"], name
        assert set(spec["fields"]) == set(STRINGS["services"][name]["fields"]), name


def test_every_entity_is_translated_and_has_an_icon():
    for platform, keys in STRINGS["entity"].items():
        assert set(keys) == set(ICONS["entity"][platform]), platform
