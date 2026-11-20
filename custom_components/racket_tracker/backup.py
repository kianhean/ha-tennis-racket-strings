"""Full backup and restore of Strung rackets (JSON + photos in a single .zip).

Backups are written to <config>/racket_tracker/exports/ (never served over HTTP)
and include every racket's options, restring history, play sessions and photos.
Restoring reads a backup from the exports folder or an allowed folder
(allowlist_external_dirs), skips restrings/sessions already present, and copies
missing photo files into <config>/racket_tracker/images/.
"""

from __future__ import annotations

import json
import re
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DATE,
    ATTR_HOURS,
    ATTR_IMAGE,
    ATTR_MAIN_STRING,
    ATTR_MAIN_TENSION,
    ATTR_NOTES,
    DOMAIN,
)
from .history_io import export_dir
from .images import MAX_IMAGE_BYTES, image_dir

BACKUP_VERSION = 1
MAX_BACKUP_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".avif"}
_SAFE_IMAGE = re.compile(r"^[A-Za-z0-9_-]{1,64}\.[a-z]{2,5}$")


def _error(key: str, **placeholders: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders=placeholders,
    )


async def async_export_backup(
    hass: HomeAssistant,
    entries: Iterable[Any],
    name: str,
) -> dict[str, Any]:
    """Write a .zip backup of the given racket entries and return a summary."""
    stamp = dt_util.now().strftime("%Y%m%d-%H%M%S")
    slug = "-".join(re.findall(r"[a-z0-9]+", name.lower())) or "all-rackets"
    out_path = export_dir(hass) / f"strung-backup-{slug}-{stamp}.zip"
    img_root = image_dir(hass)

    rackets_payload: list[dict[str, Any]] = []
    photo_files: set[str] = set()
    total_restrings = 0
    total_sessions = 0

    for entry in entries:
        history = entry.runtime_data
        restrings = [dict(r) for r in history.restrings]
        sessions = [dict(s) for s in history.sessions]
        calibrations = [dict(c) for c in history.calibrations]
        total_restrings += len(restrings)
        total_sessions += len(sessions)
        for rec in restrings:
            if (img := rec.get(ATTR_IMAGE)) and isinstance(img, str):
                photo_files.add(img)
        rackets_payload.append(
            {
                "title": entry.title,
                "entry_id": entry.entry_id,
                "options": dict(entry.options),
                "restrings": restrings,
                "sessions": sessions,
                "calibrations": calibrations,
            }
        )

    manifest = {
        "version": BACKUP_VERSION,
        "exported_at": dt_util.utcnow().isoformat(),
        "rackets": rackets_payload,
    }

    def _write_zip() -> int:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        written_photos = 0
        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("backup.json", json.dumps(manifest, indent=2))
            for filename in sorted(photo_files):
                if not _SAFE_IMAGE.match(filename):
                    continue
                src = img_root / filename
                if src.is_file():
                    zf.write(src, f"images/{filename}")
                    written_photos += 1
        return written_photos

    photos_written = await hass.async_add_executor_job(_write_zip)
    return {
        "file": str(out_path),
        "rackets": len(rackets_payload),
        "restrings": total_restrings,
        "play_sessions": total_sessions,
        "photos": photos_written,
    }


def _read_backup_zip(
    path: Path, file_label: str
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Read and validate backup.json and image payloads from a zip file."""
    if not path.is_file():
        raise _error("import_file", file=file_label, reason="not found")
    if path.stat().st_size > MAX_BACKUP_BYTES:
        raise _error("import_file", file=file_label, reason="larger than 50 MB")
    try:
        with zipfile.ZipFile(path, "r") as zf:
            if "backup.json" not in zf.namelist():
                raise _error("backup_invalid", reason="missing backup.json")
            raw = zf.read("backup.json")
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("rackets"), list):
                raise _error("backup_invalid", reason="invalid backup.json format")
            images: dict[str, bytes] = {}
            for member in zf.infolist():
                if member.is_dir() or not member.filename.startswith("images/"):
                    continue
                basename = member.filename[len("images/") :]
                if (
                    "/" in basename
                    or "\\" in basename
                    or not _SAFE_IMAGE.match(basename)
                ):
                    continue
                if Path(basename).suffix.lower() not in ALLOWED_EXTENSIONS:
                    continue
                if member.file_size > MAX_IMAGE_BYTES:
                    continue
                images[basename] = zf.read(member.filename)
            return data, images
    except zipfile.BadZipFile as err:
        raise _error("backup_invalid", reason="not a valid zip file") from err
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise _error("backup_invalid", reason="corrupted backup.json") from err


async def async_import_backup(
    hass: HomeAssistant,
    file: str,
    target_entries: list[Any],
    explicit_target: bool = False,
) -> dict[str, Any]:
    """Restore restrings, play sessions and photos from a .zip backup."""
    path = Path(file)
    exports = export_dir(hass).resolve()
    if not (
        path.resolve().is_relative_to(exports) or hass.config.is_allowed_path(str(path))
    ):
        raise _error("import_file", file=file, reason="not in an allowed folder")

    data, images = await hass.async_add_executor_job(_read_backup_zip, path, file)
    backup_rackets: list[dict[str, Any]] = [
        r for r in data["rackets"] if isinstance(r, dict)
    ]

    entries_by_title = {e.title.strip().lower(): e for e in target_entries}
    imported_restrings = 0
    skipped_restrings = 0
    imported_sessions = 0
    skipped_sessions = 0
    restored_photos = 0
    matched_rackets = 0

    img_root = image_dir(hass)
    photos_to_write: dict[str, bytes] = {}

    for b_racket in backup_rackets:
        title = str(b_racket.get("title") or "").strip()
        if explicit_target and len(target_entries) == 1:
            if (
                len(backup_rackets) == 1
                or title.lower() == target_entries[0].title.strip().lower()
            ):
                entry = target_entries[0]
            else:
                continue
        else:
            entry = entries_by_title.get(title.lower())
            if entry is None:
                continue

        matched_rackets += 1
        history = entry.runtime_data

        # Restrings (skip duplicates by id or date + main_string + main_tension)
        existing_ids = {r["id"] for r in history.restrings}
        existing_keys = {
            (
                r.get(ATTR_DATE),
                str(r.get(ATTR_MAIN_STRING, "")).lower(),
                r.get(ATTR_MAIN_TENSION),
            )
            for r in history.restrings
        }
        to_add_restrings: list[dict[str, Any]] = []
        for rec in b_racket.get("restrings") or []:
            if not isinstance(rec, dict):
                continue
            key = (
                rec.get(ATTR_DATE),
                str(rec.get(ATTR_MAIN_STRING, "")).lower(),
                rec.get(ATTR_MAIN_TENSION),
            )
            rec_id = rec.get("id")
            if (rec_id and rec_id in existing_ids) or key in existing_keys:
                skipped_restrings += 1
                continue
            clean_rec = {k: v for k, v in rec.items() if k != "image_url"}
            img_name = clean_rec.get(ATTR_IMAGE)
            if isinstance(img_name, str) and img_name in images:
                photos_to_write[img_name] = images[img_name]
            elif img_name is not None:
                # Photo file not in zip; keep only if already on disk
                if not (img_root / str(img_name)).is_file():
                    clean_rec.pop(ATTR_IMAGE, None)
            if rec_id:
                existing_ids.add(rec_id)
            existing_keys.add(key)
            to_add_restrings.append(clean_rec)

        if to_add_restrings:
            imported_restrings += await history.async_add_many(to_add_restrings)

        # Play sessions (skip duplicates by id or date + hours + notes)
        sess_ids = {s["id"] for s in history.sessions}
        sess_keys = {
            (s.get(ATTR_DATE), float(s.get(ATTR_HOURS, 0)), s.get(ATTR_NOTES) or "")
            for s in history.sessions
        }
        to_add_sessions: list[dict[str, Any]] = []
        for sess in b_racket.get("sessions") or []:
            if not isinstance(sess, dict):
                continue
            s_key = (
                sess.get(ATTR_DATE),
                float(sess.get(ATTR_HOURS, 0)),
                sess.get(ATTR_NOTES) or "",
            )
            s_id = sess.get("id")
            if (s_id and s_id in sess_ids) or s_key in sess_keys:
                skipped_sessions += 1
                continue
            if s_id:
                sess_ids.add(s_id)
            sess_keys.add(s_key)
            to_add_sessions.append(dict(sess))

        if to_add_sessions:
            imported_sessions += await history.async_add_sessions(to_add_sessions)

        # Calibrations (skip duplicates by id)
        cal_ids = {c["id"] for c in history.calibrations}
        to_add_cals = [
            dict(c)
            for c in (b_racket.get("calibrations") or [])
            if isinstance(c, dict) and c.get("id") not in cal_ids
        ]
        if to_add_cals:
            await history.async_add_calibrations(to_add_cals)

    if photos_to_write:

        def _write_photos() -> int:
            img_root.mkdir(parents=True, exist_ok=True)
            count = 0
            for filename, payload in photos_to_write.items():
                dest = img_root / filename
                if not dest.exists():
                    dest.write_bytes(payload)
                    count += 1
            return count

        restored_photos = await hass.async_add_executor_job(_write_photos)

    return {
        "rackets_matched": matched_rackets,
        "imported_restrings": imported_restrings,
        "skipped_restrings": skipped_restrings,
        "imported_sessions": imported_sessions,
        "skipped_sessions": skipped_sessions,
        "restored_photos": restored_photos,
    }
