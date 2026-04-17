"""Render premium performance trend charts as PNG images using Pillow."""

from __future__ import annotations

import logging
from io import BytesIO

from PIL import Image, ImageDraw

from src._render_helpers import load_bold_font, load_regular_font, text_width
from src.champion_icons import download_icon

logger = logging.getLogger("leaguespy.trends")

# ---------------------------------------------------------------------------
# Colors (matching scoreboard / daily summary theme)
# ---------------------------------------------------------------------------
_BG = (26, 27, 30)
_CARD_BG = (43, 45, 49)
_HEADER_BG = (32, 34, 37)
_WHITE = (255, 255, 255)
_GRAY = (120, 125, 134)
_LIGHT_GRAY = (185, 187, 190)
_GOLD = (254, 185, 56)
_GREEN = (87, 242, 135)
_GREEN_DIM = (40, 100, 60)
_RED = (239, 68, 68)
_RED_DIM = (100, 30, 30)
_BLUE = (59, 130, 246)
_BLUE_DIM = (25, 55, 110)
_GRID = (54, 57, 63)
_SEPARATOR = (54, 57, 63)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
_WIDTH = 800
_HEIGHT = 580
_MARGIN_LEFT = 60
_MARGIN_RIGHT = 55
_MARGIN_TOP = 140
_MARGIN_BOTTOM = 110
_CHART_W = _WIDTH - _MARGIN_LEFT - _MARGIN_RIGHT
_CHART_H = _HEIGHT - _MARGIN_TOP - _MARGIN_BOTTOM
_HEADER_H = 120
_HEATMAP_SQ = 14
_HEATMAP_GAP = 3


_font = load_bold_font
_font_regular = load_regular_font
_text_width = text_width


# ---------------------------------------------------------------------------
# Data functions
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Header rendering
# ---------------------------------------------------------------------------
def _render_header(draw: ImageDraw.Draw, img: Image.Image, player_name: str, matches: list[dict]):
    """Render the stats header bar with player summary."""
    # Gold accent line at top
    draw.rectangle([0, 0, _WIDTH, 3], fill=_GOLD)

    # Header background
    draw.rectangle([0, 3, _WIDTH, _HEADER_H], fill=_HEADER_BG)

    # Player name
    draw.text((20, 14), player_name.upper(), font=_font(20), fill=_GOLD)

    # Subtitle
    draw.text((20, 40), f"Ultimas {len(matches)} partidas", font=_font_regular(12), fill=_GRAY)

    # Most played champion icon
    from collections import Counter
    champ_counts = Counter(m.get("champion", "?") for m in matches)
    top_champ = champ_counts.most_common(1)[0][0] if champ_counts else None
    if top_champ:
        icon = download_icon(top_champ, size=36)
        if icon:
            icon = icon.resize((36, 36), Image.LANCZOS).convert("RGBA")
            # Circular mask
            mask = Image.new("L", (36, 36), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, 35, 35], fill=255)
            name_w = _text_width(draw, player_name.upper(), _font(20))
            ix = 20 + name_w + 12
            img.paste(icon, (ix, 12), mask)

    # Stats row
    wins = sum(1 for m in matches if m["win"])
    losses = len(matches) - wins
    wr = wins / max(1, len(matches)) * 100
    total_k = sum(m["kills"] for m in matches)
    total_d = sum(m["deaths"] for m in matches)
    total_a = sum(m["assists"] for m in matches)
    avg_kda = (total_k + total_a) / max(1, total_d)

    # Current form (last 5)
    last5 = matches[-5:] if len(matches) >= 5 else matches
    form_wins = sum(1 for m in last5 if m["win"])

    stat_y = 62
    stat_font = _font(14)
    stat_label = _font_regular(10)
    segments = [
        ("WIN RATE", f"{wr:.0f}%", _GREEN if wr >= 50 else _RED),
        ("AVG KDA", f"{avg_kda:.2f}", _GREEN if avg_kda >= 3 else _GOLD if avg_kda >= 2 else _LIGHT_GRAY),
        ("WINS", str(wins), _GREEN),
        ("LOSSES", str(losses), _RED),
        ("FORM", f"{form_wins}/{len(last5)}", _GREEN if form_wins >= 3 else _RED),
    ]

    x = 20
    for label, value, color in segments:
        draw.text((x, stat_y), label, font=stat_label, fill=_GRAY)
        draw.text((x, stat_y + 14), value, font=stat_font, fill=color)
        x += 110

    # Win/loss heatmap strip
    hx = 20
    hy = stat_y + 40
    for m in matches:
        color = _GREEN if m["win"] else _RED
        draw.rounded_rectangle([hx, hy, hx + _HEATMAP_SQ, hy + _HEATMAP_SQ], radius=2, fill=color)
        hx += _HEATMAP_SQ + _HEATMAP_GAP
        if hx + _HEATMAP_SQ > _WIDTH - 20:
            break

    # Separator
    draw.line([(0, _HEADER_H), (_WIDTH, _HEADER_H)], fill=_SEPARATOR, width=1)


# ---------------------------------------------------------------------------
# Gradient fill
# ---------------------------------------------------------------------------
def _draw_gradient_fill(img: Image.Image, points: list[tuple], base_y: int, color_top: tuple, color_bot: tuple):
    """Draw a gradient-filled area under a line chart, interpolating from color_top at the line down to color_bot at base_y."""
    if len(points) < 2:
        return

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    min_y = min(p[1] for p in points)
    x_left = points[0][0]
    x_right = points[-1][0]
    span = max(1, base_y - min_y)

    # Interpolate RGB between color_top (at line) and color_bot (at baseline),
    # with alpha fading out toward the baseline.
    top_rgb = color_top[:3]
    bot_rgb = color_bot[:3]
    for y_line in range(int(min_y), int(base_y)):
        progress = (y_line - min_y) / span
        r = int(top_rgb[0] + (bot_rgb[0] - top_rgb[0]) * progress)
        g = int(top_rgb[1] + (bot_rgb[1] - top_rgb[1]) * progress)
        b = int(top_rgb[2] + (bot_rgb[2] - top_rgb[2]) * progress)
        alpha = int(70 * (1 - progress))
        if alpha <= 0:
            continue
        odraw.line([(x_left, y_line), (x_right, y_line)], fill=(r, g, b, alpha), width=1)

    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"), (0, 0))


def _draw_thick_line(draw: ImageDraw.Draw, points: list[tuple], color: tuple, width: int = 3):
    """Draw a line with given width through a series of points."""
    if len(points) < 2:
        return
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=color, width=width)


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------
def render_trends_chart(matches: list[dict], player_name: str) -> BytesIO | None:
    """Render a premium performance trend chart."""
    if not matches:
        return None

    # Reverse: DB returns newest-first, we want oldest-first (left to right)
    if len(matches) > 1:
        matches = list(reversed(matches))

    n = len(matches)
    win_rates = compute_rolling_win_rate(matches)
    kda_ratios = compute_kda_ratios(matches)

    img = Image.new("RGB", (_WIDTH, _HEIGHT), _BG)
    draw = ImageDraw.Draw(img)

    # Header
    _render_header(draw, img, player_name, matches)

    # Chart background card
    chart_box = [
        _MARGIN_LEFT - 10, _MARGIN_TOP - 10,
        _WIDTH - _MARGIN_RIGHT + 10, _HEIGHT - _MARGIN_BOTTOM + 10,
    ]
    draw.rounded_rectangle(chart_box, radius=10, fill=_CARD_BG)

    # Grid lines (horizontal)
    for i in range(5):
        pct = i * 25
        y = _MARGIN_TOP + _CHART_H - (pct / 100) * _CHART_H
        draw.line([(_MARGIN_LEFT, y), (_WIDTH - _MARGIN_RIGHT, y)], fill=_GRID, width=1)
        draw.text((_MARGIN_LEFT - 8, y), f"{pct}%", font=_font_regular(10), fill=_GREEN, anchor="rm")

    # 50% reference line (dashed effect)
    y50 = _MARGIN_TOP + _CHART_H - 0.5 * _CHART_H
    for x_dash in range(_MARGIN_LEFT, _WIDTH - _MARGIN_RIGHT, 12):
        draw.line([(x_dash, y50), (min(x_dash + 6, _WIDTH - _MARGIN_RIGHT), y50)], fill=_GOLD, width=1)

    # Right axis labels (KDA: 0, 2.5, 5, 7.5, 10)
    for i in range(5):
        kda_val = i * 2.5
        y = _MARGIN_TOP + _CHART_H - (kda_val / 10) * _CHART_H
        draw.text((_WIDTH - _MARGIN_RIGHT + 8, y), f"{kda_val:.1f}", font=_font_regular(10), fill=_BLUE, anchor="lm")

    # Axis labels
    draw.text((_MARGIN_LEFT - 8, _MARGIN_TOP - 18), "Win%", font=_font(11), fill=_GREEN, anchor="rm")
    draw.text((_WIDTH - _MARGIN_RIGHT + 8, _MARGIN_TOP - 18), "KDA", font=_font(11), fill=_BLUE, anchor="lm")

    # Calculate x positions
    if n == 1:
        x_positions = [_MARGIN_LEFT + _CHART_W // 2]
    else:
        x_positions = [_MARGIN_LEFT + int(i * _CHART_W / (n - 1)) for i in range(n)]

    # Compute line points
    chart_bottom = _MARGIN_TOP + _CHART_H
    wr_points = []
    for i, rate in enumerate(win_rates):
        x = x_positions[i]
        y = _MARGIN_TOP + _CHART_H - (rate / 100) * _CHART_H
        wr_points.append((x, y))

    kda_points = []
    for i, ratio in enumerate(kda_ratios):
        x = x_positions[i]
        y = _MARGIN_TOP + _CHART_H - (ratio / 10) * _CHART_H
        kda_points.append((x, y))

    # Gradient fills under lines
    if len(wr_points) >= 2:
        _draw_gradient_fill(img, wr_points, chart_bottom, _GREEN, _BG)
        draw = ImageDraw.Draw(img)  # refresh after paste

    if len(kda_points) >= 2:
        _draw_gradient_fill(img, kda_points, chart_bottom, _BLUE, _BG)
        draw = ImageDraw.Draw(img)

    # Re-draw grid on top of gradient
    for i in range(5):
        pct = i * 25
        y = _MARGIN_TOP + _CHART_H - (pct / 100) * _CHART_H
        draw.line([(_MARGIN_LEFT, y), (_WIDTH - _MARGIN_RIGHT, y)], fill=(*_GRID, ), width=1)

    # Draw lines (thick, on top of gradient)
    _draw_thick_line(draw, wr_points, _GREEN, width=3)
    _draw_thick_line(draw, kda_points, _BLUE, width=2)

    # Data point dots with glow
    for pt in wr_points:
        draw.ellipse([pt[0] - 5, pt[1] - 5, pt[0] + 5, pt[1] + 5], fill=_GREEN_DIM)
        draw.ellipse([pt[0] - 3, pt[1] - 3, pt[0] + 3, pt[1] + 3], fill=_GREEN)
    for pt in kda_points:
        draw.ellipse([pt[0] - 4, pt[1] - 4, pt[0] + 4, pt[1] + 4], fill=_BLUE_DIM)
        draw.ellipse([pt[0] - 2, pt[1] - 2, pt[0] + 2, pt[1] + 2], fill=_BLUE)

    # Champion icons along the bottom (last 8 games)
    icon_row_y = _HEIGHT - _MARGIN_BOTTOM + 18
    num_icons = min(n, 8)
    icon_start = max(0, n - num_icons)
    icon_size = 28
    icon_gap = 8

    # Center the icons
    total_icon_w = num_icons * icon_size + (num_icons - 1) * icon_gap
    icon_base_x = _MARGIN_LEFT + (_CHART_W - total_icon_w) // 2

    for idx in range(num_icons):
        game_idx = icon_start + idx
        m = matches[game_idx]
        champ = m.get("champion", "?")
        ix = icon_base_x + idx * (icon_size + icon_gap)

        # Icon
        icon = download_icon(champ, size=icon_size)
        if icon:
            icon = icon.resize((icon_size, icon_size), Image.LANCZOS).convert("RGBA")
            mask = Image.new("L", (icon_size, icon_size), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, icon_size - 1, icon_size - 1], fill=255)
            # Border ring (green/red based on win)
            border_color = _GREEN if m["win"] else _RED
            ring_size = icon_size + 4
            ring = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
            ImageDraw.Draw(ring).ellipse([0, 0, ring_size - 1, ring_size - 1], fill=border_color)
            img.paste(ring, (ix - 2, icon_row_y - 2), ring)
            img.paste(icon, (ix, icon_row_y), mask)
        else:
            # Fallback: colored circle with initial
            border_color = _GREEN if m["win"] else _RED
            draw.ellipse([ix - 2, icon_row_y - 2, ix + icon_size + 2, icon_row_y + icon_size + 2], fill=border_color)
            draw.ellipse([ix, icon_row_y, ix + icon_size, icon_row_y + icon_size], fill=_CARD_BG)
            initial = champ[0] if champ else "?"
            draw.text((ix + icon_size // 2, icon_row_y + icon_size // 2), initial, font=_font(12), fill=_WHITE, anchor="mm")

        # Champion name below icon
        label = champ[:6] + "." if len(champ) > 7 else champ
        draw.text((ix + icon_size // 2, icon_row_y + icon_size + 4), label, font=_font_regular(8), fill=_LIGHT_GRAY, anchor="mt")

    # Game numbers under chart
    step = max(1, n // 8)
    for i in range(0, n, step):
        x = x_positions[i]
        draw.text((x, _HEIGHT - _MARGIN_BOTTOM + 4), f"#{i+1}", font=_font_regular(9), fill=_GRAY, anchor="mt")

    # Legend bar at very bottom
    legend_y = _HEIGHT - 18
    # Win rate
    draw.rounded_rectangle([_WIDTH // 2 - 180, legend_y - 6, _WIDTH // 2 - 168, legend_y + 6], radius=2, fill=_GREEN)
    draw.text((_WIDTH // 2 - 163, legend_y), "Win Rate", font=_font_regular(10), fill=_LIGHT_GRAY, anchor="lm")
    # KDA
    draw.rounded_rectangle([_WIDTH // 2 - 60, legend_y - 6, _WIDTH // 2 - 48, legend_y + 6], radius=2, fill=_BLUE)
    draw.text((_WIDTH // 2 - 43, legend_y), "KDA", font=_font_regular(10), fill=_LIGHT_GRAY, anchor="lm")
    # 50% line
    draw.line([(_WIDTH // 2 + 30, legend_y), (_WIDTH // 2 + 48, legend_y)], fill=_GOLD, width=1)
    draw.text((_WIDTH // 2 + 53, legend_y), "50%", font=_font_regular(10), fill=_GOLD, anchor="lm")
    # W/L dots
    draw.ellipse([_WIDTH // 2 + 100, legend_y - 4, _WIDTH // 2 + 108, legend_y + 4], fill=_GREEN)
    draw.text((_WIDTH // 2 + 112, legend_y), "W", font=_font_regular(9), fill=_GREEN, anchor="lm")
    draw.ellipse([_WIDTH // 2 + 130, legend_y - 4, _WIDTH // 2 + 138, legend_y + 4], fill=_RED)
    draw.text((_WIDTH // 2 + 142, legend_y), "L", font=_font_regular(9), fill=_RED, anchor="lm")

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
