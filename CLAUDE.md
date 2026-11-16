# Strung: tennis racket restring tracker (Home Assistant integration)

A HACS integration that keeps a restring log for tennis rackets. Domain: `racket_tracker`.
One config entry = one racket = one device.

## Structure

```
custom_components/racket_tracker/
├── __init__.py        # Setup/unload, action registration (in async_setup), photo static path
├── const.py           # DOMAIN, option keys, restring field names, action/event names
├── history.py         # RacketHistory: per-racket Store (.storage/racket_tracker.<entry_id>), listeners
├── images.py          # Photo import (media selector / media-source ID / allowed path) → <config>/racket_tracker/images
├── dataset.py         # Racqix dataset: download ≤ once a day (after HA start / on search) → .storage/racket_tracker.dataset; fallback racqix_dataset.json (bundled, unmodified CC BY-NC-ND: never edit, only replace); search, label, apply()
├── repairs.py         # On entry setup: linked racket (async_get_racquet: /api/racquets/<slug>, ~6 kB, 404 = removed; never the list) → issues (specs changed / missing: fix flows; unreachable: warning, retry after 1 h)
├── string_catalog.py  # Bundled string list (string_catalog.json, CC0 2024 + string_catalog_extra.json): suggestions(), material()
├── stats.py           # Pure stats over the history: string life, breakages, cost this year / per hour, most used / best rated setup, summary()
├── history_io.py      # CSV export (<config>/racket_tracker/exports, not served) and import (parse_csv: validate all rows, skip duplicates)
├── tension.py         # Estimated tension: options["play"] → estimate(); log-time + log-play model, sources in its docstring
├── backfill.py        # Hourly long-term statistics for tension + estimated_tension from the history (recorder import, serialized per entry)
├── due.py             # Restring rules options["due"] (days, hours_played, min_tension) → next_due()
├── specs.py           # SPECS definitions; effective_specs() merges dataset_specs < specs (user wins)
├── config_flow.py     # Add racket (name, optional lookup → "pick" step, details, collapsible play/due/setup/specs); options flow edits them; reconfigure renames
├── entity.py          # racket_device_info(entry), DailyRacketEntity (history + midnight), async_remove_entity
├── sensor.py          # History-derived sensors, PlaySensors (only with hours/week), StatsSensors (cost_per_hour only with hours/week), next_restring (only with due rules), one RacketSpecSensor per spec
├── binary_sensor.py   # restring_due (only with due rules)
├── calendar.py        # calendar.<racket>_restrings: all-day event per restring + next due
├── button.py          # Restring with usual setup → usual_setup() + async_log_restring(); Strings broke → async_mark_broken()
├── image.py           # image.<racket>_photo: most recent restring photo
├── diagnostics.py     # Options, effective specs, full history
├── services.yaml      # add_restring, repeat_restring, calibrate_tension, update_restring, delete_restring, get_history, export_history, import_history
├── icons.json         # Entity + action icons (no _attr_icon in code)
├── strings.json       # Source strings; translations/en.json must be identical
├── quality_scale.yaml # Self-assessment; keep it honest
└── brand/             # icon/logo PNGs loaded by HA 2026.3+ and checked by hacs/action. Do not delete.

blueprints/automation/racket_tracker/  # restring_due, restring_reminder, restring_logged, rate_strings, racket_picker
examples/              # scripts.yaml (form UI), dashboard.yaml (one racket), dashboard_multi.yaml (dropdown: input_select.racket + racket_picker blueprint; cards find the racket by sensor.<racket>_strings). Built-in cards only
images/brand/          # strung-logo.jpg (the logo) → make_brand.py → brand/*.png (no tagline; light logo recolours white to navy)
images/screenshots/    # README screenshots: real HA 2026.9 rendering examples/dashboard.yaml and dashboard_multi.yaml (light + dark)
tests/                 # All tests run against a real HA via pytest-homeassistant-custom-component
```

## Data model

- `entry.runtime_data` is the racket's `RacketHistory`. Records are dicts sorted by
  (`date`, `created`); `latest` is the last one. Dates are ISO strings.
- Record fields: `id`, `created`, `updated`, `date`, `main_string`, `cross_string`,
  `main_tension`, `cross_tension`, `tension_unit`, `cost`, `stringer`, `rating`, `notes`, `image`
  (stored file name), `broken_date` (strings broke; never before `date`). `with_image_url()` adds
  `image_url` for attributes, events and responses. `update_restring` takes `broken` (true: today or
  `broken_date`; false: clears).
- `add_restring` defaults `cross_string`/`cross_tension` to the mains and the date to today.
  Whole-number tensions/costs are stored as ints (`_whole`).
- `update_restring` without `restring_id` edits the latest restring.
- Options: `brand`, `model`, `head_size`, `string_pattern`, `tension_unit`, `specs` (user's
  measurements), `dataset_specs` (unstrung weight, balance, swingweight, stiffness from the Racqix dataset) and
  `dataset_racket` (`slug`, `name`, `version`). The options flow keeps both unless "Use looked-up
  specs" is turned off. Dataset details only fill brand/model/head size/pattern the user left
  blank. Changing options reloads the entry.
- `play` (optional section): `hours_per_week`, `string_type` (polyester/nylon/gut presets),
  `twu_tension_loss` (the string's TWU "Tension Loss (%)": scales the preset by value / median of the
  type, `TWU_MEDIAN_LOSS`) and optional overrides `initial_tension_loss`, `first_hour_loss`,
  `relaxation_loss`. `play_settings(options, record)`: without `string_type`, the record's main
  string's material from the string catalog, else polyester (`string_type_source`). Pass the
  restring whose estimate you want (backfill does it per record).
  loss = initial + relaxation·log10(days) + first_hour·log2(1 + hours), capped at 50 %. The
  model and its presets are cited in `tension.py` and README "Where the numbers come from"; keep
  both in sync. `calibrate_tension` scales all three rates to a measured tension. Entry minor
  version 2 migrated the old linear `tension_loss_per_hour` (×3 → `first_hour_loss`). Without
  hours/week the estimate sensors are removed.
- `due` (optional section): `days`, `hours_played`, `min_tension` (racket unit); earliest wins.
  `hours_played`/`min_tension` need hours/week (flow error `due_needs_play`). Without rules the
  due binary sensor and next_restring sensor are removed.
- `setup` (optional section): the usual `main_string`, `main_tension`, `cross_string`,
  `cross_tension`, `stringer`, `cost` (needs main string + tension). `repeat_restring` and the
  button use it, else the latest restring. All logging goes through `async_log_restring()`.
- Racqix is the integration's only network host. The list (`/api/racquets?mode=minimal`, ~1 MB;
  the API ignores search/filter params) is downloaded at most once a day, success or not
  (`attempted` in the store): in the background after HA starts, or on a search. Racqix's Vercel
  bot protection can answer HA with a 429 challenge; then the last download, else the bundled
  copy, is searched. Tests patch `async_schedule_refresh` (conftest). The repairs check
  asks for one linked racket (`/api/racquets/<slug>`: other field names, numbers as text; mapped by
  `_DETAIL_FIELDS`). Tests mock both with `aioclient_mock` (`_mock_api` in test_dataset.py).
- String suggestions: `async_update_string_suggestions()` re-registers the add/update_restring
  descriptions (services.yaml, loaded once) with a `select` + `custom_value` selector for
  main/cross string: used strings first, then the catalog. Runs on setup and history changes.
  Stats sensor names must not end in "strings": dashboards find rackets by `sensor.*_strings`.
- Import fires no `restrung` events. Duplicates: same `id`, or same date + main string + tension.

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
mypy   # strict, config in mypy.ini; CI runs it on the stable HA only
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
- Cite Tennis Warehouse / TWU as plain text, never as links: their terms of use forbid linking
  without written permission, and copying or data mining their content. Don't bundle or fetch TWU data;
  users type values in (`twu_tension_loss`).
