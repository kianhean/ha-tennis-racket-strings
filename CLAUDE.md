# Racket String Tracker (Home Assistant integration)

A HACS integration that keeps a restring log for tennis rackets. Domain: `racket_tracker`.
One config entry = one racket = one device.

## Structure

```
custom_components/racket_tracker/
├── __init__.py        # Setup/unload, action registration (in async_setup), photo static path
├── const.py           # DOMAIN, option keys, restring field names, action/event names
├── history.py         # RacketHistory: per-racket Store (.storage/racket_tracker.<entry_id>), listeners
├── images.py          # Photo import (media selector / media-source ID / allowed path) → <config>/racket_tracker/images
├── specs.py           # SPECS definitions; effective_specs() merges dataset_specs < specs (user wins)
├── config_flow.py     # Add racket (name, details, collapsible "specs" section); options flow edits them
├── entity.py          # racket_device_info(entry)
├── sensor.py          # History-derived sensors + one RacketSpecSensor per spec that has a value
├── image.py           # image.<racket>_photo: most recent restring photo
├── diagnostics.py     # Options, effective specs, full history
├── services.yaml      # add_restring, update_restring, delete_restring, get_history
├── icons.json         # Entity + action icons (no _attr_icon in code)
├── strings.json       # Source strings; translations/en.json must be identical
├── quality_scale.yaml # Self-assessment; keep it honest
└── brand/             # icon/logo PNGs loaded by HA 2026.3+ and checked by hacs/action. Do not delete.

blueprints/automation/racket_tracker/  # restring_reminder, restring_logged, rate_strings
examples/              # scripts.yaml (form UI), dashboard.yaml (built-in cards only)
images/brand/*.svg     # Sources for brand/*.png (render with rsvg-convert, trim with ImageMagick)
tests/                 # All tests run against a real HA via pytest-homeassistant-custom-component
```

## Data model

- `entry.runtime_data` is the racket's `RacketHistory`. Records are dicts sorted by
  (`date`, `created`); `latest` is the last one. Dates are ISO strings.
- Record fields: `id`, `created`, `updated`, `date`, `main_string`, `cross_string`,
  `main_tension`, `cross_tension`, `tension_unit`, `cost`, `stringer`, `rating`, `notes`, `image`
  (stored file name). `with_image_url()` adds `image_url` for attributes, events and responses.
- `add_restring` defaults `cross_string`/`cross_tension` to the mains and the date to today.
  Whole-number tensions/costs are stored as ints (`_whole`).
- `update_restring` without `restring_id` edits the latest restring.
- Options: `brand`, `model`, `head_size`, `string_pattern`, `tension_unit`, `specs` (user's
  measurements), `dataset_specs` (reserved for a future racket-database lookup; the options flow
  preserves it). Changing options reloads the entry.

## Photos

Photos are copied into `<config>/racket_tracker/images/<restring_id>.<ext>` and served unauthenticated at
`/racket_tracker/images/` (random IDs, like `/local/`); the image entity uses HA's token auth.
Media-source IDs resolve via `PlayMedia.path` (HA 2025.6+) with a `/media/<dir>/<file>`
fallback for older versions. Deleting a restring/racket deletes its photos.

## Specs

`specs.SPECS` drives the config-flow section, sensors, translations (`entity.sensor.<key>`,
`config/options...sections.specs.data.<key>`) and icons. A spec sensor exists only when the
effective value is set; cleared ones are removed from the entity registry on setup. Spec
sensors with a device class set `suggested_unit_of_measurement` to their native unit so a metric
HA doesn't show racket length in mm. Older HA rejects a suggested unit when there is no device class.

## Testing and versions

```bash
pip install -r requirements_test.txt && pytest
ruff check custom_components/ tests/ --fix && ruff format custom_components/ tests/
```

CI (`tests.yml`) runs the minimum HA (2025.7.0, harness 0.13.260, plus `pycares<5`), stable
(2026.9.4, 0.13.367, Python 3.14) and the newest harness (non-blocking). 2025.7 is the first HA with
`accept` on the media selector. When bumping the minimum, update `hacs.json`, the blueprints'
`min_version`, the README badge and the matrix together.

Tests that must stay: every blueprint is tested (`test_every_blueprint_is_tested`), every
dashboard entity exists (`test_dashboard_entities_exist`), and strings/translations/icons/services
stay in sync (`test_translations.py`).

## Releases

Bump `version` in `manifest.json` in every PR that changes shipped code. Merging to `main`
makes `release.yml` tag `v<version>`, create the GitHub release and attach `racket_tracker.zip`
(built with `git archive HEAD:custom_components/racket_tracker`), which HACS installs
(`hacs.json`: `zip_release`).

## Conventions

- Async only; blocking file I/O goes through `hass.async_add_executor_job`.
- `_attr_has_entity_name = True` + translation keys; icons in `icons.json`; unique IDs `{entry_id}_{key}`.
- Platforms use `AddConfigEntryEntitiesCallback`.
- User-facing errors are `ServiceValidationError` with translation keys under `exceptions`.
- README images and examples must show only what HA really renders from built-in cards.
