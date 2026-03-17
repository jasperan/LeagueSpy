"""Render match summary images: composite PNG (<=4 players) or animated GIF (5+)."""

from __future__ import annotations

import logging
from collections import defaultdict
from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from src.champion_icons import download_icon

logger = logging.getLogger("leaguespy.summary")

# Colors (Discord dark theme)
_BG_COLOR = (43, 45, 49)
_CARD_BG = (54, 57, 63)
_TEXT_WHITE = (255, 255, 255)
_TEXT_GRAY = (148, 155, 164)
_GREEN = (87, 242, 135)
_RED = (237, 66, 69)
_GOLD = (254, 185, 56)
_SEPARATOR = (64, 68, 75)

_FRAME_WIDTH = 620
_ICON_SIZE = 36
_MARGIN = 24
_MATCH_ROW_H = 44
_HEATMAP_SQUARE = 14
_HEATMAP_GAP = 3


@lru_cache(maxsize=8)
def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


@lru_cache(maxsize=8)
def _load_font_regular(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def group_by_player(matches: list[dict]) -> dict[str, list[dict]]:
    """Group match dicts by ``player_name``."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for m in matches:
        grouped[m["player_name"]].append(m)
    return dict(grouped)


def _draw_rounded_rect(draw: ImageDraw.Draw, xy, radius, fill):
    """Draw a rounded rectangle (Pillow < 10.0 compat)."""
    x0, y0, x1, y1 = xy
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill)
    except AttributeError:
        draw.rectangle(xy, fill=fill)


def _render_heatmap(draw: ImageDraw.Draw, x: int, y: int, matches: list[dict]) -> int:
    """Draw a win/loss heatmap strip. Returns the width used."""
    for m in matches:
        color = _GREEN if m["win"] else _RED
        _draw_rounded_rect(draw, [x, y, x + _HEATMAP_SQUARE, y + _HEATMAP_SQUARE], 2, color)
        x += _HEATMAP_SQUARE + _HEATMAP_GAP
    return x


def _render_match_row(
    img: Image.Image, draw: ImageDraw.Draw, y: int, match: dict,
) -> None:
    """Draw one match row: result bar + icon + champion + KDA + CS + gold."""
    font = _load_font_regular(14)
    font_bold = _load_font(14)

    win = match["win"]
    bar_color = _GREEN if win else _RED

    # Result indicator bar (left edge, rounded)
    _draw_rounded_rect(draw, [_MARGIN, y + 2, _MARGIN + 4, y + _MATCH_ROW_H - 4], 2, bar_color)

    # Champion icon
    icon_x = _MARGIN + 14
    icon = download_icon(match["champion"], size=_ICON_SIZE)
    if icon:
        # Paste with alpha if RGBA
        img.paste(icon, (icon_x, y + (_MATCH_ROW_H - _ICON_SIZE) // 2),
                  icon if icon.mode == "RGBA" else None)

    # Champion name
    text_y = y + (_MATCH_ROW_H - 16) // 2
    champ_name = match["champion"]
    if len(champ_name) > 12:
        champ_name = champ_name[:11] + "."
    draw.text((_MARGIN + 56, text_y), champ_name, fill=_TEXT_WHITE, font=font_bold)

    # KDA
    k, d, a = match["kills"], match["deaths"], match["assists"]
    kda_str = f"{k}/{d}/{a}"
    draw.text((_MARGIN + 170, text_y), kda_str, fill=_TEXT_WHITE, font=font)

    # CS (if available)
    cs = match.get("cs", 0) or 0
    if cs:
        draw.text((_MARGIN + 250, text_y), f"{cs} CS", fill=_TEXT_GRAY, font=font)

    # Gold (if available)
    gold = match.get("gold", 0) or 0
    if gold:
        gold_str = f"{gold / 1000:.1f}k"
        draw.text((_MARGIN + 330, text_y), gold_str, fill=_GOLD, font=font)

    # KP% (if available)
    kp = match.get("kill_participation", 0) or 0
    if kp:
        draw.text((_MARGIN + 400, text_y), f"{kp}% KP", fill=_TEXT_GRAY, font=font)

    # Vision (if available)
    vs = match.get("vision_score", 0) or 0
    if vs:
        draw.text((_MARGIN + 480, text_y), f"Vis:{vs}", fill=_TEXT_GRAY, font=font)

    # Subtle row separator
    draw.line(
        [(_MARGIN + 14, y + _MATCH_ROW_H - 1),
         (_FRAME_WIDTH - _MARGIN, y + _MATCH_ROW_H - 1)],
        fill=_SEPARATOR, width=1,
    )


def render_player_frame(player_name: str, matches: list[dict]) -> Image.Image:
    """Render a single summary card for one player."""
    wins = sum(1 for m in matches if m["win"])
    losses = len(matches) - wins
    net = wins - losses

    # Calculate frame height
    frame_height = (
        _MARGIN                              # top padding
        + 24                                  # title
        + 12                                  # gap
        + 30                                  # player name
        + 6                                   # gap
        + 22                                  # W/L record
        + 14                                  # gap
        + _HEATMAP_SQUARE                     # heatmap strip
        + 16                                  # gap
        + len(matches) * _MATCH_ROW_H         # match rows
        + _MARGIN                             # bottom padding
    )

    img = Image.new("RGBA", (_FRAME_WIDTH, frame_height), _CARD_BG)
    draw = ImageDraw.Draw(img)

    # Gold accent bar (left edge, full height)
    draw.rectangle([0, 0, 5, frame_height], fill=_GOLD)

    title_font = _load_font(18)
    name_font = _load_font(24)
    record_font = _load_font_regular(16)

    y = _MARGIN

    # Title
    draw.text((_MARGIN, y), "LEAGUESPY", fill=_GOLD, font=title_font)
    y += 36  # 24 + 12

    # Player name (left) + net result (right)
    draw.text((_MARGIN, y), player_name.upper(), fill=_TEXT_WHITE, font=name_font)
    net_str = f"+{net}" if net > 0 else str(net)
    net_color = _GREEN if net > 0 else _RED if net < 0 else _TEXT_GRAY
    net_bbox = draw.textbbox((0, 0), net_str, font=name_font)
    net_w = net_bbox[2] - net_bbox[0]
    draw.text((_FRAME_WIDTH - _MARGIN - net_w, y), net_str, fill=net_color, font=name_font)
    y += 36  # 30 + 6

    # W/L record
    record_str = f"{wins}W  {losses}L"
    draw.text((_MARGIN, y), record_str, fill=_TEXT_GRAY, font=record_font)
    y += 36  # 22 + 14

    # Heatmap strip
    _render_heatmap(draw, _MARGIN, y, matches)
    y += _HEATMAP_SQUARE + 16

    # Match rows
    for match in matches:
        _render_match_row(img, draw, y, match)
        y += _MATCH_ROW_H

    return img


def build_summary_image(grouped: dict[str, list[dict]]) -> tuple[BytesIO, str] | None:
    """Build a summary image: composite PNG for <=4 players, animated GIF for 5+.

    Returns ``(buffer, filename)`` or *None* when *grouped* is empty.
    The filename ends in ``.png`` or ``.gif`` so the caller knows the format.
    """
    if not grouped:
        return None

    frames: list[Image.Image] = []
    for player_name in sorted(grouped):
        frame = render_player_frame(player_name, grouped[player_name])
        frames.append(frame)

    if not frames:
        return None

    # Composite PNG for <= 4 players
    if len(frames) <= 4:
        gap = 6
        total_h = sum(f.size[1] for f in frames) + gap * (len(frames) - 1)
        composite = Image.new("RGBA", (_FRAME_WIDTH, total_h), _BG_COLOR)
        y = 0
        for f in frames:
            composite.paste(f, (0, y))
            y += f.size[1] + gap

        buf = BytesIO()
        composite.save(buf, format="PNG")
        buf.seek(0)
        return buf, "leaguespy_summary.png"

    # Animated GIF for 5+ players
    max_h = max(f.size[1] for f in frames)
    normalized: list[Image.Image] = []
    for f in frames:
        if f.size[1] < max_h:
            padded = Image.new("RGBA", (_FRAME_WIDTH, max_h), _BG_COLOR)
            padded.paste(f, (0, 0))
            normalized.append(padded)
        else:
            normalized.append(f)

    p_frames = [
        f.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        for f in normalized
    ]

    buf = BytesIO()
    p_frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=p_frames[1:],
        duration=3000,
        loop=0,
    )
    buf.seek(0)
    return buf, "leaguespy_summary.gif"


# Keep backward compat alias for existing callers
def build_summary_gif(grouped: dict[str, list[dict]]) -> BytesIO | None:
    """Legacy wrapper: returns just the buffer (no filename)."""
    result = build_summary_image(grouped)
    if result is None:
        return None
    return result[0]
