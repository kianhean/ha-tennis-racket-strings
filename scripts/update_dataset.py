"""Refresh the Racqix list bundled with the integration.

custom_components/racket_tracker/racqix_dataset.json is only searched when a
download isn't available, and an install that never gets one uses it for as long
as it runs. It is an unmodified copy of what Racqix serves (CC BY-NC-ND 4.0), so
this script replaces it with a fresh download and moves the "served on" date in
racqix_dataset.NOTICE.md with it.

Racqix's bot protection sometimes answers with a 429 challenge. Then a refused
response is never written: the file is left as it is and the script exits 1.

    python scripts/update_dataset.py             # download and replace
    python scripts/update_dataset.py --check     # exit 1 when the bundled copy is old
    python scripts/update_dataset.py --refused   # exit 1 when Racqix refuses us

--check only compares versions, because the list changes about once a year, and
--refused retries a few times before giving up. Both are meant for a scheduled
run: a day Racqix refuses to answer isn't a reason to update the file or to fail
a build.

Only the standard library is used, so CI doesn't have to install anything. With
SOURCE_DATE_EPOCH set, that date is recorded instead of today's.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "racket_tracker"
DATASET_FILE = COMPONENT / "racqix_dataset.json"
NOTICE_FILE = COMPONENT / "racqix_dataset.NOTICE.md"

DATASET_URL = "https://www.racqix.com/api/racquets?mode=minimal"
WEB_URL = "https://www.racqix.com/en/tennis-racquet-dataset"
TIMEOUT = 30
RETRIES = 3

# What a usable download looks like (dataset._parse also needs the list itself)
MIN_RACQUETS = 1000
_VERSION = re.compile(r'"?dataset_version"?\s*[:=]\s*"?(\d{4}\.\d+)')
_SERVED_ON = re.compile(r"served on \d{4}-\d{2}-\d{2}\.")


class Refused(Exception):
    """Racqix's bot protection answered instead of the list."""


def _get(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, text/html;q=0.9",
            # Racqix's bot protection is friendlier to a named client
            "User-Agent": "Strung-dataset-updater (+https://github.com/kianhean/ha-tennis-racket-strings)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        if err.code in (403, 429):
            raise Refused(f"{url} answered {err.code}") from err
        raise


def _json(text: str) -> Any:
    """The JSON in a body: the API's payload, or data embedded in the page."""
    try:
        return json.loads(text)
    except ValueError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except ValueError:
            pass
    return None


def _usable(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("racquets"), list)
        and bool(payload.get("dataset_version"))
        and len(payload["racquets"]) >= MIN_RACQUETS
    )


def bundled_version() -> str | None:
    text = DATASET_FILE.read_text(encoding="utf-8")
    return _version(text)


def _version(text: str) -> str | None:
    match = _VERSION.search(text)
    return match.group(1) if match else None


def download() -> dict[str, Any] | None:
    """The current list, or None when Racqix answered with something unusable."""
    try:
        payload = _json(_get(DATASET_URL))
    except Refused:
        payload = None
    if _usable(payload):
        return payload
    # When the API is blocked, the page still lists the data (and raises Refused
    # itself when that is blocked too)
    payload = _json(_get(WEB_URL))
    return payload if _usable(payload) else None


def live_version() -> str:
    """Racqix's current version, from the page (smaller than the full list)."""
    page = _get(WEB_URL)
    if payload := _json(page):
        for value in json.dumps(payload).split(","):
            if version := _VERSION.search(value):
                return version.group(1)
    if version := _version(page):
        return version
    raise Refused("no dataset version on the page")


def _today() -> str:
    epoch = os.environ.get("SOURCE_DATE_EPOCH", "")
    if epoch.isdigit():
        return datetime.fromtimestamp(int(epoch), timezone.utc).date().isoformat()
    return date.today().isoformat()


def _write_notice(payload: dict[str, Any], served: str) -> None:
    """Version, last update and served-on date, for the copy just written."""
    version = f"version {payload['dataset_version']}"
    if payload.get("last_updated"):
        version += f" (last updated {payload['last_updated']})"
    lines = NOTICE_FILE.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith("Racqix Tennis Racquet Dataset, version"):
            lines[index] = f"Racqix Tennis Racquet Dataset, {version}, by Racqix:"
        elif "served on " in line:
            lines[index] = _SERVED_ON.sub(f"served on {served}.", line)
    NOTICE_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _retrying(check: Any) -> int:
    for attempt in range(RETRIES):
        try:
            check()
        except Refused as err:
            print(f"Racqix refused ({err}); retrying" if attempt + 1 < RETRIES else err)
            time.sleep(5 * (attempt + 1))
        else:
            return 0
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="is the bundled copy old?")
    mode.add_argument("--refused", action="store_true", help="does Racqix refuse us?")
    args = parser.parse_args(argv)

    current = bundled_version()
    print(f"bundled: {current or 'unreadable'}")
    if args.check:
        live: list[str] = []
        if _retrying(lambda: live.append(live_version())):
            return 2  # can't tell either way, which mustn't look like "old"
        print(f"live: {live[0]}")
        if live[0] == current:
            print("up to date")
            return 0
        print(f"refresh due: bundled {current}, Racqix {live[0]}")
        return 1
    if args.refused:
        return _retrying(live_version)

    try:
        payload = download()
    except Refused as err:
        print(f"{err}; {DATASET_FILE.name} left unchanged")
        return 1
    except (OSError, urllib.error.URLError) as err:
        print(f"Couldn't download the list ({err}); {DATASET_FILE.name} left unchanged")
        return 1
    if payload is None:
        print(f"Unexpected response; {DATASET_FILE.name} left unchanged")
        return 1
    served = _today()
    DATASET_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    _write_notice(payload, served)
    print(
        f"wrote {payload['dataset_version']} ({len(payload['racquets'])} rackets, "
        f"served {served})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
