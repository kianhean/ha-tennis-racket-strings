<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="custom_components/racket_tracker/brand/dark_logo@2x.png">
    <img src="custom_components/racket_tracker/brand/logo@2x.png" alt="Strung: tennis restring tracker for Home Assistant" height="96">
  </picture>
</h1>

<p align="center">
  A restring log for every tennis racket you own: strings, tensions, cost, photos<br>
  and notes on what you liked, plus your racket's specs, all inside Home Assistant.
</p>

<p align="center">
  <a href="https://hacs.xyz/docs/faq/custom_repositories"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS Custom"></a>
  <a href="https://github.com/kianhean/ha-tennis-racket-strings/releases"><img src="https://img.shields.io/github/v/release/kianhean/ha-tennis-racket-strings" alt="Latest release"></a>
  <a href="https://github.com/kianhean/ha-tennis-racket-strings/releases"><img src="https://img.shields.io/github/downloads/kianhean/ha-tennis-racket-strings/total" alt="Downloads"></a>
  <a href="https://analytics.home-assistant.io/custom_integrations.json"><img src="https://img.shields.io/badge/dynamic/json?label=active%20installs&color=41BDF5&query=%24.racket_tracker.total&url=https%3A%2F%2Fanalytics.home-assistant.io%2Fcustom_integrations.json" alt="Active installs (Home Assistant analytics)"></a>
  <a href="https://github.com/kianhean/ha-tennis-racket-strings/actions/workflows/tests.yml"><img src="https://github.com/kianhean/ha-tennis-racket-strings/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2025.7%2B-41BDF5?logo=home-assistant&logoColor=white" alt="Home Assistant 2025.7 or newer">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/kianhean/ha-tennis-racket-strings" alt="MIT License"></a>
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=kianhean&repository=ha-tennis-racket-strings&category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and open this repository in HACS"></a>
  <a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=racket_tracker"><img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Open your Home Assistant instance and start adding a racket"></a>
</p>

<p align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/screenshots/dashboard-dark.png">
  <img src="images/screenshots/dashboard-light.png" alt="The example Rackets dashboard: photo, current hybrid strings, tension and estimated tension, log, usual setup and rate buttons, specs from the dataset and your measurements, restring due and next restring with a calendar, and a restring history table with photos" width="800">
</picture>
</p>

## What's inside

| | | |
|---|---|---|
| 🔔 **Restring due**<br>Restring after N days, N hours of play, or when the estimated tension drops to a set value: a [due sensor and a calendar](#restring-due) | 🔁 **Usual setup**<br>Save your usual string job and [log it in one tap](#usual-setup) | 📅 **Calendar**<br>Every restring, and the next one due, in HA's calendar |
| 🎾 **One device per racket**<br>Brand, model, head size and string pattern, with lbs or kg per racket; add as many rackets as you own | 🧵 **Restring history**<br>Date, mains and crosses (hybrids too), tensions, cost and stringer, plus a 1–5 rating and notes for every job | ⏱️ **Tension estimate**<br>A [research-based](#where-the-numbers-come-from) estimate of the current tension, by string type, that you can calibrate with a measurement |
| 📸 **A photo per restring**<br>Upload from your phone through HA's media browser | 📏 **Racket specs**<br>Weight, balance, swingweight, stiffness, length and recommended tension range: looked up from a 1,250-racket dataset, or your own measurements | 📊 **Sensors**<br>Current strings, tension (graphed over time), last restrung, string age, number of restrings and total spent |
| 🛠️ **Actions**<br>Add, edit and delete restrings or fetch the whole history, from scripts, automations and dashboards | 🧩 **Blueprints**<br>[One-click automations](#one-click-blueprints): restring due, a notification with the photo, and a nudge to rate your strings | 🏠 **Local first**<br>No account. History lives in `.storage`, photos in your config folder. The only network request is the optional racket lookup |

## Installation

1. Use the **Open in HACS** button above, or in HACS go to **⋮ → Custom repositories**, add
   `https://github.com/kianhean/ha-tennis-racket-strings` and pick the **Integration** category.
2. Search for **Strung** and install it.
3. Restart Home Assistant.

Requires **Home Assistant 2025.7** or newer.

<details>
<summary>Manual install</summary>

Download `racket_tracker.zip` from the [latest release](https://github.com/kianhean/ha-tennis-racket-strings/releases/latest),
unzip it into `<config>/custom_components/racket_tracker/`, and restart Home Assistant.
</details>

## Setup

1. Go to **Settings → Devices & services → Add integration** (or use the **Add integration** button above).
2. Search for **Strung**.
3. Fill in the racket:

| Field | Example | |
|---|---|---|
| Name | `Pure Aero` | Used for entity IDs, e.g. `sensor.pure_aero_tension` |
| Look up *(optional)* | `pure aero 2023` | Finds the racket in the [racket dataset](#looked-up-specs) and fills in its specs |
| Brand / Model | `Babolat` / `Pure Aero 98` | Shown on the device |
| Head size | `98` sq in | |
| String pattern | `16x20` | |
| Tension unit | lbs or kg | Used for every tension on this racket: restrings, recommended range and estimates |
| **Play and tension loss** *(optional, collapsed)* | `4` h/week | Turns on the [tension estimate](#estimated-tension) |
| **Restring reminder** *(optional, collapsed)* | `60` days | Turns on [Restring due](#restring-due) |
| **Usual setup** *(optional, collapsed)* | `RPM Blast` @ `52` | For [one-tap restrings](#usual-setup) |
| **Specs** *(optional, collapsed)* | see [Racket specs](#racket-specs) | Your own measurements |

If you filled in **Look up**, the next step lists the matching rackets. Pick yours, or leave it empty
to skip. Brand, model, head size and string pattern you left blank come from the dataset.

Repeat for each racket. To change the details or specs later, or to look the racket up later, click
**Configure** on the racket. To rename it, use **⋮ → Reconfigure** (entity IDs keep their names).

### Removing a racket

**Settings → Devices & services → Strung → ⋮ → Delete** on the racket. This deletes
its restring history and photos too. To remove the integration entirely, delete every racket,
then remove it in HACS and restart.

## Logging a restring

### With the form (easiest)

1. Copy [`examples/scripts.yaml`](examples/scripts.yaml) into your `scripts.yaml` (or paste each
   script into the script editor's YAML mode).
2. Run **Log restring** to get a form: racket, date, strings, tensions, cost, stringer, photo and notes.
3. After a few hitting sessions, run **Rate current strings** to add a rating and notes to the latest restring.

The [example dashboard](#dashboard) has a button for each.

### Usual setup

Save the string job you always get under **Configure → Usual setup**: main string and tension, and
optionally crosses, stringer and cost. Then **Restring with usual setup**
(`button.<racket>_restring_with_usual_setup`) logs it for today in one tap. Without a usual setup,
the button repeats the latest restring's strings, tensions, stringer and cost. Rating, notes and
photo are not copied.

`racket_tracker.repeat_restring` does the same from scripts. It also takes `date`, `cost`,
`stringer`, `notes` and `image`, or a `restring_id` to copy a particular past restring.

### With the action

**Developer tools → Actions → Strung: Add restring**, or in YAML:

```yaml
action: racket_tracker.add_restring
data:
  config_entry_id: 01JC...               # pick the racket in the UI
  date: "2026-11-15"                     # optional, defaults to today
  main_string: Solinco Hyper-G 1.25
  main_tension: 52
  cross_string: Babolat VS Touch 1.30    # optional (hybrid); defaults to main_string
  cross_tension: 50                      # optional; defaults to main_tension
  cost: 950                              # in your Home Assistant currency
  stringer: Pro shop
  rating: 4                              # 1–5, optional
  notes: Great spin, a bit stiff for the first 2 hours
  image:                                 # optional, see Photos
    media_content_id: media-source://media_source/local/rackets/aero.jpg
    media_content_type: image/jpeg
```

### Photos

Each restring can have **one photo**.

- In the form, the **Photo** field opens the media browser. Go to **My media**, press **Upload**,
  and choose the photo from your phone or computer.
- In YAML you can also give a file path inside an
  [allowed directory](https://www.home-assistant.io/integrations/homeassistant/#allowlist_external_dirs),
  e.g. `image: /media/rackets/aero.jpg`.
- The photo is **copied** to `<config>/racket_tracker/images/`, so you can delete the original.
- Add or replace a photo later with `update_restring` + `image`; remove it with `remove_image: true`.
- Deleting a restring or a racket deletes its photos.

`image.<racket>_photo` shows the latest restring photo. Every history entry also has an
`image_url` (`/racket_tracker/images/<id>.jpg`) for dashboards.

> **Privacy:** `image_url` links work without logging in, behind a random ID that can't be guessed
> (like files in `/local/`). The `image.*` entity always needs a login.

## Racket specs

Enter what you've measured yourself in the **Specs** section when you add a racket, or later
under **Configure**. Every field is optional, and each one you fill in becomes a sensor:

| Spec | Unit | Sensor |
|---|---|---|
| Strung weight | g | `sensor.<racket>_strung_weight` |
| Unstrung weight | g | `sensor.<racket>_unstrung_weight` |
| Balance | mm from the butt cap | `sensor.<racket>_balance` |
| Swingweight | kg·cm² | `sensor.<racket>_swingweight` |
| Stiffness | RA | `sensor.<racket>_stiffness` |
| Length | in | `sensor.<racket>_length` |
| Recommended tension (min/max) | the racket's tension unit | `sensor.<racket>_recommended_tension_min` / `_max` |

Each spec sensor has a `source` attribute: `measured` for your own values, or `dataset` for
[looked-up values](#looked-up-specs). **Your measurements always win**: clear a field and the sensor
falls back to the dataset value, or disappears if there isn't one.

### Looked-up specs

Type the racket's brand and model under **Look up** when you add it (or later under **Configure**)
and pick it from the matches. Strung then reads its **unstrung weight, balance, swingweight and
stiffness** from the [Racqix Tennis Racquet Dataset](https://www.racqix.com/en/tennis-racquet-dataset)
(about 1,250 rackets from 18 brands, 1998 to 2026).

<p align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/screenshots/lookup-dark.png">
  <img src="images/screenshots/lookup-light.png" alt="Pick your racket: the Pure Aero 2023 variants found by a lookup" width="560">
</picture>
</p>
 Not every racket has every value; swingweight is
listed for roughly 40% of them.

- The list is downloaded from racqix.com only when you search, and kept in memory for a day. Nothing
  about you or your rackets is sent.
- Looked-up sensors have `source: dataset` and credit the dataset in their `attribution`.
- To stop using the dataset values for a racket, turn off **Use looked-up specs** under **Configure**.

## Estimated tension

Tell Strung how much you play a racket (**Play and tension loss**, when adding it or under
**Configure**) and it estimates the tension of the current strings. Strings lose tension in three
ways, and the estimate adds them up:

```text
loss = initial loss                                  first day after stringing
     + relaxation loss × log10(days since stringing)  played or not
     + first-hour loss × log2(1 + hours played)       from play
hours played = hours per week × days ÷ 7              (loss is capped at 50 %)
tension now  = strung tension × (1 − loss)
```

So an idle racket keeps losing a little (the same again each time its age multiplies by 10), and
play costs most in the first hours: each doubling of the hours played costs as much as the first hour.

| Field | Polyester | Nylon / multi | Natural gut |
|---|---|---|---|
| Hours of play per week | required (0 for a spare racket) | | |
| String type | default | | |
| Initial tension loss | 10 % | 6 % | 4 % |
| Loss in the first hour of play | 3 % | 1.5 % | 1 % |
| Loss per tenfold age | 4 % | 2 % | 1.5 % |

Leave the three rates empty to use the string type's values. For a hybrid, pick the mains' type.

Example: polyester strung at 52 lbs two weeks ago, 4 hours a week → 8 hours played:
10 % + 4 % × log10(14) + 3 % × log2(9) = 24 % lost, about **39.5 lbs** now.

**Calibrate it to your strings.** Measure the mains with a stringbed tension meter or app and run
`racket_tracker.calibrate_tension` (racket, measured tension, optional date). All three rates are
scaled by the same factor so the estimate matches your measurement, and saved on the racket.

### History, including backdated restrings

Home Assistant only records a sensor from the moment it changes, so a restring you log late would
show up as a sudden jump. Strung fills in the gap: after every restring you add, edit or delete, it
writes hourly long-term statistics for **Tension** (the strung tension of the restring in effect)
and **Estimated tension** (the estimate for each day), from the first restring up to now (at most
three years). Use a **Statistics graph** card to see it, as the example dashboards do; a History
graph only shows what was recorded live. Rewriting the history uses your current tension settings,
so after calibrating, the past is re-estimated too. Needs the recorder (on by default).

This adds three sensors, updated at midnight and after every restring: **Estimated tension** (in the
racket's unit; `strung_tension`, `estimated_cross_tension` and the rates in use), **Estimated tension
loss** (%) and **Hours played**. Clear the hours to remove them.

### Where the numbers come from

- **Loss grows with log(time) and never stops.** "A plot of tension vs. log(time) is linear after
  the first 100 s, even over a period of several days"
  ([Cross, Lindsey & Andruczyk 2000](https://www.physics.sydney.edu.au/~cross/PUBLICATIONS/14.%20StringTests.PDF)).
  A string clamped at 28 kg read 24.8 kg after 17 minutes, 21.9 kg after 3 days and an extrapolated
  19.1 kg after a year: about **4.3 % of the strung tension per tenfold time**
  ([Cross & Bower 2001](https://www.physics.usyd.edu.au/~cross/PUBLICATIONS/19.%20MeasureStringT.PDF)).
  That is the polyester relaxation rate.
- **Play costs most at first.** "Successive impacts result in successively smaller drops in
  tension", and about half of the drop over ten hard impacts came on the first (Cross & Bower 2001).
  "After using the racket for one or two sets, the tension will drop a further one or two kg"
  from about 20 kg (Cross et al. 2000), roughly 3.5–7 % of the strung tension. A log of hours
  gives that shape. The 3 % first-hour default gives about 9.5 % after 8 hours.
- **Materials.** "Natural gut has one of the lowest rates of tension loss … while all polyester
  strings lose tension rapidly" (Cross et al. 2000). "Polyester loses more than nylon which loses
  more than gut" ([Lindsey, TWU 2013](https://twu.tennis-warehouse.com/learning_center/deadstrings.php)).
  The nylon and gut rates scale polyester's by roughly the ratio of the median losses in
  Tennis Warehouse University's string database: polyester 41 %, nylon 21 %, gut 15 %
  ([summary](https://thetennisindex.com/guides/compendium/string-types)).
- **Initial loss.** Measured against the stringing machine's pull, strings lose much more in the
  first day (28 kg → about 20 kg, Cross et al. 2000), and the racket frame also shortens the
  strings as they go in (Cross & Bower 2001). The 10 % is the loss relative to the freshly strung
  racket, which is what a stringbed meter compares against. Calibrate if your meter disagrees.

**Limits.** These are averages from a few lab strings, not your string in your climate; play
intensity and temperature matter too. And tension isn't the whole story: strings feel "dead"
mostly because the stringbed gets softer and the strings stop sliding back, not because of
tension loss ([Lindsey, TWU 2013](https://twu.tennis-warehouse.com/learning_center/deadstrings.php);
[part 2](https://twu.tennis-warehouse.com/learning_center/deadstringsPart2.php)). For polyester, a
[restring rule](#restring-due) on days or hours of play is often a better trigger than a tension
threshold.

## Restring due

Under **Restring reminder** (when adding the racket or under **Configure**), set one or more rules.
The earliest one wins:

| Rule | Example | Needs |
|---|---|---|
| Restring after (days) | `60` | — |
| Restring after (hours of play) | `40` | Hours of play per week |
| Restring when estimated tension drops to | `44` (the racket's unit) | Hours of play per week |

Then you get:

- `binary_sensor.<racket>_restring_due`: **Due** from the due date on, until you log a restring.
  Attributes: `due_date`, `days_until_due` (negative when overdue) and `reason` (`days`,
  `hours_played` or `min_tension`). It's unknown before the first restring.
- `sensor.<racket>_next_restring`: the due date.
- A **Restring due** event in `calendar.<racket>_restrings`.

Clear the rules to remove the sensors. The [Restring due blueprint](#one-click-blueprints) notifies
you when it turns on.

### Calendar

`calendar.<racket>_restrings` always exists. It has an all-day event for every restring (strings,
tensions, stringer, cost, rating and notes) and, with a rule set, one for the next restring due. Add
it to a **Calendar** card, or use it in calendar triggers. Event text is in English.

## Recipes

### One-click blueprints

Import a blueprint, then create an automation from it and pick your racket's sensor from the
drop-down. For the notify action, enter your phone's, for example `notify.mobile_app_your_phone`.

| Blueprint | What it does | |
|---|---|---|
| 🔔 **Restring due** | Notify when a racket's [Restring due](#restring-due) sensor turns on, and say why | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fkianhean%2Fha-tennis-racket-strings%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fracket_tracker%2Frestring_due.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import the restring_due.yaml blueprint"></a> |
| ⏳ **Restring reminder** | Notify when a racket's strings reach an age you choose (no rules needed) | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fkianhean%2Fha-tennis-racket-strings%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fracket_tracker%2Frestring_reminder.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import the restring_reminder.yaml blueprint"></a> |
| 📸 **Restring logged** | A notification, with the photo, every time a restring is logged (one racket or all) | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fkianhean%2Fha-tennis-racket-strings%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fracket_tracker%2Frestring_logged.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import the restring_logged.yaml blueprint"></a> |
| 🎾 **Racket picker** | Keep a dropdown helper filled with your rackets, for the [multi-racket dashboard](#several-rackets-pick-one-from-a-dropdown) | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fkianhean%2Fha-tennis-racket-strings%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fracket_tracker%2Fracket_picker.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import the racket_picker.yaml blueprint"></a> |
| ⭐ **Rate your strings** | A few days after a restring, remind you to rate it if you haven't | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fkianhean%2Fha-tennis-racket-strings%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fracket_tracker%2Frate_strings.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import the rate_strings.yaml blueprint"></a> |

The blueprints live in [`blueprints/automation/racket_tracker/`](blueprints/automation/racket_tracker)
and need Home Assistant 2025.7 or newer.

### Or copy the YAML

Remind me after 60 days:

```yaml
triggers:
  - trigger: numeric_state
    entity_id: sensor.pure_aero_days_since_restring
    above: 59
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "🎾 Time to restring?"
      message: "{{ states('sensor.pure_aero_strings') }} has been in for {{ states('sensor.pure_aero_days_since_restring') }} days."
```

React to every restring with the `racket_tracker_restrung` event:

```yaml
triggers:
  - trigger: event
    event_type: racket_tracker_restrung
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "Restrung: {{ trigger.event.data.racket }}"
      message: "{{ trigger.event.data.main_string }} @ {{ trigger.event.data.main_tension }} {{ trigger.event.data.tension_unit }}"
      data:
        image: "{{ trigger.event.data.image_url }}"
```

## Dashboard

There's no automatic dashboard: you add the example view yourself. It takes a minute:

1. Add the two scripts from [`examples/scripts.yaml`](examples/scripts.yaml) to your `scripts.yaml`,
   then reload them (**Developer tools → YAML → Scripts**).
2. **Settings → Dashboards → Add dashboard → New dashboard from scratch**, name it *Rackets*, and open it.
3. **✏️ → ⋮ → Raw configuration editor**, replace everything with `views:` and paste the contents of
   [`examples/dashboard.yaml`](examples/dashboard.yaml) indented under `  - `.
4. Replace `pure_aero` with your racket's entity prefix. Remove spec rows or the estimate tiles you
   don't use.

[`examples/dashboard.yaml`](examples/dashboard.yaml) is a complete sections view built only from
Home Assistant's built-in cards:

- the racket photo, current strings, tension, string age, last restrung and total spent
- the estimated tension now and how much has been lost (remove those two tiles if you don't set hours per week)
- **Log restring** and **Rate strings** buttons (they open the script forms), and **Usual setup**,
  which logs your [usual setup](#usual-setup) for today after a confirmation
- a **Schedule** column: Restring due, Next restring and a month calendar of restrings and the next
  one due (remove it if you don't set a [restring rule](#restring-due))
- the current setup's rating and notes, your specs, and tension (strung and estimated) over time,
  in a Statistics graph so [backdated restrings](#history-including-backdated-restrings) show too
- a history table with photo thumbnails, strings, tensions, cost, stars and notes

A test checks that every entity it uses exists. The screenshot at the top is this view in Home
Assistant 2026.9 with example data (the photos are placeholders).

### Several rackets: pick one from a dropdown

[`examples/dashboard_multi.yaml`](examples/dashboard_multi.yaml) is one view for all your rackets.
Pick a racket in the dropdown and the photo, current setup, estimate, next restring and history
follow it. Below that, an **All rackets** table lists every racket with its age, tension and
whether it's due, and a graph shows every racket's estimated tension.

1. **Settings → Devices & services → Helpers → Create helper → Dropdown**, name it `Racket`
   (so it's `input_select.racket`) and give it any one option.
2. Import the [Racket picker blueprint](#one-click-blueprints) and create an automation from it with
   that dropdown. It fills in your rackets and keeps them up to date as you add, rename or delete one.
3. Add the scripts from [`examples/scripts.yaml`](examples/scripts.yaml) (**Usual setup** uses
   `restring_selected_racket`), then paste the view like the one above.

New rackets show up in the dropdown and the table by themselves. Only the graph lists rackets by
name, because Home Assistant's graph cards can't follow a dropdown: add a line for each racket.
Tests render every card with two rackets.

<p align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/screenshots/dashboard-multi-dark.png">
  <img src="images/screenshots/dashboard-multi-light.png" alt="The multi-racket view: a Racket dropdown set to Blade with its photo, strings, estimate and a Restring due warning; an All rackets table; a graph of both rackets' estimated tension since June; and Blade's restring history" width="800">
</picture>
</p>

A minimal history card:

```yaml
type: markdown
content: >
  {% for r in state_attr('sensor.pure_aero_restrings', 'history') or [] %}
  **{{ r.date }}**: {{ r.main_string }}{% if r.cross_string != r.main_string %} / {{ r.cross_string }}{% endif %}
  @ {{ r.main_tension }} {{ r.tension_unit }} {{ '⭐' * (r.rating or 0) }}
  {% if r.image_url %}<img src="{{ r.image_url }}" width="80">{% endif %}
  {{ r.notes or '' }}

  {% endfor %}
```

## Entity reference

Entity IDs are built from the racket name: `Pure Aero` → `sensor.pure_aero_*`.

| Entity | State | Attributes |
|---|---|---|
| `sensor.<racket>_strings` | `Hyper-G 1.25 / VS Touch 1.30` | `restring_id`, `date`, `main_string`, `cross_string`, `main_tension`, `cross_tension`, `stringer`, `rating`, `cost`, `notes`, `image_url` |
| `sensor.<racket>_tension` | `52` lbs | `cross_tension`. Has long-term statistics |
| `sensor.<racket>_last_restrung` | `2026-11-15` | |
| `sensor.<racket>_days_since_restring` | `12` d | Updated at midnight |
| `sensor.<racket>_restrings` | `7` | `history`: every restring, newest first (not stored in the recorder) |
| `sensor.<racket>_total_string_cost` | `6650` (your currency) | `average_cost` |
| `sensor.<racket>_estimated_tension` | `39.5` lbs | `strung_tension`, `strung_cross_tension`, `estimated_cross_tension`, `date`, `string_type` and rates. Only with [hours per week](#estimated-tension) |
| `sensor.<racket>_estimated_tension_loss` | `24` % | play settings |
| `sensor.<racket>_hours_played` | `8` h | Since the latest restring |
| `sensor.<racket>_next_restring` | `2027-01-14` | Only with a [restring rule](#restring-due) |
| `binary_sensor.<racket>_restring_due` | on (Due) / off | `due_date`, `days_until_due`, `reason`. Only with a restring rule |
| `calendar.<racket>_restrings` | on during a restring / due day | Events: every restring and the next one due |
| `button.<racket>_restring_with_usual_setup` | time last pressed | Logs the [usual setup](#usual-setup) for today |
| `image.<racket>_photo` | time of the latest photo | `restring_id`, `date` |
| `sensor.<racket>_<spec>` | see [Racket specs](#racket-specs) | `source`: `measured` / `dataset` |

### Actions

| Action | What it does | Response |
|---|---|---|
| `racket_tracker.add_restring` | Log a restring | Optional: the new restring, including its `id` |
| `racket_tracker.calibrate_tension` | Scale the tension estimate to a measured mains tension | Optional: the new rates |
| `racket_tracker.repeat_restring` | Log a restring with the usual setup, or copy a past one (`restring_id`) | Optional: the new restring |
| `racket_tracker.update_restring` | Change any field; add, replace or remove the photo. **Leave `restring_id` empty to edit the latest restring.** | Optional: the updated restring |
| `racket_tracker.delete_restring` | Delete a restring and its photo | — |
| `racket_tracker.get_history` | The whole history | `racket`, `specs`, `restring_count`, `total_cost`, `restrings[]` |

Restring IDs are in the `history` attribute and in the action responses.

### Event

`racket_tracker_restrung` fires after every `add_restring`, `repeat_restring` and button press. Its data has `config_entry_id`, `racket`
and every restring field, including `image_url`.

## Troubleshooting

- **"Couldn't use that image"**: pick the photo from **My media** (local media), or give a path
  inside `allowlist_external_dirs`. Photos must be under 20 MB.
- **The specs section or photo field is missing**: update to Home Assistant 2025.7 or newer.
- **Something looks wrong**: on the racket, **⋮ → Download diagnostics** gives its options,
  specs and full history. Attach it to an [issue](https://github.com/kianhean/ha-tennis-racket-strings/issues).

## Development

```bash
pip install -r requirements_test.txt
pytest
ruff check custom_components/ tests/ && ruff format custom_components/ tests/
```

Every test loads the integration into a real Home Assistant (via
`pytest-homeassistant-custom-component`). CI runs them on the minimum supported version (2025.7),
current stable and the newest beta. They cover the config and options flows (including over HTTP),
every action, photos, specs, the sensors, the blueprints, the example scripts and dashboard, and
the translations.

Releases are automatic: bump `version` in `custom_components/racket_tracker/manifest.json` in your
PR, and merging to `main` creates the GitHub release and the `racket_tracker.zip` that HACS installs.

## Contributing

Issues and PRs are welcome. Please keep `strings.json` and `translations/en.json` in sync (a test
checks this), add tests for new behaviour, and bump the manifest version.

## License

[MIT](LICENSE)
