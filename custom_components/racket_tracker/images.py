"""Photo handling: one image per restring, copied into the integration's folder."""

from __future__ import annotations

import mimetypes
import re
import shutil
from datetime import timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from aiohttp import web
from homeassistant.components import media_source
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.http import HomeAssistantView

from .const import DOMAIN

IMAGE_URL_PREFIX = f"/api/{DOMAIN}/images"
# Signed photo URLs work without an Authorization header (for <img> tags) for this
# long, or until HA restarts. The sensors sign theirs again every midnight.
IMAGE_URL_LIFETIME = timedelta(days=2)
MAX_IMAGE_BYTES = 20 * 1024 * 1024
# Stored names are <restring_id><ext>; anything else is never served
_IMAGE_NAME = re.compile(r"^[0-9a-f]{12}\.[a-z0-9]{2,5}$")


def image_dir(hass: HomeAssistant) -> Path:
    """Folder where restring photos are kept (<config>/racket_tracker/images)."""
    return Path(hass.config.path(DOMAIN, "images"))


def image_url(hass: HomeAssistant, filename: str | None) -> str | None:
    """Signed URL of a stored photo, valid for IMAGE_URL_LIFETIME.

    Signed for HA's content user rather than whoever happens to be calling, so a
    URL in a state attribute doesn't depend on (or reveal) one user's login.
    """
    if not filename:
        return None
    return async_sign_path(
        hass,
        f"{IMAGE_URL_PREFIX}/{filename}",
        IMAGE_URL_LIFETIME,
        use_content_user=True,
    )


class RacketImageView(HomeAssistantView):
    """Serve restring photos to logged-in users (or with a signed URL)."""

    url = IMAGE_URL_PREFIX + "/{filename}"
    name = f"api:{DOMAIN}:images"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        """Serve photos from the integration's image folder."""
        self._hass = hass
        self._folder = image_dir(hass)

    async def get(self, request: web.Request, filename: str) -> web.StreamResponse:
        """Return one photo."""
        if not _IMAGE_NAME.fullmatch(filename):
            return web.Response(status=HTTPStatus.NOT_FOUND)
        path = self._folder / filename
        if not await self._hass.async_add_executor_job(path.is_file):
            return web.Response(status=HTTPStatus.NOT_FOUND)
        return web.FileResponse(
            path,
            headers={
                "Cache-Control": "private, max-age=3600",
                "Content-Type": image_content_type(filename),
            },
        )


def image_content_type(filename: str) -> str:
    """Guess the MIME type of a stored photo."""
    return mimetypes.guess_type(filename)[0] or "image/jpeg"


def _invalid(reason: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="invalid_image",
        translation_placeholders={"reason": reason},
    )


def _local_media_path(hass: HomeAssistant, url: str) -> Path | None:
    """Map a /media/<dir>/<file> URL to its file (PlayMedia.path is HA 2025.6+)."""
    if not url.startswith("/media/"):
        return None
    dir_id, _, location = unquote(url.removeprefix("/media/").split("?")[0]).partition(
        "/"
    )
    if (base := hass.config.media_dirs.get(dir_id)) is None:
        return None
    root = Path(base).resolve()
    path = (root / location).resolve()
    return path if path.is_relative_to(root) else None


async def _async_source_path(hass: HomeAssistant, source: Any) -> Path:
    """Turn a media selector value, media-source ID or file path into a local path."""
    if isinstance(source, dict):
        source = source.get("media_content_id")
    if not isinstance(source, str) or not source:
        raise _invalid("no image selected")

    if media_source.is_media_source_id(source):
        try:
            play = await media_source.async_resolve_media(hass, source, None)
        except HomeAssistantError as err:
            raise _invalid(str(err)) from err
        if (
            path := getattr(play, "path", None) or _local_media_path(hass, play.url)
        ) is None:
            raise _invalid("pick an image from 'My media' (local media)")
        return Path(path)

    path = Path(source)
    if not hass.config.is_allowed_path(str(path)):
        raise _invalid(
            f"{path} is not in an allowed folder (see allowlist_external_dirs)"
        )
    return path


async def async_import_image(hass: HomeAssistant, source: Any, restring_id: str) -> str:
    """Copy a photo into storage for a restring. Returns the stored file name."""
    src = await _async_source_path(hass, source)
    mime = mimetypes.guess_type(src.name)[0] or ""
    if not mime.startswith("image/"):
        raise _invalid(f"{src.name} is not an image")
    ext = mimetypes.guess_extension(mime) or src.suffix or ".jpg"
    if ext == ".jpe":
        ext = ".jpg"
    dest_dir = image_dir(hass)
    filename = f"{restring_id}{ext}"

    def _copy() -> None:
        if not src.is_file():
            raise _invalid(f"{src} not found")
        if src.stat().st_size > MAX_IMAGE_BYTES:
            raise _invalid("image is larger than 20 MB")
        dest_dir.mkdir(parents=True, exist_ok=True)
        for old in dest_dir.glob(f"{restring_id}.*"):
            old.unlink(missing_ok=True)
        shutil.copyfile(src, dest_dir / filename)

    await hass.async_add_executor_job(_copy)
    return filename


async def async_delete_image(hass: HomeAssistant, filename: str | None) -> None:
    """Remove a stored photo."""
    if not filename:
        return
    path = image_dir(hass) / Path(filename).name
    await hass.async_add_executor_job(lambda: path.unlink(missing_ok=True))


async def async_read_image(hass: HomeAssistant, filename: str) -> bytes | None:
    """Read a stored photo."""
    path = image_dir(hass) / Path(filename).name

    def _read() -> bytes | None:
        return path.read_bytes() if path.is_file() else None

    return await hass.async_add_executor_job(_read)
