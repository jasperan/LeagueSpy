"""Render a 5v5 match scoreboard as a PNG image using Pillow."""

from __future__ import annotations

import logging
from io import BytesIO
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from src.champion_icons import download_icon
from src.models import MatchDetails, MatchParticipant

logger = logging.getLogger("leaguespy.match_image")

# -- Colors (Discord dark theme) --
_BG = (43, 45, 49)
_HEADER_BG = (32, 34, 37)
_ROW_BLUE = (24, 40, 60)
_ROW_RED = (60, 24, 28)
_ROW_BLUE_HL = (30, 55, 90)
_ROW_RED_HL = (90, 30, 35)
_BLUE_ACCENT = (59, 130, 246)
_RED_ACCENT = (239, 68, 68)
_WHITE = (255, 255, 255)
_GRAY = (148, 155, 164)
_LIGHT_GRAY = (185, 187, 190)
_GOLD = (254, 185, 56)
_GREEN = (87, 242, 135)
_SEPARATOR = (64, 68, 75)

# -- Layout constants --
_WIDTH = 720
_ROW_H = 40
_ICON_SIZE = 28
_HEADER_H = 32
_TEAM_GAP = 6
_MARGIN = 12
_COL_ICON = _MARGIN
_COL_NAME = _MARGIN + _ICON_SIZE + 8
_COL_RANK = 250
_COL_KDA = 330
_COL_CS = 430
_COL_GOLD = 490
_COL_KP = 560
_COL_VS = 640


@lru_cache(maxsize=8)
def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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
def _font_regular(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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


def _draw_rounded_rect(draw: ImageDraw.Draw, xy, radius, fill):
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill)
    except AttributeError:
        draw.rectangle(xy, fill=fill)


def _find_tracked_player(
    details: MatchDetails, summoner_slug: str,
) -> tuple[int, int] | None:
    """Return (team_index, player_index) for the tracked player, or None."""
    slug_as_name = summoner_slug.replace("-", "#").lower()
    for team_idx, players in enumerate([details.team1_players, details.team2_players]):
        for p_idx, p in enumerate(players):
            if p.summoner_name.lower().replace(" ", "") == slug_as_name.replace(" ", ""):
                return (team_idx, p_idx)
    return None


def _draw_header(draw: ImageDraw.Draw, y: int, label: str, result: str, accent: tuple) -> int:
    """Draw a team header bar. Returns the y after the header."""
    _draw_rounded_rect(draw, [0, y, _WIDTH, y + _HEADER_H], 0, _HEADER_BG)
    # Accent bar on left
    draw.rectangle([0, y, 4, y + _HEADER_H], fill=accent)

    hdr_font = _font(13)
    draw.text((_MARGIN + 6, y + 8), label, fill=accent, font=hdr_font)

    # Result on right
    result_color = _GREEN if result.upper() == "WIN" else _RED_ACCENT
    bbox = draw.textbbox((0, 0), result, font=hdr_font)
    rw = bbox[2] - bbox[0]
    draw.text((_WIDTH - _MARGIN - rw, y + 8), result, fill=result_color, font=hdr_font)

    return y + _HEADER_H


def _draw_column_headers(draw: ImageDraw.Draw, y: int) -> int:
    """Draw the column header labels."""
    f = _font_regular(10)
    color = _GRAY
    draw.text((_COL_NAME, y + 2), "PLAYER", fill=color, font=f)
    draw.text((_COL_RANK, y + 2), "RANK", fill=color, font=f)
    draw.text((_COL_KDA, y + 2), "KDA", fill=color, font=f)
    draw.text((_COL_CS, y + 2), "CS", fill=color, font=f)
    draw.text((_COL_GOLD, y + 2), "GOLD", fill=color, font=f)
    draw.text((_COL_KP, y + 2), "KP", fill=color, font=f)
    draw.text((_COL_VS, y + 2), "VIS", fill=color, font=f)
    return y + 18


def _draw_player_row(
    img: Image.Image,
    draw: ImageDraw.Draw,
    y: int,
    player: MatchParticipant,
    bg_color: tuple,
    highlight: bool = False,
) -> int:
    """Draw one player row. Returns y after the row."""
    row_bg = bg_color
    _draw_rounded_rect(draw, [0, y, _WIDTH, y + _ROW_H], 0, row_bg)

    name_font = _font(12) if highlight else _font_regular(12)
    stat_font = _font_regular(12)
    text_y = y + (_ROW_H - 14) // 2

    # Champion icon
    icon = download_icon(player.champion, size=_ICON_SIZE)
    if icon:
        ix = _COL_ICON
        iy = y + (_ROW_H - _ICON_SIZE) // 2
        img.paste(icon, (ix, iy), icon if icon.mode == "RGBA" else None)

    # Player name (truncate if long)
    name_color = _GOLD if highlight else _WHITE
    name = player.summoner_name
    if len(name) > 18:
        name = name[:17] + "."
    draw.text((_COL_NAME, text_y), name, fill=name_color, font=name_font)

    # Highlight marker
    if highlight:
        # Small gold triangle/arrow to the left of name
        draw.rectangle([_COL_NAME - 4, y + 4, _COL_NAME - 2, y + _ROW_H - 4], fill=_GOLD)

    # Rank
    rank = player.rank if player.rank else "-"
    if len(rank) > 10:
        rank = rank[:9] + "."
    draw.text((_COL_RANK, text_y), rank, fill=_LIGHT_GRAY, font=stat_font)

    # KDA
    k, d, a = player.kills, player.deaths, player.assists
    kda_str = f"{k}/{d}/{a}"
    # Color deaths red if high
    draw.text((_COL_KDA, text_y), kda_str, fill=_WHITE, font=stat_font)

    # KDA ratio
    ratio = (k + a) / d if d > 0 else float("inf")
    if ratio != float("inf"):
        ratio_str = f" ({ratio:.1f})"
        # Position after KDA text
        kda_bbox = draw.textbbox((_COL_KDA, text_y), kda_str, font=stat_font)
        ratio_color = _GREEN if ratio >= 3.0 else _GRAY
        draw.text((kda_bbox[2] + 2, text_y), ratio_str, fill=ratio_color, font=_font_regular(10))

    # CS
    draw.text((_COL_CS, text_y), str(player.cs), fill=_LIGHT_GRAY, font=stat_font)

    # Gold
    draw.text((_COL_GOLD, text_y), player.gold_display, fill=_GOLD, font=stat_font)

    # KP
    kp_str = f"{player.kill_participation}%" if player.kill_participation else "-"
    draw.text((_COL_KP, text_y), kp_str, fill=_LIGHT_GRAY, font=stat_font)

    # Vision
    vs_str = str(player.vision_score) if player.vision_score else "-"
    draw.text((_COL_VS, text_y), vs_str, fill=_LIGHT_GRAY, font=stat_font)

    # Row separator
    draw.line(
        [(_MARGIN, y + _ROW_H - 1), (_WIDTH - _MARGIN, y + _ROW_H - 1)],
        fill=_SEPARATOR, width=1,
    )

    return y + _ROW_H


def render_scoreboard(
    details: MatchDetails,
    summoner_slug: str,
) -> bytes | None:
    """Render a 5v5 scoreboard PNG.

    Returns PNG bytes or None if details are incomplete.
    """
    if not details.team1_players or not details.team2_players:
        return None

    tracked = _find_tracked_player(details, summoner_slug)

    # Calculate total height
    n1 = len(details.team1_players)
    n2 = len(details.team2_players)
    total_h = (
        _MARGIN
        + _HEADER_H + 18 + n1 * _ROW_H  # team 1 header + col headers + rows
        + _TEAM_GAP
        + _HEADER_H + 18 + n2 * _ROW_H  # team 2 header + col headers + rows
        + _MARGIN
    )

    img = Image.new("RGBA", (_WIDTH, total_h), _BG)
    draw = ImageDraw.Draw(img)

    y = _MARGIN

    # -- Team 1 (Blue side) --
    y = _draw_header(draw, y, "BLUE TEAM", details.team1_result, _BLUE_ACCENT)
    y = _draw_column_headers(draw, y)
    for i, player in enumerate(details.team1_players):
        is_highlighted = tracked == (0, i)
        bg = _ROW_BLUE_HL if is_highlighted else _ROW_BLUE
        y = _draw_player_row(img, draw, y, player, bg, highlight=is_highlighted)

    y += _TEAM_GAP

    # -- Team 2 (Red side) --
    y = _draw_header(draw, y, "RED TEAM", details.team2_result, _RED_ACCENT)
    y = _draw_column_headers(draw, y)
    for i, player in enumerate(details.team2_players):
        is_highlighted = tracked == (1, i)
        bg = _ROW_RED_HL if is_highlighted else _ROW_RED
        y = _draw_player_row(img, draw, y, player, bg, highlight=is_highlighted)

    # Export as PNG bytes
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
