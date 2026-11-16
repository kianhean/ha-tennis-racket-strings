"""scripts/update_dataset.py keeps the bundled Racqix copy fresh, safely."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from custom_components.racket_tracker import dataset as integration_dataset

SCRIPT = Path(__file__).parent.parent / "scripts" / "update_dataset.py"
BUNDLED = Path(__file__).parent.parent / "custom_components/racket_tracker"


def _racquet(slug: str) -> dict[str, Any]:
    return {
        "slug": slug,
        "brand": "Babolat",
        "model": "Pure Aero",
        "year": "2027",
        "weight": 300,
        "swingweight": 320,
        "ra": 68,
        "balance_mm": 320,
        "head_size": 100,
        "string_pattern": "16x19",
    }


def _payload(version: str = "2027.1", count: int = 1250) -> dict[str, Any]:
    return {
        "dataset_version": version,
        "last_updated": "2027-03-01",
        "total_racquets": count,
        "racquets": [_racquet(f"racquet-{i}") for i in range(count)],
    }


# A bot challenge or a cut-off response: right version, far too few rackets
PARTIAL = {**_payload(), "racquets": _payload(count=10)["racquets"]}
NO_VERSION = {k: v for k, v in _payload().items() if k != "dataset_version"}


@pytest.fixture(name="update")
def update_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[ModuleType, dict[str, str]]]:
    """The script, pointing at a temporary copy of the bundled files.

    Network: a URL whose body is in the second item is served; any other URL is
    answered with a 429, like Racqix's bot protection does.
    """
    spec = importlib.util.spec_from_file_location("update_dataset", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    component = tmp_path / "custom_components" / "racket_tracker"
    component.mkdir(parents=True)
    for name in ("racqix_dataset.json", "racqix_dataset.NOTICE.md"):
        (component / name).write_bytes((BUNDLED / name).read_bytes())
    monkeypatch.setattr(module, "DATASET_FILE", component / "racqix_dataset.json")
    monkeypatch.setattr(module, "NOTICE_FILE", component / "racqix_dataset.NOTICE.md")
    monkeypatch.setattr(module, "TIMEOUT", 0.001)  # freezegun runs out a sleep
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    served: dict[str, str] = {}

    def _get(url: str) -> str:
        if url not in served:
            raise module.Refused(f"{url} answered 429")
        return served[url]

    monkeypatch.setattr(module, "_get", _get)
    yield module, served


def _api_refused(module: ModuleType, served: dict[str, str]) -> Any:
    """Answer the page from `served`; the API always gets a 429."""

    def _get(url: str) -> str:
        if url == module.DATASET_URL or url not in served:
            raise module.Refused(f"{url} answered 429")
        return served[url]

    return _get


def _run(module: ModuleType, *args: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = module.main(list(args))
    return status, out.getvalue()


def test_bundled_file_is_what_the_script_reads(
    update: tuple[ModuleType, dict[str, str]],
) -> None:
    """The version the script reports is the one the integration searches."""
    module, _ = update
    payload = json.loads(integration_dataset.BUNDLED_FILE.read_text(encoding="utf-8"))
    assert module.bundled_version() == payload["dataset_version"]
    assert module._usable(payload)
    assert integration_dataset._parse(payload, None) is not None


def test_replace_updates_file_and_notice(
    update: tuple[ModuleType, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A download replaces the copy and its notice, unmodified and dated."""
    module, served = update
    payload = _payload()
    served[module.DATASET_URL] = json.dumps(payload)
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1803945600")  # 2027-03-02, UTC

    status, out = _run(module)
    assert status == 0, out
    assert json.loads(module.DATASET_FILE.read_text(encoding="utf-8")) == payload
    notice = module.NOTICE_FILE.read_text(encoding="utf-8")
    assert "version 2027.1 (last updated 2027-03-01), by Racqix:" in notice
    assert "served on 2027-03-02." in notice
    # The rest of the notice is left as it was
    assert "served on 2026-11-16" not in notice
    assert "Creative Commons Attribution-NonCommercial-NoDerivatives 4.0" in notice
    assert "Do not edit it" in notice


def test_refused_download_keeps_the_bundled_file(
    update: tuple[ModuleType, dict[str, str]],
) -> None:
    """A 429 is never written, whichever URL it comes from."""
    module, served = update
    before = module.DATASET_FILE.read_bytes(), module.NOTICE_FILE.read_bytes()

    status, out = _run(module)
    assert status == 1
    assert "left unchanged" in out
    assert (module.DATASET_FILE.read_bytes(), module.NOTICE_FILE.read_bytes()) == before


@pytest.mark.parametrize(
    "body",
    [
        "not json at all",
        json.dumps({"dataset_version": "2027.1", "racquets": []}),
        json.dumps(PARTIAL),
        json.dumps(NO_VERSION),
    ],
)
def test_incomplete_response_is_not_written(
    update: tuple[ModuleType, dict[str, str]], body: str
) -> None:
    """A partial list from either URL is refused rather than saved."""
    module, served = update
    before = module.DATASET_FILE.read_bytes()
    served[module.DATASET_URL] = body
    served[module.WEB_URL] = "<html><body>blocked</body></html>"

    status, out = _run(module)
    assert status == 1
    assert "left unchanged" in out
    assert module.DATASET_FILE.read_bytes() == before


def test_api_refused_falls_back_to_the_page(
    update: tuple[ModuleType, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The page still carries the data when the API itself is blocked."""
    module, served = update
    payload = _payload()
    # The API refuses (nothing served for it); the page has the list
    monkeypatch.setattr(module, "_get", _api_refused(module, served))
    served[module.WEB_URL] = (
        f'<html><script id="__NEXT_DATA__">{json.dumps(payload)}</script></html>'
    )
    assert module.download() == payload


def test_check_reports_a_new_version(update: tuple[ModuleType, dict[str, str]]) -> None:
    module, served = update
    served[module.WEB_URL] = json.dumps({"props": {"dataset_version": "2027.1"}})
    status, out = _run(module, "--check")
    assert status == 1
    assert "refresh due" in out


def test_check_up_to_date(update: tuple[ModuleType, dict[str, str]]) -> None:
    module, served = update
    version = module.bundled_version()
    served[module.WEB_URL] = f'<html>"dataset_version":"{version}"</html>'
    status, out = _run(module, "--check")
    assert status == 0
    assert "up to date" in out


def test_check_that_cannot_reach_racqix_is_not_stale(
    update: tuple[ModuleType, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not knowing must neither open a pull request nor look like success."""
    module, _ = update
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    status, out = _run(module, "--check")
    assert status == 2
    assert "Racqix refused" in out


def test_refused_mode_succeeds_once_reachable(
    update: tuple[ModuleType, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A scheduled job only records whether Racqix answers, with retries."""
    module, served = update
    page = '"dataset_version":"2027.1"'
    calls: list[str] = []

    def _get(url: str) -> str:
        calls.append(url)
        if len(calls) > 1:
            return page
        raise module.Refused(f"{url} answered 429")  # the first try is refused

    monkeypatch.setattr(module, "_get", _get)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    status, _ = _run(module, "--refused")
    assert status == 0 and len(calls) == 2
