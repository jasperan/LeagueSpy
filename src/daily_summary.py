"""Render an animated GIF summarising recent matches per player."""

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
_TEXT_WHITE = (255, 255, 255)
_TEXT_GRAY = (148, 155, 164)
_GREEN = (87, 242, 135)
_RED = (237, 66, 69)
_GOLD = (254, 185, 56)

_FRAME_WIDTH = 600
_ICON_SIZE = 40
_ICON_PAD = 6
_MARGIN = 30


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


def group_by_player(matches: list[dict]) -> dict[str, list[dict]]:
    """Group match dicts by ``player_name``."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for m in matches:
        grouped[m["player_name"]].append(m)
    return dict(grouped)


def render_player_frame(player_name: str, matches: list[dict]) -> Image.Image:
    """Render a single summary card for one player."""
    wins = sum(1 for m in matches if m["win"])
    losses = len(matches) - wins
    net = wins - losses

    # Unique champions in order played
    champs_seen: list[str] = []
    for m in matches:
        if m["champion"] not in champs_seen:
            champs_seen.append(m["champion"])

    # Download champion icons
    champ_icons: dict[str, Image.Image] = {}
    for c in champs_seen:
        icon = download_icon(c, size=_ICON_SIZE)
        if icon:
            champ_icons[c] = icon

    # Calculate layout
    icons_per_row = max(1, (_FRAME_WIDTH - 2 * _MARGIN - 8) // (_ICON_SIZE + _ICON_PAD))
    icon_rows = max(1, (len(champs_seen) + icons_per_row - 1) // icons_per_row)
    frame_height = (
        _MARGIN          # top
        + 30             # title
        + 20             # spacing
        + 35             # player name + net
        + 10             # spacing
        + 25             # W/L line
        + 15             # spacing
        + icon_rows * (_ICON_SIZE + _ICON_PAD)
        + _MARGIN        # bottom
    )

    img = Image.new("RGBA", (_FRAME_WIDTH, frame_height), _BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Gold accent bar on left
    draw.rectangle([0, 0, 5, frame_height], fill=_GOLD)

    title_font = _load_font(22)
    name_font = _load_font(28)
    stats_font = _load_font(20)
    champ_font = _load_font(14)

    y = _MARGIN

    # Title
    draw.text((_MARGIN, y), "LEAGUESPY SUMMARY", fill=_GOLD, font=title_font)
    y += 50  # 30 + 20 spacing

    # Player name (left) and net result (right)
    draw.text((_MARGIN, y), player_name.upper(), fill=_TEXT_WHITE, font=name_font)

    net_str = f"+{net}" if net > 0 else str(net)
    net_color = _GREEN if net > 0 else _RED if net < 0 else _TEXT_GRAY
    net_bbox = draw.textbbox((0, 0), net_str, font=name_font)
    net_w = net_bbox[2] - net_bbox[0]
    draw.text((_FRAME_WIDTH - _MARGIN - net_w, y), net_str, fill=net_color, font=name_font)
    y += 45  # 35 + 10 spacing

    # W/L line
    record_str = f"{wins}W / {losses}L"
    draw.text((_MARGIN, y), record_str, fill=_TEXT_GRAY, font=stats_font)
    y += 40  # 25 + 15 spacing

    # Champion icons
    x = _MARGIN
    for champ in champs_seen:
        if champ in champ_icons:
            icon = champ_icons[champ]
            img.paste(icon, (x, y), icon if icon.mode == "RGBA" else None)
        else:
            draw.text((x, y + _ICON_SIZE // 3), champ[:4], fill=_TEXT_GRAY, font=champ_font)
        x += _ICON_SIZE + _ICON_PAD
        if x + _ICON_SIZE > _FRAME_WIDTH - _MARGIN:
            x = _MARGIN
            y += _ICON_SIZE + _ICON_PAD

    return img


def build_summary_gif(grouped: dict[str, list[dict]]) -> BytesIO | None:
    """Build an animated GIF with one frame per active player.

    Returns *None* when *grouped* is empty.
    """
    if not grouped:
        return None

    frames: list[Image.Image] = []
    for player_name in sorted(grouped):
        frame = render_player_frame(player_name, grouped[player_name])
        frames.append(frame)

    if not frames:
        return None

    # Normalize all frames to the same height
    max_h = max(f.size[1] for f in frames)
    normalized: list[Image.Image] = []
    for f in frames:
        if f.size[1] < max_h:
            padded = Image.new("RGBA", (_FRAME_WIDTH, max_h), _BG_COLOR)
            padded.paste(f, (0, 0))
            normalized.append(padded)
        else:
            normalized.append(f)

    # Convert to palette mode for GIF
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
    return buf
