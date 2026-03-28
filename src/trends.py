"""Render performance trend charts as PNG images using Pillow."""

from __future__ import annotations

import logging
from io import BytesIO
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("leaguespy.trends")

# Colors (matching existing dark theme from match_image.py)
_BG = (26, 27, 30)
_CARD_BG = (43, 45, 49)
_WHITE = (255, 255, 255)
_GRAY = (120, 125, 134)
_LIGHT_GRAY = (185, 187, 190)
_GOLD = (254, 185, 56)
_GREEN = (87, 242, 135)
_RED = (239, 68, 68)
_BLUE = (59, 130, 246)
_GRID = (54, 57, 63)

# Layout
_WIDTH = 800
_HEIGHT = 500
_MARGIN_LEFT = 65
_MARGIN_RIGHT = 55
_MARGIN_TOP = 70
_MARGIN_BOTTOM = 90
_CHART_W = _WIDTH - _MARGIN_LEFT - _MARGIN_RIGHT
_CHART_H = _HEIGHT - _MARGIN_TOP - _MARGIN_BOTTOM


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


def compute_rolling_win_rate(matches: list[dict], window: int = 10) -> list[float]:
    """Compute rolling win rate over a sliding window. Returns list of percentages."""
    if not matches:
        return []
    rates = []
    for i in range(len(matches)):
        start = max(0, i - window + 1)
        chunk = matches[start:i + 1]
        wins = sum(1 for m in chunk if m["win"])
        rates.append(round(wins / len(chunk) * 100, 1))
    return rates


def compute_kda_ratios(matches: list[dict]) -> list[float]:
    """Compute per-game KDA ratio. Returns list of floats (capped at 10)."""
    ratios = []
    for m in matches:
        deaths = m["deaths"] if m["deaths"] else 1
        ratio = (m["kills"] + m["assists"]) / deaths
        ratios.append(min(ratio, 10.0))
    return ratios


def render_trends_chart(matches: list[dict], player_name: str) -> BytesIO | None:
    """Render a performance trend chart. Matches should be ordered oldest-first."""
    if not matches:
        return None

    # Reverse if newest-first (DB returns newest first)
    if len(matches) > 1:
        # We always reverse since DB returns newest-first
        matches = list(reversed(matches))

    n = len(matches)
    win_rates = compute_rolling_win_rate(matches)
    kda_ratios = compute_kda_ratios(matches)

    img = Image.new("RGB", (_WIDTH, _HEIGHT), _BG)
    draw = ImageDraw.Draw(img)

    # Title
    title = f"{player_name} - Tendencias de rendimiento"
    draw.text((_WIDTH // 2, 20), title, font=_font(18), fill=_GOLD, anchor="mt")
    subtitle = f"Ultimas {n} partidas"
    draw.text((_WIDTH // 2, 44), subtitle, font=_font_regular(12), fill=_GRAY, anchor="mt")

    # Chart background
    draw.rounded_rectangle(
        [_MARGIN_LEFT - 5, _MARGIN_TOP - 5, _WIDTH - _MARGIN_RIGHT + 5, _HEIGHT - _MARGIN_BOTTOM + 5],
        radius=8, fill=_CARD_BG,
    )

    # Grid lines (horizontal) - 5 lines for win rate (0%, 25%, 50%, 75%, 100%)
    for i in range(5):
        pct = i * 25
        y = _MARGIN_TOP + _CHART_H - (pct / 100) * _CHART_H
        draw.line([(_MARGIN_LEFT, y), (_WIDTH - _MARGIN_RIGHT, y)], fill=_GRID, width=1)
        # Left axis label (Win Rate)
        draw.text((_MARGIN_LEFT - 8, y), f"{pct}%", font=_font_regular(10), fill=_GREEN, anchor="rm")

    # Right axis labels (KDA: 0, 2.5, 5, 7.5, 10)
    for i in range(5):
        kda_val = i * 2.5
        y = _MARGIN_TOP + _CHART_H - (kda_val / 10) * _CHART_H
        draw.text((_WIDTH - _MARGIN_RIGHT + 8, y), f"{kda_val:.1f}", font=_font_regular(10), fill=_BLUE, anchor="lm")

    # Axis labels
    draw.text((_MARGIN_LEFT - 8, _MARGIN_TOP - 15), "Win%", font=_font(10), fill=_GREEN, anchor="rm")
    draw.text((_WIDTH - _MARGIN_RIGHT + 8, _MARGIN_TOP - 15), "KDA", font=_font(10), fill=_BLUE, anchor="lm")

    # Calculate x positions for each game
    if n == 1:
        x_positions = [_MARGIN_LEFT + _CHART_W // 2]
    else:
        x_positions = [_MARGIN_LEFT + int(i * _CHART_W / (n - 1)) for i in range(n)]

    # Draw win rate line (green)
    wr_points = []
    for i, rate in enumerate(win_rates):
        x = x_positions[i]
        y = _MARGIN_TOP + _CHART_H - (rate / 100) * _CHART_H
        wr_points.append((x, y))

    if len(wr_points) >= 2:
        for i in range(len(wr_points) - 1):
            draw.line([wr_points[i], wr_points[i + 1]], fill=_GREEN, width=2)

    # Draw KDA line (blue)
    kda_points = []
    for i, ratio in enumerate(kda_ratios):
        x = x_positions[i]
        y = _MARGIN_TOP + _CHART_H - (ratio / 10) * _CHART_H
        kda_points.append((x, y))

    if len(kda_points) >= 2:
        for i in range(len(kda_points) - 1):
            draw.line([kda_points[i], kda_points[i + 1]], fill=_BLUE, width=2)

    # Draw win/loss dots
    dot_y = _HEIGHT - _MARGIN_BOTTOM + 15
    for i, match in enumerate(matches):
        x = x_positions[i]
        color = _GREEN if match["win"] else _RED
        draw.ellipse([x - 4, dot_y - 4, x + 4, dot_y + 4], fill=color)

    # Draw data points on lines
    for pt in wr_points:
        draw.ellipse([pt[0] - 3, pt[1] - 3, pt[0] + 3, pt[1] + 3], fill=_GREEN)
    for pt in kda_points:
        draw.ellipse([pt[0] - 3, pt[1] - 3, pt[0] + 3, pt[1] + 3], fill=_BLUE)

    # X-axis champion labels (every 5 games, rotated text not possible in Pillow so just show game #)
    step = max(1, n // 10)
    for i in range(0, n, step):
        x = x_positions[i]
        draw.text((x, _HEIGHT - _MARGIN_BOTTOM + 30), f"#{i+1}", font=_font_regular(9), fill=_GRAY, anchor="mt")

    # Champion names for last 5 games
    start_idx = max(0, n - 5)
    for i in range(start_idx, n):
        x = x_positions[i]
        champ = matches[i].get("champion", "?")
        if len(champ) > 8:
            champ = champ[:7] + "."
        draw.text((x, _HEIGHT - _MARGIN_BOTTOM + 42), champ, font=_font_regular(8), fill=_LIGHT_GRAY, anchor="mt")

    # Legend
    legend_y = _HEIGHT - 20
    # Win rate legend
    draw.rectangle([_WIDTH // 2 - 130, legend_y - 5, _WIDTH // 2 - 120, legend_y + 5], fill=_GREEN)
    draw.text((_WIDTH // 2 - 115, legend_y), "Win Rate (10 partidas)", font=_font_regular(10), fill=_LIGHT_GRAY, anchor="lm")
    # KDA legend
    draw.rectangle([_WIDTH // 2 + 60, legend_y - 5, _WIDTH // 2 + 70, legend_y + 5], fill=_BLUE)
    draw.text((_WIDTH // 2 + 75, legend_y), "KDA Ratio", font=_font_regular(10), fill=_LIGHT_GRAY, anchor="lm")

    # Win/loss indicator legend
    draw.ellipse([_MARGIN_LEFT, legend_y - 4, _MARGIN_LEFT + 8, legend_y + 4], fill=_GREEN)
    draw.text((_MARGIN_LEFT + 12, legend_y), "W", font=_font_regular(9), fill=_GREEN, anchor="lm")
    draw.ellipse([_MARGIN_LEFT + 25, legend_y - 4, _MARGIN_LEFT + 33, legend_y + 4], fill=_RED)
    draw.text((_MARGIN_LEFT + 37, legend_y), "L", font=_font_regular(9), fill=_RED, anchor="lm")

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
