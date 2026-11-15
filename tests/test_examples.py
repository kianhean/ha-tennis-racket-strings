"""Make sure the example scripts in examples/scripts.yaml actually work."""

from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml

from .test_integration import PNG, _add_racket

EXAMPLES = Path(__file__).parent.parent / "examples"


async def test_example_scripts(hass: HomeAssistant, tmp_path: Path) -> None:
    hass.config.media_dirs = {"local": str(tmp_path)}
    (tmp_path / "r.png").write_bytes(PNG)
    assert await async_setup_component(hass, "http", {})
    entry_id = await _add_racket(hass)
    scripts = load_yaml(str(EXAMPLES / "scripts.yaml"))
    assert await async_setup_component(hass, "script", {"script": scripts})
    await hass.async_block_till_done()

    # Minimal form: only required fields
    await hass.services.async_call(
        "script",
        "log_restring",
        {"racket": entry_id, "main_string": "RPM Blast", "main_tension": 52},
        blocking=True,
    )
    # Full form incl. hybrid + photo from My media
    await hass.services.async_call(
        "script",
        "log_restring",
        {
            "racket": entry_id,
            "date": "2030-01-01",
            "main_string": "Hyper-G",
            "main_tension": 50,
            "cross_string": "VS Touch",
            "cross_tension": 48,
            "cost": 900,
            "stringer": "Shop",
            "notes": "Nice",
            "image": {
                "media_content_id": "media-source://media_source/local/r.png",
                "media_content_type": "image/png",
            },
        },
        blocking=True,
    )
    await hass.services.async_call(
        "script",
        "rate_current_strings",
        {"racket": entry_id, "rating": 4, "notes": "Holds tension well"},
        blocking=True,
    )
    await hass.async_block_till_done()
    a = hass.states.get("sensor.pure_aero_strings").attributes
    assert hass.states.get("sensor.pure_aero_strings").state == "Hyper-G / VS Touch"
    assert a["rating"] == 4 and a["notes"] == "Holds tension well" and a["image_url"]
    assert a["cost"] == 900
    assert hass.states.get("sensor.pure_aero_restrings").state == "2"


async def test_example_yaml_parses() -> None:
    for name in ("dashboard.yaml", "scripts.yaml"):
        assert load_yaml(str(EXAMPLES / name))


def _entity_ids(node) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("entity", "entities") and isinstance(value, str):
                found.add(value)
            found |= _entity_ids(value)
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, str) and "." in item and " " not in item:
                found.add(item)
            found |= _entity_ids(item)
    return found


async def test_dashboard_entities_exist(hass: HomeAssistant) -> None:
    """Every entity the example dashboard uses is one the integration creates."""
    from homeassistant import config_entries

    from custom_components.racket_tracker.const import DOMAIN
    from custom_components.racket_tracker.specs import SPECS

    assert await async_setup_component(hass, "http", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Pure Aero",
            "tension_unit": "lbs",
            "specs": {s.key: s.min for s in SPECS},
        },
    )
    await hass.async_block_till_done()
    scripts = load_yaml(str(EXAMPLES / "scripts.yaml"))
    assert await async_setup_component(hass, "script", {"script": scripts})
    await hass.async_block_till_done()

    dashboard = load_yaml(str(EXAMPLES / "dashboard.yaml"))
    used = _entity_ids(dashboard)
    assert used, "no entities found in dashboard.yaml"
    missing = sorted(e for e in used if hass.states.get(e) is None)
    assert not missing, missing
