from __future__ import annotations

import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageFile, ImageOps


MAX_INPUT_BYTES = 5 * 1024 * 1024
MAX_DECODED_PIXELS = 12_000_000
MAX_OUTPUT_EDGE = 2048
_FORMAT_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


class InvalidMediaInput(ValueError):
    """An upload is invalid or violates the accepted image contract."""


class UnsupportedMediaType(InvalidMediaInput):
    """The request Content-Type is not an accepted image type."""


@dataclass(frozen=True)
class NormalizedImage:
    content: bytes
    width: int
    height: int

    @property
    def byte_size(self) -> int:
        return len(self.content)


def validate_content_type(content_type: str | None) -> str:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type not in _FORMAT_MIME.values():
        raise UnsupportedMediaType
    return media_type


def normalize_image(content: bytes, content_type: str | None) -> NormalizedImage:
    media_type = validate_content_type(content_type)
    if not content or len(content) > MAX_INPUT_BYTES or ImageFile.LOAD_TRUNCATED_IMAGES:
        raise InvalidMediaInput

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content), formats=tuple(_FORMAT_MIME)) as image:
                detected_format = image.format
                if detected_format not in _FORMAT_MIME or _FORMAT_MIME[detected_format] != media_type:
                    raise UnsupportedMediaType
                if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) != 1:
                    raise InvalidMediaInput
                if image.width * image.height > MAX_DECODED_PIXELS:
                    raise InvalidMediaInput
                image.verify()

            with Image.open(BytesIO(content), formats=tuple(_FORMAT_MIME)) as image:
                if image.format != detected_format or image.width * image.height > MAX_DECODED_PIXELS:
                    raise InvalidMediaInput
                if getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) != 1:
                    raise InvalidMediaInput
                image.load()
                oriented = ImageOps.exif_transpose(image)
                if oriented.width * oriented.height > MAX_DECODED_PIXELS:
                    raise InvalidMediaInput

                has_alpha = "A" in oriented.getbands() or "transparency" in oriented.info
                pixels = oriented.convert("RGBA" if has_alpha else "RGB")
                pixels.thumbnail(
                    (MAX_OUTPUT_EDGE, MAX_OUTPUT_EDGE),
                    Image.Resampling.LANCZOS,
                )
                pixels.info.clear()

                output = BytesIO()
                pixels.save(
                    output,
                    format="WEBP",
                    quality=85,
                    method=6,
                    exif=b"",
                    icc_profile=None,
                    xmp=b"",
                )
                encoded = output.getvalue()
                if not encoded:
                    raise InvalidMediaInput
                return NormalizedImage(encoded, pixels.width, pixels.height)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning,
            Image.UnidentifiedImageError, OSError, EOFError, SyntaxError, ValueError) as exc:
        if isinstance(exc, (UnsupportedMediaType, InvalidMediaInput)):
            raise
        raise InvalidMediaInput from None
