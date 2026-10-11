"""Listing photo uploads.

Every upload is opened with Pillow to prove it really is an image, then re-saved as a resized WebP.
Re-saving throws away anything hidden in the original file, including GPS location metadata (EXIF).
"""

import uuid
import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import get_settings
from app.errors import DomainError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_SIDE = 1200
# Refuse "decompression bombs": tiny files that expand to enormous images and exhaust memory.
Image.MAX_IMAGE_PIXELS = 30_000_000

_NOT_AN_IMAGE = DomainError(422, "That file isn't a supported photo. Please use JPG, PNG or WebP.", field="image")


def save_listing_image(data: bytes) -> str:
    """Validate and store the image; returns its path relative to the media folder."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        try:
            with Image.open(BytesIO(data)) as probe:
                if probe.format not in ALLOWED_FORMATS:
                    raise _NOT_AN_IMAGE
                probe.verify()
            with Image.open(BytesIO(data)) as image:
                image = ImageOps.exif_transpose(image)
                image = image.convert("RGB")
                image.thumbnail((MAX_SIDE, MAX_SIDE))
                relative = f"listings/{uuid.uuid4().hex}.webp"
                target = get_settings().media_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                image.save(target, "WEBP", quality=82, method=4)
        except (
            UnidentifiedImageError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            OSError,
            SyntaxError,
            ValueError,
        ) as exc:
            raise _NOT_AN_IMAGE from exc
    return relative


def delete_image(relative: str | None) -> None:
    if not relative:
        return
    media_dir = get_settings().media_dir.resolve()
    path = (media_dir / relative).resolve()
    if path.is_relative_to(media_dir) and path.is_file():
        path.unlink(missing_ok=True)
