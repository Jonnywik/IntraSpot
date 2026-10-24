from io import BytesIO

import pytest
from PIL import Image

from app.domains.media.codec import (
    InvalidMediaInput,
    MAX_DECODED_PIXELS,
    MAX_INPUT_BYTES,
    normalize_image,
)


def _encode(image: Image.Image, format_name: str, **options) -> bytes:
    output = BytesIO()
    image.save(output, format=format_name, **options)
    return output.getvalue()


@pytest.mark.parametrize(
    ("format_name", "content_type"),
    [("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")],
)
def test_accepts_supported_formats_and_returns_static_webp(format_name: str, content_type: str) -> None:
    source = _encode(Image.new("RGB", (80, 40), "navy"), format_name)

    normalized = normalize_image(source, content_type)

    with Image.open(BytesIO(normalized.content)) as result:
        assert result.format == "WEBP"
        assert result.n_frames == 1
        assert result.size == (80, 40)
        assert normalized.byte_size == len(normalized.content)


def test_rejects_content_type_spoofing() -> None:
    source = _encode(Image.new("RGB", (8, 8), "red"), "PNG")

    with pytest.raises(InvalidMediaInput):
        normalize_image(source, "image/jpeg")


def test_applies_exif_orientation_and_strips_metadata() -> None:
    source_image = Image.new("RGB", (40, 20), "green")
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "private test metadata"
    source = _encode(source_image, "JPEG", exif=exif)

    normalized = normalize_image(source, "image/jpeg")

    with Image.open(BytesIO(normalized.content)) as result:
        assert result.size == (20, 40)
        assert not result.getexif()
        assert not {"exif", "xmp", "icc_profile"} & result.info.keys()


def test_fits_oversized_edge_without_changing_aspect_ratio() -> None:
    source = _encode(Image.new("RGB", (3000, 1000), "white"), "PNG")

    normalized = normalize_image(source, "image/png")

    assert (normalized.width, normalized.height) == (2048, 683)


def test_rejects_animated_webp() -> None:
    frames = [Image.new("RGB", (10, 10), color) for color in ("red", "blue")]
    source = _encode(frames[0], "WEBP", save_all=True, append_images=frames[1:], duration=50, loop=0)

    with pytest.raises(InvalidMediaInput):
        normalize_image(source, "image/webp")


def test_rejects_truncated_input() -> None:
    source = _encode(Image.new("RGB", (32, 32), "orange"), "PNG")

    with pytest.raises(InvalidMediaInput):
        normalize_image(source[:-24], "image/png")


def test_rejects_input_over_five_mib() -> None:
    with pytest.raises(InvalidMediaInput):
        normalize_image(b"x" * (MAX_INPUT_BYTES + 1), "image/png")


def test_rejects_more_than_twelve_million_pixels() -> None:
    source = _encode(Image.new("RGB", (4001, 3000), "black"), "PNG")

    assert 4001 * 3000 > MAX_DECODED_PIXELS
    with pytest.raises(InvalidMediaInput):
        normalize_image(source, "image/png")
