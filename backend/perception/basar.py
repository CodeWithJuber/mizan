"""Basar (بَصَر, sight): images in a chat, prepared on MIZAN's server and shown to the model.

An image the user attaches is decoded with Pillow; only PNG, JPEG, WebP and GIF
are accepted, a GIF as its first frame. Re-encoding drops its metadata (EXIF:
the camera, the time and often the GPS position where the photo was taken), and
it is scaled down to at most 1568 px on its longer side, beyond which the
models see no more detail and only cost more. It is kept per user with the chat
(shown again in the history, erased with the chat by Mahw), and for the turn it
was sent in, and the turn right after, it is given to the model as an image.

Text inside an image is outside content, like a web page: the run is tainted
(Amanah), so an action the model chooses that changes something needs approval.
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

MAX_IMAGES = 4
MAX_BYTES = 10 * 1024 * 1024  # an attached file, before preparing
MAX_PIXELS = 40_000_000  # refuse decompression bombs before decoding them
MAX_SIDE = 1568
FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}
_SHA = re.compile(r"^[0-9a-f]{64}$")


class ImageError(ValueError):
    """An attachment that is not an image MIZAN can read."""


@dataclass(frozen=True)
class Image:
    sha: str
    media_type: str
    width: int
    height: int
    data: bytes

    def meta(self) -> dict:
        return {
            "sha": self.sha,
            "media_type": self.media_type,
            "width": self.width,
            "height": self.height,
        }

    def block(self) -> dict:
        """The image as a content block of a model request (Anthropic's form,
        which MIZAN's other providers translate)."""
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": self.media_type,
                "data": base64.b64encode(self.data).decode(),
            },
        }


def prepare(raw: bytes) -> Image:
    """Decode, check and re-encode one attached image."""
    if not raw or len(raw) > MAX_BYTES:
        raise ImageError(f"An image must be at most {MAX_BYTES // (1024 * 1024)} MB")
    from PIL import Image as Pillow
    from PIL import UnidentifiedImageError

    Pillow.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Pillow.open(io.BytesIO(raw)) as opened:
            kind = opened.format or ""
            if kind not in FORMATS:
                raise ImageError("Only PNG, JPEG, WebP and GIF images can be read")
            opened.seek(0)  # a GIF: its first frame
            picture = opened.convert("RGBA" if _has_alpha(opened) else "RGB")
    except (UnidentifiedImageError, OSError, Pillow.DecompressionBombError) as exc:
        raise ImageError("This file is not an image MIZAN can read") from exc
    picture.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    if picture.mode == "RGBA":
        picture.save(out, format="PNG", optimize=True)
        media_type = "image/png"
    else:
        picture.save(out, format="JPEG", quality=90, optimize=True)
        media_type = "image/jpeg"
    data = out.getvalue()
    return Image(hashlib.sha256(data).hexdigest(), media_type, picture.width, picture.height, data)


def _has_alpha(picture) -> bool:
    return picture.mode in {"RGBA", "LA", "PA"} or (
        picture.mode == "P" and "transparency" in picture.info
    )


def decode(data: str) -> bytes:
    """An attachment sent as base64 (with or without a ``data:`` prefix)."""
    body = data.split(",", 1)[1] if data.startswith("data:") else data
    try:
        return base64.b64decode(body, validate=True)
    except (ValueError, TypeError) as exc:
        raise ImageError("The image is not valid base64") from exc


# ── kept per user ───────────────────────────────────────────────────────


def _root(owner: str) -> Path:
    folder = hashlib.sha256((owner or "anonymous").encode()).hexdigest()[:24]
    return Path(os.getenv("MIZAN_DATA_DIR", "/data/mizan")) / "media" / folder


def _path(owner: str, sha: str, media_type: str) -> Path:
    return _root(owner) / f"{sha}.{'png' if media_type == 'image/png' else 'jpg'}"


def store(owner: str, image: Image) -> None:
    path = _path(owner, image.sha, image.media_type)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(image.data)


def load(owner: str, sha: str) -> Image | None:
    """One of the user's own kept images; another user's never resolves."""
    if not _SHA.match(sha or ""):
        return None
    for media_type in ("image/jpeg", "image/png"):
        path = _path(owner, sha, media_type)
        if path.exists():
            data = path.read_bytes()
            return Image(sha, media_type, 0, 0, data)
    return None


def erase(owner: str, shas: Sequence[str]) -> int:
    removed = 0
    for sha in shas:
        if not _SHA.match(sha or ""):
            continue
        for media_type in ("image/jpeg", "image/png"):
            path = _path(owner, sha, media_type)
            if path.exists():
                path.unlink()
                removed += 1
    return removed


# ── the images of the current turn ──────────────────────────────────────

_turn: ContextVar[tuple[Image, ...]] = ContextVar("mizan_basar_turn", default=())


@contextmanager
def bind(images: Sequence[Image]) -> Iterator[None]:
    token = _turn.set(tuple(images)[:MAX_IMAGES])
    try:
        yield
    finally:
        _turn.reset(token)


def current() -> tuple[Image, ...]:
    return _turn.get()


def content(text: str, images: Sequence[Image] | None = None) -> str | list[dict]:
    """A user message's content: the text alone, or the text with the turn's images."""
    shown = current() if images is None else tuple(images)
    if not shown:
        return text
    return [{"type": "text", "text": text}, *(image.block() for image in shown)]
