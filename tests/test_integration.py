"""End-to-end tests: add a racket, log restrings with photos, edit, delete."""

from datetime import timedelta
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.racket_tracker.const import DOMAIN, EVENT_RESTRUNG

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01"
    b"\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _add_racket(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Pure Aero",
            "brand": "Babolat",
            "model": "Pure Aero 98",
            "head_size": 98,
            "string_pattern": "16x20",
            "tension_unit": "lbs",
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    return result["result"].entry_id


async def test_full_flow(hass: HomeAssistant, tmp_path: Path, hass_client) -> None:
    hass.config.currency = "THB"
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    assert await async_setup_component(hass, "http", {})
    entry_id = await _add_racket(hass)
    events = async_capture_events(hass, EVENT_RESTRUNG)

    assert hass.states.get("sensor.pure_aero_restrings").state == "0"
    assert hass.states.get("image.pure_aero_photo").state == "unknown"

    photo = tmp_path / "racket.png"
    photo.write_bytes(PNG)

    # First restring: full bed, with a photo
    resp = await hass.services.async_call(
        DOMAIN,
        "add_restring",
        {
            "config_entry_id": entry_id,
            "date": "2026-09-01",
            "main_string": "RPM Blast 1.25",
            "main_tension": 52,
            "cost": 600,
            "rating": 3,
            "notes": "Too stiff",
            "image": str(photo),
        },
        blocking=True,
        return_response=True,
    )
    first_id = resp["restring"]["id"]
    assert resp["restring"]["image_url"].startswith("/api/racket_tracker/images/")
    assert "authSig=" in resp["restring"]["image_url"]

    # Second restring: hybrid, photo via media selector style dict is tested below
    await hass.services.async_call(
        DOMAIN,
        "add_restring",
        {
            "config_entry_id": entry_id,
            "date": "2026-11-01",
            "main_string": "Hyper-G 1.25",
            "cross_string": "VS Touch 1.30",
            "main_tension": 50,
            "cross_tension": 48,
            "cost": 1200,
            "stringer": "Pro shop",
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    assert len(events) == 2

    assert (
        hass.states.get("sensor.pure_aero_strings").state
        == "Hyper-G 1.25 / VS Touch 1.30"
    )
    tension = hass.states.get("sensor.pure_aero_tension")
    assert (
        float(tension.state) == 50
        and tension.attributes["unit_of_measurement"] == "lbs"
    )
    assert hass.states.get("sensor.pure_aero_last_restrung").state == "2026-11-01"
    assert hass.states.get("sensor.pure_aero_days_since_restring").state.isdigit()
    cost = hass.states.get("sensor.pure_aero_total_string_cost")
    assert float(cost.state) == 1800 and cost.attributes["unit_of_measurement"] == "THB"
    assert cost.attributes["average_cost"] == 900
    hist = hass.states.get("sensor.pure_aero_restrings")
    assert hist.state == "2" and hist.attributes["history"][1]["id"] == first_id

    # Photo entity shows the most recent restring that has a photo
    photo_state = hass.states.get("image.pure_aero_photo")
    assert photo_state.state != "unknown"
    assert photo_state.attributes["restring_id"] == first_id

    client = await hass_client()
    r = await client.get(photo_state.attributes["entity_picture"])
    assert r.status == 200 and await r.read() == PNG
    # Signed URL used by dashboards
    r = await client.get(hist.attributes["history"][1]["image_url"])
    assert r.status == 200 and await r.read() == PNG

    # Update latest (no id): add notes, rating and a photo
    await hass.services.async_call(
        DOMAIN,
        "update_restring",
        {
            "config_entry_id": entry_id,
            "rating": 5,
            "notes": "Great spin",
            "image": str(photo),
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    latest = hass.states.get("sensor.pure_aero_strings").attributes
    assert latest["rating"] == 5 and latest["notes"] == "Great spin"
    assert latest["image_url"]
    assert (
        hass.states.get("image.pure_aero_photo").attributes["restring_id"] != first_id
    )

    # Remove photo from first restring, then delete it
    await hass.services.async_call(
        DOMAIN,
        "update_restring",
        {"config_entry_id": entry_id, "restring_id": first_id, "remove_image": True},
        blocking=True,
    )
    images = Path(hass.config.path(DOMAIN, "images"))
    assert not list(images.glob(f"{first_id}.*"))
    await hass.services.async_call(
        DOMAIN,
        "delete_restring",
        {"config_entry_id": entry_id, "restring_id": first_id},
        blocking=True,
    )
    resp = await hass.services.async_call(
        DOMAIN,
        "get_history",
        {"config_entry_id": entry_id},
        blocking=True,
        return_response=True,
    )
    assert resp["restring_count"] == 1 and resp["total_cost"] == 1200

    # History survives a reload
    await hass.config_entries.async_reload(entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.pure_aero_restrings").state == "1"

    # Options flow edits racket details
    result = await hass.config_entries.options.async_init(entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"brand": "Babolat", "tension_unit": "kg"}
    )
    await hass.async_block_till_done()
    assert (
        hass.states.get("sensor.pure_aero_tension").attributes["unit_of_measurement"]
        == "kg"
    )

    # Removing the racket cleans up photos
    remaining = [r["image"] for r in resp["restrings"] if r.get("image")]
    assert remaining
    await hass.config_entries.async_remove(entry_id)
    await hass.async_block_till_done()
    assert not any((images / name).exists() for name in remaining)


async def test_bad_image(hass: HomeAssistant, tmp_path: Path) -> None:
    import pytest
    from homeassistant.exceptions import ServiceValidationError

    assert await async_setup_component(hass, "http", {})
    entry_id = await _add_racket(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "add_restring",
            {
                "config_entry_id": entry_id,
                "main_string": "X",
                "main_tension": 50,
                "image": "/etc/passwd",
            },
            blocking=True,
        )
    # Today is the default date
    await hass.services.async_call(
        DOMAIN,
        "add_restring",
        {"config_entry_id": entry_id, "main_string": "X", "main_tension": 50},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.pure_aero_days_since_restring").state == "0"


async def test_media_browser_photo(hass: HomeAssistant, tmp_path: Path) -> None:
    """Photo picked from My media in the action form (media selector value)."""
    (tmp_path / "rackets").mkdir()
    (tmp_path / "rackets" / "aero.png").write_bytes(PNG)
    hass.config.media_dirs = {"local": str(tmp_path)}
    assert await async_setup_component(hass, "http", {})
    entry_id = await _add_racket(hass)
    resp = await hass.services.async_call(
        DOMAIN,
        "add_restring",
        {
            "config_entry_id": entry_id,
            "main_string": "ALU Power",
            "main_tension": 53,
            "image": {
                "media_content_id": "media-source://media_source/local/rackets/aero.png",
                "media_content_type": "image/png",
            },
        },
        blocking=True,
        return_response=True,
    )
    assert resp["restring"]["image"].endswith(".png")
    assert (
        Path(hass.config.path(DOMAIN, "images")) / resp["restring"]["image"]
    ).read_bytes() == PNG


async def test_diagnostics(hass: HomeAssistant) -> None:
    from custom_components.racket_tracker.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    assert await async_setup_component(hass, "http", {})
    entry_id = await _add_racket(hass)
    await hass.services.async_call(
        DOMAIN,
        "add_restring",
        {"config_entry_id": entry_id, "main_string": "X", "main_tension": 50},
        blocking=True,
    )
    diag = await async_get_config_entry_diagnostics(
        hass, hass.config_entries.async_get_entry(entry_id)
    )
    assert diag["title"] == "Pure Aero"
    assert diag["options"]["brand"] == "Babolat"
    assert diag["restring_count"] == 1 and diag["restrings"][0]["main_string"] == "X"
    # No signed photo URLs in a file users share
    assert "image_url" not in diag["restrings"][0]


async def test_photos_need_login(
    hass: HomeAssistant,
    tmp_path: Path,
    hass_client,
    hass_client_no_auth,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Photos are served only to logged-in users or through short-lived signed URLs."""
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    assert await async_setup_component(hass, "http", {})
    entry_id = await _add_racket(hass)
    photo = tmp_path / "racket.png"
    photo.write_bytes(PNG)
    resp = await hass.services.async_call(
        DOMAIN,
        "add_restring",
        {
            "config_entry_id": entry_id,
            "main_string": "X",
            "main_tension": 50,
            "image": str(photo),
        },
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    filename = resp["restring"]["image"]
    signed = hass.states.get("sensor.pure_aero_strings").attributes["image_url"]
    path = signed.split("?")[0]
    assert path == f"/api/racket_tracker/images/{filename}"
    anonymous = await hass_client_no_auth()
    client = await hass_client()

    # The signed URL works without a login; the bare path, a tampered signature or
    # the old static path don't
    r = await anonymous.get(signed)
    assert r.status == 200 and await r.read() == PNG
    assert r.headers["Cache-Control"].startswith("private")
    assert (await anonymous.get(path)).status == 401
    assert (await anonymous.get(signed[:-3] + "abc")).status == 401
    assert (await anonymous.get(f"/racket_tracker/images/{filename}")).status == 404
    # A login is enough, but only for stored photo names
    assert (await client.get(path)).status == 200
    for name in ("racket_tracker.json", "0123456789ab.png"):
        assert (await client.get(f"/api/racket_tracker/images/{name}")).status == 404
    traversal = await client.get("/api/racket_tracker/images/%2e%2e%2fsecrets.yaml")
    assert traversal.status in (400, 404)

    # Every midnight the sensors sign the URLs again, before the old ones expire
    for _ in range(3):
        freezer.tick(timedelta(days=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert (await anonymous.get(signed)).status == 401
    fresh = hass.states.get("sensor.pure_aero_strings").attributes["image_url"]
    history = hass.states.get("sensor.pure_aero_restrings").attributes["history"]
    for url in (fresh, history[0]["image_url"]):
        assert url != signed
        assert (await anonymous.get(url)).status == 200


async def test_no_recorder(hass: HomeAssistant) -> None:
    """Without the recorder, backfilling is skipped quietly."""
    from custom_components.racket_tracker.backfill import async_backfill

    assert await async_setup_component(hass, "http", {})
    entry_id = await _add_racket(hass)
    await hass.services.async_call(
        DOMAIN,
        "add_restring",
        {"config_entry_id": entry_id, "main_string": "X", "main_tension": 50},
        blocking=True,
    )
    await async_backfill(hass, hass.config_entries.async_get_entry(entry_id))


async def test_current_strings_in_forms(hass: HomeAssistant) -> None:
    """The add and options forms save the strings on the racket now."""
    assert await async_setup_component(hass, "http", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    # A main string without a tension is not enough
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Blade",
            "tension_unit": "lbs",
            "current": {"main_string": "RPM Blast 1.25"},
        },
    )
    assert result["errors"] == {"base": "current_incomplete"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Blade",
            "tension_unit": "lbs",
            "current": {
                "main_string": "RPM Blast 1.25",
                "main_tension": 52.0,
                "date": "2026-10-01",
            },
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.data == {}
    [record] = entry.runtime_data.restrings
    assert record["date"] == "2026-10-01"
    assert record["main_tension"] == 52 and record["cross_tension"] == 52
    assert record["cross_string"] == "RPM Blast 1.25"
    assert hass.states.get("sensor.blade_restrings").state == "1"

    async def configure(current: dict, error: str | None = None) -> None:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        # The section is prefilled from the latest restring
        current_section = result["data_schema"].schema["current"]
        suggested = {
            str(key): (key.description or {}).get("suggested_value")
            for key in current_section.schema.schema
        }
        latest = entry.runtime_data.latest
        assert suggested["main_string"] == latest["main_string"]
        assert suggested["date"] == latest["date"]
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"tension_unit": "lbs", "current": current}
        )
        if error:
            assert result["errors"] == {"base": error}
            return
        assert result["type"] == "create_entry"
        await hass.async_block_till_done()

    # Same date as the latest restring: corrects it
    await configure(
        {"main_string": "RPM Blast 1.25", "main_tension": 53, "date": "2026-10-01"}
    )
    [record] = entry.runtime_data.restrings
    assert record["main_tension"] == 53 and record["cross_tension"] == 53

    # Unchanged: nothing happens
    await configure(
        {"main_string": "RPM Blast 1.25", "main_tension": 53, "date": "2026-10-01"}
    )
    assert entry.runtime_data.count == 1

    # Only the date changed: moves the latest restring
    await configure(
        {"main_string": "RPM Blast 1.25", "main_tension": 53, "date": "2026-09-20"}
    )
    [record] = entry.runtime_data.restrings
    assert record["date"] == "2026-09-20" and record["main_tension"] == 53

    # Not past the day the strings broke
    await entry.runtime_data.async_update(record["id"], {"broken_date": "2026-10-05"})
    await configure(
        {"main_string": "RPM Blast 1.25", "main_tension": 53, "date": "2026-10-10"},
        "current_after_broken",
    )
    assert entry.runtime_data.latest["date"] == "2026-09-20"

    # Strings and date changed: a new restring
    await configure(
        {
            "main_string": "Hyper-G 1.25",
            "main_tension": 50,
            "cross_string": "Velocity 1.30",
            "cross_tension": 52.5,
            "date": "2026-11-10",
        }
    )
    latest = entry.runtime_data.latest
    assert entry.runtime_data.count == 2
    assert latest["date"] == "2026-11-10" and latest["cross_tension"] == 52.5
    assert latest["tension_unit"] == "lbs"
