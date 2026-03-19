"""Render premium match summary images: composite PNG (<=4 players) or animated GIF (5+)."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from src.champion_icons import download_icon, download_splash

logger = logging.getLogger("leaguespy.summary")

# ---------------------------------------------------------------------------
# Colors (matching scoreboard theme)
# ---------------------------------------------------------------------------
_BG = (26, 27, 30)
_CARD_BG = (43, 45, 49)
_HEADER_BG = (32, 34, 37)
_WHITE = (255, 255, 255)
_GRAY = (120, 125, 134)
_LIGHT_GRAY = (185, 187, 190)
_GREEN = (87, 242, 135)
_RED = (239, 68, 68)
_GOLD = (254, 185, 56)
_SEPARATOR = (54, 57, 63)
_ROW_WIN = (20, 38, 25)
_ROW_LOSS = (48, 20, 22)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
_WIDTH = 800
_MARGIN = 16
_CORNER_R = 10
_ICON_SIZE = 32
_MATCH_ROW_H = 44
_HEATMAP_SQ = 16
_HEATMAP_GAP = 4
_CARD_HEADER_H = 120
_SUMMARY_HEADER_H = 90
_CARD_GAP = 6


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
@lru_cache(maxsize=12)
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


@lru_cache(maxsize=12)
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _text_width(draw: ImageDraw.Draw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _rounded_rect(draw: ImageDraw.Draw, xy, radius, fill):
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill)
    except AttributeError:
        draw.rectangle(xy, fill=fill)


def _circular_icon(icon: Image.Image, size: int, border_color: tuple, border_w: int = 2) -> Image.Image:
    """Create a circular icon with a colored border ring."""
    total = size + border_w * 2
    canvas = Image.new("RGBA", (total, total), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.ellipse([0, 0, total - 1, total - 1], fill=border_color)
    draw.ellipse(
        [border_w - 1, border_w - 1, total - border_w, total - border_w],
        fill=_BG,
    )
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    icon_resized = icon.resize((size, size), Image.LANCZOS).convert("RGBA")
    canvas.paste(icon_resized, (border_w, border_w), mask)
    return canvas


def _make_win_rate_ring(size: int, win_rate: float) -> Image.Image:
    """Create a donut chart showing win rate."""
    ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(ring)

    bbox = [0, 0, size - 1, size - 1]
    win_deg = int(win_rate * 360)

    # Colored pie segments
    if win_deg > 0:
        d.pieslice(bbox, -90, -90 + win_deg, fill=(*_GREEN, 255))
    if win_deg < 360:
        d.pieslice(bbox, -90 + win_deg, 270, fill=(*_RED, 255))
    elif win_rate == 0:
        d.pieslice(bbox, 0, 360, fill=(*_RED, 255))

    # Donut mask: outer ring only
    outer_r = size // 2
    inner_r = outer_r - 7
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse(bbox, fill=255)
    md.ellipse(
        [outer_r - inner_r, outer_r - inner_r, outer_r + inner_r, outer_r + inner_r],
        fill=0,
    )
    ring.putalpha(mask)

    return ring


def _most_played_champion(matches: list[dict]) -> str | None:
    """Return the champion played most in the match list."""
    champs = Counter(m["champion"] for m in matches)
    return champs.most_common(1)[0][0] if champs else None


def _best_game_index(matches: list[dict]) -> int:
    """Find index of highest KDA ratio game."""
    if not matches:
        return -1
    ratios = [(m["kills"] + m["assists"]) / max(1, m["deaths"]) for m in matches]
    return ratios.index(max(ratios))


def group_by_player(matches: list[dict]) -> dict[str, list[dict]]:
    """Group match dicts by ``player_name``."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for m in matches:
        grouped[m["player_name"]].append(m)
    return dict(grouped)


# ---------------------------------------------------------------------------
# Summary header
# ---------------------------------------------------------------------------
def _render_summary_header(grouped: dict[str, list[dict]]) -> Image.Image:
    """Render the aggregate summary header strip."""
    img = Image.new("RGBA", (_WIDTH, _SUMMARY_HEADER_H), _HEADER_BG)
    draw = ImageDraw.Draw(img)

    # Gold accent line at top
    draw.rectangle([0, 0, _WIDTH, 2], fill=_GOLD)

    title_font = _font(16)
    stat_font = _font_regular(12)
    stat_font_b = _font(12)

    # Title
    draw.text((_MARGIN + 4, 14), "8-HOUR MATCH SUMMARY", fill=_GOLD, font=title_font)

    # Player count (right)
    count_str = f"{len(grouped)} PLAYERS"
    cw = _text_width(draw, count_str, stat_font)
    draw.text((_WIDTH - _MARGIN - cw - 4, 16), count_str, fill=_GRAY, font=stat_font)

    # Aggregate stats
    total_games = sum(len(ms) for ms in grouped.values())
    total_wins = sum(sum(1 for m in ms if m["win"]) for ms in grouped.values())
    total_losses = total_games - total_wins
    wr = total_wins / max(1, total_games) * 100

    stats_y = 42
    x = _MARGIN + 4
    segments = [
        (f"{total_games}", stat_font_b, _WHITE),
        (" GAMES  \u2022  ", stat_font, _GRAY),
        (f"{total_wins}", stat_font_b, _GREEN),
        (" WINS  \u2022  ", stat_font, _GRAY),
        (f"{total_losses}", stat_font_b, _RED),
        (" LOSSES  \u2022  ", stat_font, _GRAY),
        (f"{wr:.0f}% WIN RATE", stat_font_b, _GOLD),
    ]
    for text, f, color in segments:
        draw.text((x, stats_y), text, fill=color, font=f)
        x += _text_width(draw, text, f)

    # Most active player
    most_active = max(grouped, key=lambda p: len(grouped[p]))
    active_count = len(grouped[most_active])
    active_str = f"Most Active: {most_active} ({active_count} games)"
    draw.text((_MARGIN + 4, stats_y + 22), active_str, fill=_LIGHT_GRAY, font=stat_font)

    return img


# ---------------------------------------------------------------------------
# Player card
# ---------------------------------------------------------------------------
def _render_card_header(player_name: str, matches: list[dict]) -> Image.Image:
    """Render the player card header with splash background and stats."""
    img = Image.new("RGBA", (_WIDTH, _CARD_HEADER_H), _CARD_BG)
    draw = ImageDraw.Draw(img)

    wins = sum(1 for m in matches if m["win"])
    losses = len(matches) - wins
    net = wins - losses
    win_rate = wins / max(1, len(matches))
    top_champ = _most_played_champion(matches)

    # Splash background
    if top_champ:
        splash = download_splash(top_champ, width=_WIDTH, height=_CARD_HEADER_H)
        if splash:
            splash = splash.convert("RGBA")
            overlay = Image.new("RGBA", (_WIDTH, _CARD_HEADER_H), (18, 20, 24, 200))
            splash = Image.alpha_composite(splash, overlay)
            img.paste(splash, (0, 0))

    # Gold accent bar (left)
    draw.rectangle([0, 0, 4, _CARD_HEADER_H], fill=_GOLD)

    # Player name
    name_font = _font(22)
    draw.text((_MARGIN + 8, 12), player_name, fill=_GOLD, font=name_font)

    # Most played champion icon (next to name)
    name_w = _text_width(draw, player_name, name_font)
    if top_champ:
        icon = download_icon(top_champ, size=28)
        if icon:
            circ = _circular_icon(icon, 28, _GOLD, border_w=2)
            img.paste(circ, (_MARGIN + 8 + name_w + 10, 12), circ)

    # W-L record
    record_font = _font_regular(14)
    record_y = 42
    w_text = f"{wins}W"
    l_text = f"{losses}L"
    net_str = f"+{net}" if net > 0 else str(net)
    net_color = _GREEN if net > 0 else _RED if net < 0 else _GRAY

    draw.text((_MARGIN + 8, record_y), w_text, fill=_GREEN, font=record_font)
    wx = _MARGIN + 8 + _text_width(draw, w_text, record_font)
    draw.text((wx, record_y), "  ", fill=_GRAY, font=record_font)
    wx += _text_width(draw, "  ", record_font)
    draw.text((wx, record_y), l_text, fill=_RED, font=record_font)
    lx = wx + _text_width(draw, l_text, record_font)
    draw.text((lx, record_y), f"  ({net_str})", fill=net_color, font=record_font)

    # Average KDA
    total_k = sum(m["kills"] for m in matches)
    total_d = sum(m["deaths"] for m in matches)
    total_a = sum(m["assists"] for m in matches)
    avg_kda = (total_k + total_a) / max(1, total_d)
    kda_font = _font(13)
    kda_str = f"Avg KDA {avg_kda:.2f}"
    kda_color = _GREEN if avg_kda >= 3.0 else _GOLD if avg_kda >= 2.0 else _LIGHT_GRAY
    kw = _text_width(draw, kda_str, kda_font)
    draw.text((_MARGIN + 8, record_y + 22), kda_str, fill=kda_color, font=kda_font)

    # Win rate ring (right side)
    ring_size = 56
    ring = _make_win_rate_ring(ring_size, win_rate)
    ring_x = _WIDTH - _MARGIN - ring_size - 16
    ring_y = 10
    img.paste(ring, (ring_x, ring_y), ring)
    # Percentage text in center of ring
    pct_str = f"{int(win_rate * 100)}%"
    pct_font = _font(13)
    pw = _text_width(draw, pct_str, pct_font)
    draw.text(
        (ring_x + (ring_size - pw) // 2, ring_y + (ring_size - 14) // 2),
        pct_str, fill=_WHITE, font=pct_font,
    )

    # Heatmap strip
    heatmap_y = _CARD_HEADER_H - _HEATMAP_SQ - 14
    hx = _MARGIN + 8
    for m in matches:
        color = _GREEN if m["win"] else _RED
        _rounded_rect(draw, [hx, heatmap_y, hx + _HEATMAP_SQ, heatmap_y + _HEATMAP_SQ], 3, color)
        hx += _HEATMAP_SQ + _HEATMAP_GAP

    # Separator at bottom
    draw.line(
        [(_MARGIN, _CARD_HEADER_H - 1), (_WIDTH - _MARGIN, _CARD_HEADER_H - 1)],
        fill=_SEPARATOR, width=1,
    )

    return img


def _render_match_row(
    img: Image.Image, draw: ImageDraw.Draw, y: int,
    match: dict, is_best: bool = False,
) -> int:
    """Draw one match row with colored background and circular icon."""
    bg = _ROW_WIN if match["win"] else _ROW_LOSS
    _rounded_rect(draw, [0, y, _WIDTH, y + _MATCH_ROW_H], 0, bg)

    font = _font_regular(12)
    font_b = _font(12)
    text_y = y + (_MATCH_ROW_H - 13) // 2

    # Result indicator bar
    bar_color = _GREEN if match["win"] else _RED
    _rounded_rect(draw, [_MARGIN, y + 4, _MARGIN + 4, y + _MATCH_ROW_H - 4], 2, bar_color)

    # Champion icon (circular)
    icon_x = _MARGIN + 14
    icon = download_icon(match["champion"], size=_ICON_SIZE)
    if icon:
        border = _GOLD if is_best else _SEPARATOR
        circ = _circular_icon(icon, _ICON_SIZE, border, border_w=2)
        iy = y + (_MATCH_ROW_H - circ.size[1]) // 2
        img.paste(circ, (icon_x, iy), circ)

    # Champion name
    champ = match["champion"]
    if len(champ) > 12:
        champ = champ[:11] + "\u2026"
    draw.text((_MARGIN + 56, text_y), champ, fill=_WHITE, font=font_b)

    # KDA with color coding
    k, d, a = match["kills"], match["deaths"], match["assists"]
    ratio = (k + a) / max(1, d)
    kda_str = f"{k}/{d}/{a}"
    kda_color = _GREEN if ratio >= 3.0 else _GOLD if ratio >= 2.0 else _WHITE
    draw.text((220, text_y), kda_str, fill=kda_color, font=font)

    # KDA ratio
    ratio_str = f"({ratio:.1f})"
    kda_w = _text_width(draw, kda_str, font)
    ratio_color = _GREEN if ratio >= 3.0 else _GRAY
    draw.text((220 + kda_w + 4, text_y + 1), ratio_str, fill=ratio_color, font=_font_regular(10))

    # CS
    cs = match.get("cs", 0) or 0
    if cs:
        draw.text((350, text_y), f"{cs} CS", fill=_LIGHT_GRAY, font=font)

    # Gold
    gold = match.get("gold", 0) or 0
    if gold:
        gold_str = f"{gold / 1000:.1f}k" if gold >= 1000 else str(gold)
        draw.text((430, text_y), gold_str, fill=_GOLD, font=font)

    # KP
    kp = match.get("kill_participation", 0) or 0
    if kp:
        draw.text((510, text_y), f"{kp}%", fill=_LIGHT_GRAY, font=font)

    # Vision
    vs = match.get("vision_score", 0) or 0
    if vs:
        draw.text((570, text_y), f"Vis {vs}", fill=_LIGHT_GRAY, font=font)

    # Best game star
    if is_best:
        star_font = _font(14)
        draw.text((_WIDTH - _MARGIN - 20, text_y - 1), "\u2605", fill=_GOLD, font=star_font)

    # Row separator
    draw.line(
        [(_MARGIN + 14, y + _MATCH_ROW_H - 1), (_WIDTH - _MARGIN, y + _MATCH_ROW_H - 1)],
        fill=_SEPARATOR, width=1,
    )

    return y + _MATCH_ROW_H


def render_player_frame(player_name: str, matches: list[dict]) -> Image.Image:
    """Render a premium summary card for one player."""
    best_idx = _best_game_index(matches) if len(matches) > 1 else -1

    # Header
    header = _render_card_header(player_name, matches)

    # Match rows area
    rows_h = len(matches) * _MATCH_ROW_H + _MARGIN
    total_h = _CARD_HEADER_H + rows_h

    img = Image.new("RGBA", (_WIDTH, total_h), _CARD_BG)
    img.paste(header, (0, 0))
    draw = ImageDraw.Draw(img)

    y = _CARD_HEADER_H
    for i, match in enumerate(matches):
        y = _render_match_row(img, draw, y, match, is_best=(i == best_idx))

    # Rounded corners
    mask = Image.new("L", img.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    try:
        mask_draw.rounded_rectangle([0, 0, _WIDTH, total_h], radius=_CORNER_R, fill=255)
    except AttributeError:
        mask_draw.rectangle([0, 0, _WIDTH, total_h], fill=255)

    final = Image.new("RGBA", img.size, (0, 0, 0, 0))
    final.paste(img, (0, 0), mask)

    return final


# ---------------------------------------------------------------------------
# Public build functions
# ---------------------------------------------------------------------------
def build_summary_image(grouped: dict[str, list[dict]]) -> tuple[BytesIO, str] | None:
    """Build a summary image: composite PNG for <=4 players, animated GIF for 5+.

    Returns ``(buffer, filename)`` or *None* when *grouped* is empty.
    """
    if not grouped:
        return None

    # Summary header (only for multi-player summaries)
    header = _render_summary_header(grouped) if len(grouped) >= 2 else None

    frames: list[Image.Image] = []
    for player_name in sorted(grouped):
        frame = render_player_frame(player_name, grouped[player_name])
        frames.append(frame)

    if not frames:
        return None

    # Composite PNG for <= 4 players
    if len(frames) <= 4:
        header_h = header.size[1] + _CARD_GAP if header else 0
        total_h = header_h + sum(f.size[1] for f in frames) + _CARD_GAP * (len(frames) - 1)
        composite = Image.new("RGBA", (_WIDTH, total_h), _BG)

        y = 0
        if header:
            composite.paste(header, (0, y), header)
            y += header.size[1] + _CARD_GAP

        for f in frames:
            composite.paste(f, (0, y), f)
            y += f.size[1] + _CARD_GAP

        buf = BytesIO()
        composite.save(buf, format="PNG")
        buf.seek(0)
        return buf, "leaguespy_summary.png"

    # Animated GIF for 5+ players: embed mini-header in each frame
    max_h = max(f.size[1] for f in frames)
    normalized: list[Image.Image] = []
    for idx, f in enumerate(frames):
        padded = Image.new("RGBA", (_WIDTH, max_h), _BG)
        padded.paste(f, (0, 0), f)
        normalized.append(padded)

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


# Keep backward compat alias
def build_summary_gif(grouped: dict[str, list[dict]]) -> BytesIO | None:
    """Legacy wrapper: returns just the buffer (no filename)."""
    result = build_summary_image(grouped)
    if result is None:
        return None
    return result[0]
