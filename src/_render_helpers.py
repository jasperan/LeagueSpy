"""Shared Pillow rendering helpers (fonts, common shapes).

Used by match_image, daily_summary, trends, and rankings to avoid repeating
the same font-loading and primitive-drawing logic across four files.
"""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

_BOLD_FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
)

_REGULAR_FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
)


def _load_truetype(
    paths: tuple[str, ...], size: int
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


@lru_cache(maxsize=32)
def load_bold_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a bold TrueType font at the given size, falling back to default."""
    return _load_truetype(_BOLD_FONT_PATHS, size)


@lru_cache(maxsize=32)
def load_regular_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a regular-weight TrueType font at the given size, falling back to default."""
    return _load_truetype(_REGULAR_FONT_PATHS, size)


def text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    """Measure the pixel width of `text` drawn with `font`."""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill) -> None:
    """Draw a rounded rectangle, falling back to a plain rectangle on older Pillow."""
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill)
    except AttributeError:
        draw.rectangle(xy, fill=fill)


def circular_icon(
    icon: Image.Image,
    size: int,
    border_color: tuple,
    bg_color: tuple,
    border_w: int = 2,
) -> Image.Image:
    """Return `icon` fit into a circular frame with a colored border ring."""
    total = size + border_w * 2
    canvas = Image.new("RGBA", (total, total), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.ellipse([0, 0, total - 1, total - 1], fill=border_color)
    draw.ellipse(
        [border_w - 1, border_w - 1, total - border_w, total - border_w],
        fill=bg_color,
    )
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    icon_resized = icon.resize((size, size), Image.LANCZOS).convert("RGBA")
    canvas.paste(icon_resized, (border_w, border_w), mask)
    return canvas
