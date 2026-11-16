"""Image upload validation and safe storage (Req 20.5, 20.6, 33.3, 33.4).

The client file name is only used to read the extension; it is never used on disk."""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO, Union

from .errors import ValidationFailed

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {'.jpg': 'jpeg', '.jpeg': 'jpeg', '.png': 'png', '.webp': 'webp'}


def _signature_type(data: bytes) -> str | None:
    if data[:3] == b'\xff\xd8\xff':
        return 'jpeg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    return None


def read_limited(stream: BinaryIO) -> bytes:
    """Read at most 5 MB + 1 byte so an oversized body is detected without loading all of it."""
    return stream.read(MAX_IMAGE_BYTES + 1)


def validate_image(filename: str, data: bytes) -> str:
    """Return the normalised extension (e.g. '.jpg') or raise ValidationFailed (422)."""
    ext = os.path.splitext(filename or '')[1].lower()
    kind = ALLOWED_EXTENSIONS.get(ext)
    if kind is None:
        raise ValidationFailed([{'field': 'image', 'reason': 'only .jpg, .jpeg, .png and .webp files are accepted'}],
                               code='unsupported_image_type')
    if len(data) > MAX_IMAGE_BYTES:
        raise ValidationFailed([{'field': 'image', 'reason': 'image must be at most 5 MB'}], code='image_too_large')
    if len(data) == 0:
        raise ValidationFailed([{'field': 'image', 'reason': 'image is empty'}], code='unsupported_image_type')
    if _signature_type(data) != kind:
        raise ValidationFailed([{'field': 'image', 'reason': 'file content does not match the image type'}],
                               code='unsupported_image_type')
    return '.jpg' if kind == 'jpeg' else ext


def stored_name(ext: str) -> str:
    return uuid.uuid4().hex + ext


def store_image(media_dir: Union[str, Path], data: bytes, ext: str) -> str:
    """Write to a temp file in media_dir/.tmp, then move to its final uuid4 name. Returns the stored filename."""
    root = Path(media_dir)
    tmp_dir = root / '.tmp'
    tmp_dir.mkdir(parents=True, exist_ok=True)
    name = stored_name(ext)
    tmp_path = tmp_dir / (uuid.uuid4().hex + '.part')
    try:
        tmp_path.write_bytes(data)
        shutil.move(str(tmp_path), str(root / name))
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return name
