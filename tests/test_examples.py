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
    for name in ("dashboard.yaml", "dashboard_multi.yaml", "scripts.yaml"):
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
            "play": {"hours_per_week": 4},
            "due": {"days": 60},
        },
    )
    await hass.async_block_till_done()
    scripts = load_yaml(str(EXAMPLES / "scripts.yaml"))
    assert await async_setup_component(hass, "script", {"script": scripts})
    await hass.async_block_till_done()

    # A second racket and the dropdown, for dashboard_multi.yaml
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Blade", "tension_unit": "kg", "play": {"hours_per_week": 2}},
    )
    assert await async_setup_component(
        hass, "input_select", {"input_select": {"racket": {"options": ["Blade"]}}}
    )
    await hass.async_block_till_done()

    for name in ("dashboard.yaml", "dashboard_multi.yaml"):
        used = _entity_ids(load_yaml(str(EXAMPLES / name)))
        assert used, f"no entities found in {name}"
        missing = sorted(e for e in used if hass.states.get(e) is None)
        assert not missing, (name, missing)


def _markdown(node) -> list[str]:
    """Every markdown card's template in a dashboard."""
    found: list[str] = []
    if isinstance(node, dict):
        if node.get("type") == "markdown":
            found.append(node["content"])
        for value in node.values():
            found += _markdown(value)
    elif isinstance(node, list):
        for item in node:
            found += _markdown(item)
    return found


async def test_multi_racket_dashboard(hass: HomeAssistant) -> None:
    """The dropdown-driven cards render the picked racket; the script restrings it."""
    from datetime import timedelta

    from homeassistant import config_entries
    from homeassistant.helpers.template import Template
    from homeassistant.util import dt as dt_util

    from custom_components.racket_tracker.const import DOMAIN

    assert await async_setup_component(hass, "http", {})
    aero = await _add_racket(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Blade",
            "tension_unit": "kg",
            "play": {"hours_per_week": 3},
            "due": {"days": 30},
            "setup": {"main_string": "ALU Power", "main_tension": 24},
        },
    )
    blade = result["result"].entry_id
    await hass.async_block_till_done()
    assert await async_setup_component(
        hass,
        "input_select",
        {"input_select": {"racket": {"options": ["Blade", "Pure Aero", "Nope"]}}},
    )
    scripts = load_yaml(str(EXAMPLES / "scripts.yaml"))
    assert await async_setup_component(hass, "script", {"script": scripts})
    await hass.async_block_till_done()
    for entry_id, data in (
        (aero, {"main_string": "RPM Blast", "main_tension": 53, "notes": "Spin"}),
        (
            blade,
            {
                "main_string": "ALU Power",
                "cross_string": "Gut",
                "main_tension": 24,
                "cross_tension": 23,
                "rating": 4,
                "date": (dt_util.now().date() - timedelta(days=40)).isoformat(),
            },
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            "add_restring",
            {"config_entry_id": entry_id, **data},
            blocking=True,
        )
    await hass.async_block_till_done()

    detail, overview, history = _markdown(
        load_yaml(str(EXAMPLES / "dashboard_multi.yaml"))
    )

    def render(content: str) -> str:
        return Template(content, hass).async_render(parse_result=False)

    async def pick(name: str) -> None:
        await hass.services.async_call(
            "input_select",
            "select_option",
            {"entity_id": "input_select.racket", "option": name},
            blocking=True,
        )

    await pick("Blade")
    text = render(detail)
    assert "**ALU Power / Gut** @ 24/23 kg" in text
    assert "(40 days ago)" in text and "⭐⭐⭐⭐" in text
    assert "Estimated now: **" in text and "Restring due" in text
    assert "ALU Power / Gut" in render(history) and "RPM Blast" not in render(history)

    await pick("Pure Aero")
    text = render(detail)
    assert "**RPM Blast** @ 53 lbs" in text and "Spin" in text
    assert "Estimated" not in text and "Next restring" not in text
    assert "RPM Blast" in render(history)

    await pick("Nope")
    assert render(detail).strip() == "Pick a racket above."
    assert render(history).strip() == "No restrings logged yet."

    table = render(overview)
    assert table.index("**Blade**") < table.index("**Pure Aero**")
    assert "⚠️ **Due**" in table and "| 53 lbs |" in table

    # dashboard.yaml's cards render too, with a restring that has no cost
    for content in _markdown(load_yaml(str(EXAMPLES / "dashboard.yaml"))):
        assert "RPM Blast" in render(content) or "Specs" not in content

    # The script restrings the picked racket with its usual setup
    await pick("Blade")
    await hass.services.async_call(
        "script", "restring_selected_racket", {}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.blade_restrings").state == "2"
    assert hass.states.get("sensor.pure_aero_restrings").state == "1"
    assert hass.states.get("sensor.blade_strings").state == "ALU Power"
