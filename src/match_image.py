"""Render a premium 5v5 match scoreboard as a PNG image using Pillow."""

from __future__ import annotations

import logging
from io import BytesIO
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageEnhance

from src.champion_icons import download_icon, download_splash
from src.models import MatchDetails, MatchParticipant

logger = logging.getLogger("leaguespy.match_image")

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
_BG = (26, 27, 30)
_CARD_BG = (43, 45, 49)
_HEADER_BG = (32, 34, 37)
_ROW_BLUE = (20, 35, 55)
_ROW_RED = (55, 20, 25)
_ROW_BLUE_HL = (28, 50, 82)
_ROW_RED_HL = (82, 28, 32)
_BLUE_ACCENT = (59, 130, 246)
_BLUE_DARK = (30, 60, 100)
_RED_ACCENT = (239, 68, 68)
_RED_DARK = (100, 30, 30)
_WHITE = (255, 255, 255)
_GRAY = (120, 125, 134)
_LIGHT_GRAY = (185, 187, 190)
_GOLD = (254, 185, 56)
_GREEN = (87, 242, 135)
_SEPARATOR = (54, 57, 63)
_PILL_BG = (0, 0, 0, 120)
_MVP_GLOW = (255, 215, 0)

# Rank tier colors
_RANK_COLORS = {
    "iron": (92, 64, 51),
    "bronze": (140, 98, 57),
    "silver": (155, 168, 183),
    "gold": (255, 185, 56),
    "platinum": (0, 184, 171),
    "emerald": (80, 200, 120),
    "diamond": (104, 170, 247),
    "master": (155, 89, 182),
    "grandmaster": (231, 72, 72),
    "challenger": (240, 230, 140),
}

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
_WIDTH = 800
_MARGIN = 14
_GAME_INFO_H = 34
_SPOTLIGHT_H = 190
_BANS_H = 44
_TEAM_HEADER_H = 34
_COL_HEADERS_H = 18
_ROW_H = 44
_ICON_SIZE = 32
_SPOTLIGHT_ICON = 76
_TEAM_GAP = 6
_SECTION_GAP = 5
_CORNER_R = 10

# Column positions for player rows
_COL_ICON = _MARGIN + 4
_COL_NAME = _MARGIN + _ICON_SIZE + 18
_COL_RANK = 240
_COL_KDA = 340
_COL_CS = 460
_COL_GOLD = 520
_COL_KP = 600
_COL_VS = 670
_COL_MVP = 740


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
def _rank_color(rank_str: str) -> tuple:
    """Get the tier color for a rank string like 'Diamond II'."""
    rank_lower = rank_str.lower() if rank_str else ""
    for tier, color in _RANK_COLORS.items():
        if tier in rank_lower:
            return color
    return _GRAY


def _rounded_rect(draw: ImageDraw.Draw, xy, radius, fill):
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill)
    except AttributeError:
        draw.rectangle(xy, fill=fill)


def _rounded_rect_outline(draw: ImageDraw.Draw, xy, radius, outline, width=2):
    try:
        draw.rounded_rectangle(xy, radius=radius, outline=outline, width=width)
    except AttributeError:
        draw.rectangle(xy, outline=outline, width=width)


def _make_gradient(width: int, height: int, color_left: tuple, color_right: tuple) -> Image.Image:
    """Create a horizontal gradient image (fast: 1px tall then scale)."""
    base = Image.new("RGBA", (width, 1))
    for x in range(width):
        ratio = x / max(1, width - 1)
        r = int(color_left[0] + (color_right[0] - color_left[0]) * ratio)
        g = int(color_left[1] + (color_right[1] - color_left[1]) * ratio)
        b = int(color_left[2] + (color_right[2] - color_left[2]) * ratio)
        base.putpixel((x, 0), (r, g, b, 255))
    return base.resize((width, height), Image.NEAREST)


def _circular_icon(icon: Image.Image, size: int, border_color: tuple, border_w: int = 3) -> Image.Image:
    """Create a circular icon with a colored border ring."""
    total = size + border_w * 2
    canvas = Image.new("RGBA", (total, total), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Border circle
    draw.ellipse([0, 0, total - 1, total - 1], fill=border_color)

    # Inner dark circle (gap between border and icon)
    inner_gap = 1
    draw.ellipse(
        [border_w - inner_gap, border_w - inner_gap,
         total - border_w + inner_gap, total - border_w + inner_gap],
        fill=_BG,
    )

    # Circular mask for icon
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)

    icon_resized = icon.resize((size, size), Image.LANCZOS).convert("RGBA")
    canvas.paste(icon_resized, (border_w, border_w), mask)

    return canvas


def _ban_icon_overlay(icon: Image.Image, size: int = 24) -> Image.Image:
    """Create a desaturated banned champion icon with red X."""
    icon_resized = icon.resize((size, size), Image.LANCZOS).convert("RGBA")
    # Desaturate
    gray = icon_resized.convert("L").convert("RGBA")
    enhancer = ImageEnhance.Brightness(gray)
    darkened = enhancer.enhance(0.5)
    # Red X
    draw = ImageDraw.Draw(darkened)
    draw.line([(3, 3), (size - 4, size - 4)], fill=(255, 50, 50, 220), width=2)
    draw.line([(size - 4, 3), (3, size - 4)], fill=(255, 50, 50, 220), width=2)
    return darkened


def _text_width(draw: ImageDraw.Draw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _find_tracked_player(
    details: MatchDetails, summoner_slug: str,
) -> tuple[int, int] | None:
    """Return (team_index, player_index) for the tracked player."""
    slug_as_name = summoner_slug.replace("-", "#").lower()
    for team_idx, players in enumerate([details.team1_players, details.team2_players]):
        for p_idx, p in enumerate(players):
            if p.summoner_name.lower().replace(" ", "") == slug_as_name.replace(" ", ""):
                return (team_idx, p_idx)
    return None


def _compute_mvps(players: list[MatchParticipant]) -> dict[str, int]:
    """Find index of best stat per category within a team."""
    if not players:
        return {}
    kda_ratios = [(p.kills + p.assists) / max(1, p.deaths) for p in players]
    return {
        "kda": kda_ratios.index(max(kda_ratios)),
        "cs": max(range(len(players)), key=lambda i: players[i].cs),
        "gold": max(range(len(players)), key=lambda i: players[i].gold),
        "vision": max(range(len(players)), key=lambda i: players[i].vision_score),
        "kp": max(range(len(players)), key=lambda i: players[i].kill_participation),
    }


def _find_game_mvp(details: MatchDetails) -> tuple[int, int] | None:
    """Find the game MVP (best KDA ratio across all 10 players)."""
    all_players = details.team1_players + details.team2_players
    if not all_players:
        return None
    ratios = [(p.kills + p.assists) / max(1, p.deaths) for p in all_players]
    best = ratios.index(max(ratios))
    n1 = len(details.team1_players)
    if best < n1:
        return (0, best)
    return (1, best - n1)


def _team_kills(players: list[MatchParticipant]) -> int:
    return sum(p.kills for p in players)


def _team_gold(players: list[MatchParticipant]) -> int:
    return sum(p.gold for p in players)


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_game_info(
    img: Image.Image, draw: ImageDraw.Draw, y: int,
    details: MatchDetails, game_mode: str, game_duration: str,
) -> int:
    """Render the game info bar: mode, duration, kill score, gold diff."""
    _rounded_rect(draw, [0, y, _WIDTH, y + _GAME_INFO_H], 0, _HEADER_BG)

    font = _font_regular(11)
    font_b = _font(11)
    text_y = y + (_GAME_INFO_H - 12) // 2

    x = _MARGIN + 4

    # Game mode
    if game_mode:
        draw.text((x, text_y), game_mode.upper(), fill=_LIGHT_GRAY, font=font)
        x += _text_width(draw, game_mode.upper(), font) + 12

    # Dot separator
    if game_mode and game_duration:
        draw.text((x, text_y), "\u2022", fill=_GRAY, font=font)
        x += 14

    # Duration
    if game_duration:
        draw.text((x, text_y), game_duration, fill=_LIGHT_GRAY, font=font)

    # Team kill score (centered)
    t1_kills = _team_kills(details.team1_players)
    t2_kills = _team_kills(details.team2_players)
    score_text = f"{t1_kills}  -  {t2_kills}"
    score_w = _text_width(draw, score_text, font_b)
    score_x = (_WIDTH - score_w) // 2
    # Blue kills
    draw.text((score_x, text_y), str(t1_kills), fill=_BLUE_ACCENT, font=font_b)
    dash_x = score_x + _text_width(draw, str(t1_kills), font_b)
    draw.text((dash_x, text_y), "  -  ", fill=_GRAY, font=font)
    red_x = dash_x + _text_width(draw, "  -  ", font)
    draw.text((red_x, text_y), str(t2_kills), fill=_RED_ACCENT, font=font_b)

    # Gold difference (right-aligned)
    t1_gold = _team_gold(details.team1_players)
    t2_gold = _team_gold(details.team2_players)
    diff = t1_gold - t2_gold
    sign = "+" if diff >= 0 else ""
    if abs(diff) >= 1000:
        gold_text = f"{sign}{diff / 1000:.1f}k gold"
    else:
        gold_text = f"{sign}{diff} gold"
    gold_color = _BLUE_ACCENT if diff >= 0 else _RED_ACCENT
    gw = _text_width(draw, gold_text, font)
    draw.text((_WIDTH - _MARGIN - gw - 4, text_y), gold_text, fill=gold_color, font=font)

    return y + _GAME_INFO_H


def _render_spotlight(
    img: Image.Image, draw: ImageDraw.Draw, y: int,
    details: MatchDetails, summoner_slug: str,
    tracked: tuple[int, int] | None,
) -> int:
    """Render the tracked player spotlight with splash art background."""
    if tracked is None:
        return y

    team_idx, p_idx = tracked
    players = details.team1_players if team_idx == 0 else details.team2_players
    player = players[p_idx]
    result = details.team1_result if team_idx == 0 else details.team2_result
    is_win = result.upper() == "WIN"

    # -- Background: splash art with dark overlay --
    splash = download_splash(player.champion, width=_WIDTH, height=_SPOTLIGHT_H)
    if splash:
        splash = splash.convert("RGBA")
        # Dark overlay
        overlay = Image.new("RGBA", (_WIDTH, _SPOTLIGHT_H), (18, 20, 24, 195))
        splash = Image.alpha_composite(splash, overlay)
        img.paste(splash, (0, y))
    else:
        # Fallback: gradient background
        accent = _BLUE_DARK if team_idx == 0 else _RED_DARK
        gradient = _make_gradient(_WIDTH, _SPOTLIGHT_H, accent, _BG)
        img.paste(gradient, (0, y))

    # Subtle accent line at top
    accent_color = _BLUE_ACCENT if team_idx == 0 else _RED_ACCENT
    draw.rectangle([0, y, _WIDTH, y + 2], fill=accent_color)

    # -- Champion icon (circular with rank border) --
    icon = download_icon(player.champion, size=_SPOTLIGHT_ICON)
    rank_col = _rank_color(player.rank)
    ix = _MARGIN + 16
    iy = y + 28
    if icon:
        circ = _circular_icon(icon, _SPOTLIGHT_ICON, rank_col, border_w=4)
        img.paste(circ, (ix, iy), circ)
    icon_right = ix + _SPOTLIGHT_ICON + 8 + 20

    # -- Player name --
    name_font = _font(22)
    name_y = y + 32
    draw.text((icon_right, name_y), player.summoner_name, fill=_GOLD, font=name_font)

    # -- Rank below name --
    rank_font = _font_regular(13)
    rank_y = name_y + 28
    draw.text((icon_right, rank_y), player.rank or "Unranked", fill=rank_col, font=rank_font)

    # -- KDA (large, right side) --
    kda_font = _font(30)
    kda_small_font = _font_regular(13)
    kda_str = f"{player.kills} / {player.deaths} / {player.assists}"
    kda_w = _text_width(draw, kda_str, kda_font)
    kda_x = _WIDTH - _MARGIN - kda_w - 16
    kda_y = y + 30

    # Render KDA with colored deaths
    k_str = str(player.kills)
    d_str = str(player.deaths)
    a_str = str(player.assists)
    slash = " / "

    cx = kda_x
    draw.text((cx, kda_y), k_str, fill=_WHITE, font=kda_font)
    cx += _text_width(draw, k_str, kda_font)
    draw.text((cx, kda_y), slash, fill=_GRAY, font=kda_font)
    cx += _text_width(draw, slash, kda_font)
    death_color = _RED_ACCENT if player.deaths >= 5 else _LIGHT_GRAY
    draw.text((cx, kda_y), d_str, fill=death_color, font=kda_font)
    cx += _text_width(draw, d_str, kda_font)
    draw.text((cx, kda_y), slash, fill=_GRAY, font=kda_font)
    cx += _text_width(draw, slash, kda_font)
    draw.text((cx, kda_y), a_str, fill=_WHITE, font=kda_font)

    # KDA ratio
    ratio = (player.kills + player.assists) / max(1, player.deaths)
    ratio_str = f"KDA {ratio:.2f}"
    ratio_color = _GREEN if ratio >= 3.0 else _GOLD if ratio >= 2.0 else _LIGHT_GRAY
    ratio_y = kda_y + 36
    rw = _text_width(draw, ratio_str, kda_small_font)
    draw.text((_WIDTH - _MARGIN - rw - 16, ratio_y), ratio_str, fill=ratio_color, font=kda_small_font)

    # -- Result badge (top-right) --
    badge_font = _font(11)
    badge_text = "VICTORY" if is_win else "DEFEAT"
    badge_color = (34, 139, 34) if is_win else (180, 30, 30)
    badge_outline = _GREEN if is_win else _RED_ACCENT
    bw = _text_width(draw, badge_text, badge_font) + 16
    bx = _WIDTH - _MARGIN - bw - 8
    by = y + 8
    _rounded_rect(draw, [bx, by, bx + bw, by + 22], 4, badge_color)
    draw.text((bx + 8, by + 4), badge_text, fill=_WHITE, font=badge_font)

    # -- Stat badges (bottom of spotlight) --
    badge_data = [
        ("CS", str(player.cs)),
        ("GOLD", f"{player.gold / 1000:.1f}k" if player.gold >= 1000 else str(player.gold)),
        ("KP", f"{player.kill_participation}%"),
        ("VISION", str(player.vision_score)),
    ]
    badge_w = 110
    badge_h = 38
    badge_gap = 12
    total_badges_w = len(badge_data) * badge_w + (len(badge_data) - 1) * badge_gap
    badge_start_x = (_WIDTH - total_badges_w) // 2
    badge_y = y + _SPOTLIGHT_H - badge_h - 16

    label_font = _font_regular(9)
    value_font = _font(14)

    for i, (label, value) in enumerate(badge_data):
        bx = badge_start_x + i * (badge_w + badge_gap)
        # Semi-transparent pill background
        pill = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
        pill_draw = ImageDraw.Draw(pill)
        try:
            pill_draw.rounded_rectangle([0, 0, badge_w, badge_h], radius=6, fill=(0, 0, 0, 130))
        except AttributeError:
            pill_draw.rectangle([0, 0, badge_w, badge_h], fill=(0, 0, 0, 130))
        img.paste(pill, (bx, badge_y), pill)

        # Label (centered)
        lw = _text_width(draw, label, label_font)
        draw.text((bx + (badge_w - lw) // 2, badge_y + 3), label, fill=_GRAY, font=label_font)
        # Value (centered)
        vw = _text_width(draw, value, value_font)
        draw.text((bx + (badge_w - vw) // 2, badge_y + 16), value, fill=_WHITE, font=value_font)

    return y + _SPOTLIGHT_H


def _render_bans(
    img: Image.Image, draw: ImageDraw.Draw, y: int,
    details: MatchDetails,
) -> int:
    """Render banned champions row."""
    if not details.team1_bans and not details.team2_bans:
        return y

    _rounded_rect(draw, [0, y, _WIDTH, y + _BANS_H], 0, _HEADER_BG)

    label_font = _font_regular(10)
    icon_size = 26
    icon_gap = 6

    # "BANS" label
    draw.text((_MARGIN + 4, y + (_BANS_H - 10) // 2), "BANS", fill=_GRAY, font=label_font)

    label_w = _text_width(draw, "BANS", label_font) + _MARGIN + 12
    center = _WIDTH // 2

    # Blue team bans (left of center)
    bans_total_w = len(details.team1_bans) * (icon_size + icon_gap) - icon_gap
    bx = center - bans_total_w - 20
    by = y + (_BANS_H - icon_size) // 2

    for champ in details.team1_bans:
        icon = download_icon(champ, size=icon_size)
        if icon:
            banned = _ban_icon_overlay(icon, icon_size)
            img.paste(banned, (bx, by), banned)
        else:
            # Placeholder gray circle
            draw.ellipse([bx + 2, by + 2, bx + icon_size - 2, by + icon_size - 2], fill=_SEPARATOR)
        bx += icon_size + icon_gap

    # Divider
    div_x = center
    draw.line([(div_x, y + 8), (div_x, y + _BANS_H - 8)], fill=_SEPARATOR, width=2)

    # Red team bans (right of center)
    bx = center + 20
    for champ in details.team2_bans:
        icon = download_icon(champ, size=icon_size)
        if icon:
            banned = _ban_icon_overlay(icon, icon_size)
            img.paste(banned, (bx, by), banned)
        else:
            draw.ellipse([bx + 2, by + 2, bx + icon_size - 2, by + icon_size - 2], fill=_SEPARATOR)
        bx += icon_size + icon_gap

    return y + _BANS_H


def _render_team_header(
    img: Image.Image, draw: ImageDraw.Draw, y: int,
    label: str, result: str, accent: tuple, dark: tuple,
    team_kda: str, team_gold: int,
) -> int:
    """Render a gradient team header with result, KDA, and gold."""
    # Gradient background
    gradient = _make_gradient(_WIDTH, _TEAM_HEADER_H, accent, _BG)
    # Reduce opacity
    overlay = Image.new("RGBA", (_WIDTH, _TEAM_HEADER_H), (*_BG, 140))
    gradient = Image.alpha_composite(gradient, overlay)
    img.paste(gradient, (0, y))

    # Accent bar on left
    draw.rectangle([0, y, 4, y + _TEAM_HEADER_H], fill=accent)

    hdr_font = _font(13)
    small_font = _font_regular(11)
    text_y = y + (_TEAM_HEADER_H - 14) // 2

    # Team label
    draw.text((_MARGIN + 8, text_y), label, fill=accent, font=hdr_font)

    # Team KDA (center-ish)
    kda_w = _text_width(draw, team_kda, small_font)
    draw.text((_WIDTH // 2 - kda_w // 2, text_y + 1), team_kda, fill=_LIGHT_GRAY, font=small_font)

    # Gold total
    if team_gold >= 1000:
        gold_str = f"{team_gold / 1000:.1f}k"
    else:
        gold_str = str(team_gold)
    gold_w = _text_width(draw, gold_str, small_font)
    draw.text((_WIDTH - _MARGIN - gold_w - 80, text_y + 1), gold_str, fill=_GOLD, font=small_font)

    # Result
    result_color = _GREEN if result.upper() == "WIN" else _RED_ACCENT
    result_font = _font(12)
    rw = _text_width(draw, result.upper(), result_font)
    draw.text((_WIDTH - _MARGIN - rw - 4, text_y), result.upper(), fill=result_color, font=result_font)

    return y + _TEAM_HEADER_H


def _render_col_headers(draw: ImageDraw.Draw, y: int) -> int:
    """Draw column header labels."""
    f = _font_regular(9)
    color = _GRAY
    draw.text((_COL_NAME, y + 2), "PLAYER", fill=color, font=f)
    draw.text((_COL_RANK, y + 2), "RANK", fill=color, font=f)
    draw.text((_COL_KDA, y + 2), "KDA", fill=color, font=f)
    draw.text((_COL_CS, y + 2), "CS", fill=color, font=f)
    draw.text((_COL_GOLD, y + 2), "GOLD", fill=color, font=f)
    draw.text((_COL_KP, y + 2), "KP", fill=color, font=f)
    draw.text((_COL_VS, y + 2), "VIS", fill=color, font=f)
    return y + _COL_HEADERS_H


def _render_player_row(
    img: Image.Image, draw: ImageDraw.Draw, y: int,
    player: MatchParticipant, bg_color: tuple,
    highlight: bool = False,
    mvp_stats: dict | None = None,
    player_idx: int = 0,
    is_game_mvp: bool = False,
) -> int:
    """Draw one player row with circular icon, rank border, and MVP markers."""
    _rounded_rect(draw, [0, y, _WIDTH, y + _ROW_H], 0, bg_color)

    name_font = _font(12) if highlight else _font_regular(12)
    stat_font = _font_regular(11)
    text_y = y + (_ROW_H - 13) // 2

    # -- Circular champion icon with rank border --
    icon = download_icon(player.champion, size=_ICON_SIZE)
    rank_col = _rank_color(player.rank)
    if icon:
        circ = _circular_icon(icon, _ICON_SIZE, rank_col, border_w=2)
        ix = _COL_ICON
        iy = y + (_ROW_H - circ.size[1]) // 2
        img.paste(circ, (ix, iy), circ)

    # -- Highlight marker for tracked player --
    if highlight:
        draw.rectangle([_COL_ICON - 2, y + 4, _COL_ICON, y + _ROW_H - 4], fill=_GOLD)

    # -- Player name --
    name_color = _GOLD if highlight else _WHITE
    name = player.summoner_name
    if len(name) > 16:
        name = name[:15] + "\u2026"
    draw.text((_COL_NAME, text_y), name, fill=name_color, font=name_font)

    # -- Game MVP crown --
    if is_game_mvp:
        crown_font = _font(10)
        mvp_label = "\u2605 MVP"
        mvp_x = _COL_NAME + _text_width(draw, name, name_font) + 6
        _rounded_rect(draw, [mvp_x, text_y - 1, mvp_x + 42, text_y + 13], 3, (180, 140, 20))
        draw.text((mvp_x + 3, text_y), mvp_label, fill=_WHITE, font=crown_font)

    # -- Rank --
    rank = player.rank if player.rank else "-"
    if len(rank) > 10:
        rank = rank[:9] + "."
    draw.text((_COL_RANK, text_y), rank, fill=rank_col, font=stat_font)

    # -- KDA --
    k, d, a = player.kills, player.deaths, player.assists
    kda_str = f"{k}/{d}/{a}"
    # Highlight if team MVP for KDA
    is_kda_mvp = mvp_stats and mvp_stats.get("kda") == player_idx
    kda_color = _MVP_GLOW if is_kda_mvp else _WHITE
    draw.text((_COL_KDA, text_y), kda_str, fill=kda_color, font=_font(11) if is_kda_mvp else stat_font)

    # KDA ratio
    ratio = (k + a) / d if d > 0 else float("inf")
    if ratio != float("inf"):
        ratio_str = f" ({ratio:.1f})"
        kda_bbox = draw.textbbox((_COL_KDA, text_y), kda_str, font=_font(11) if is_kda_mvp else stat_font)
        ratio_color = _GREEN if ratio >= 3.0 else _GRAY
        draw.text((kda_bbox[2] + 2, text_y + 1), ratio_str, fill=ratio_color, font=_font_regular(9))
    elif d == 0:
        kda_bbox = draw.textbbox((_COL_KDA, text_y), kda_str, font=stat_font)
        draw.text((kda_bbox[2] + 2, text_y + 1), " P", fill=_GREEN, font=_font(9))

    # -- CS --
    is_cs_mvp = mvp_stats and mvp_stats.get("cs") == player_idx
    cs_color = _MVP_GLOW if is_cs_mvp else _LIGHT_GRAY
    draw.text((_COL_CS, text_y), str(player.cs), fill=cs_color, font=_font(11) if is_cs_mvp else stat_font)

    # -- Gold --
    is_gold_mvp = mvp_stats and mvp_stats.get("gold") == player_idx
    gold_color = _MVP_GLOW if is_gold_mvp else _GOLD
    draw.text((_COL_GOLD, text_y), player.gold_display, fill=gold_color, font=_font(11) if is_gold_mvp else stat_font)

    # -- KP --
    kp_str = f"{player.kill_participation}%" if player.kill_participation else "-"
    is_kp_mvp = mvp_stats and mvp_stats.get("kp") == player_idx
    kp_color = _MVP_GLOW if is_kp_mvp else _LIGHT_GRAY
    draw.text((_COL_KP, text_y), kp_str, fill=kp_color, font=_font(11) if is_kp_mvp else stat_font)

    # -- Vision --
    vs_str = str(player.vision_score) if player.vision_score else "-"
    is_vis_mvp = mvp_stats and mvp_stats.get("vision") == player_idx
    vis_color = _MVP_GLOW if is_vis_mvp else _LIGHT_GRAY
    draw.text((_COL_VS, text_y), vs_str, fill=vis_color, font=_font(11) if is_vis_mvp else stat_font)

    # -- MVP dot indicators --
    mvp_count = sum(1 for cat in ("kda", "cs", "gold", "vision", "kp")
                    if mvp_stats and mvp_stats.get(cat) == player_idx)
    if mvp_count >= 2:
        for dot_i in range(min(mvp_count, 5)):
            dx = _COL_MVP + dot_i * 8
            dy = text_y + 3
            draw.ellipse([dx, dy, dx + 5, dy + 5], fill=_MVP_GLOW)

    # -- Row separator --
    draw.line(
        [(_MARGIN, y + _ROW_H - 1), (_WIDTH - _MARGIN, y + _ROW_H - 1)],
        fill=_SEPARATOR, width=1,
    )

    return y + _ROW_H


def _render_team(
    img: Image.Image, draw: ImageDraw.Draw, y: int,
    players: list[MatchParticipant], result: str,
    accent: tuple, dark: tuple,
    row_bg: tuple, row_hl: tuple,
    tracked: tuple[int, int] | None, team_idx: int,
    game_mvp: tuple[int, int] | None,
) -> int:
    """Render a full team section: header + columns + player rows."""
    team_kda = f"{sum(p.kills for p in players)}/{sum(p.deaths for p in players)}/{sum(p.assists for p in players)}"
    team_gold = sum(p.gold for p in players)

    y = _render_team_header(img, draw, y, "BLUE TEAM" if team_idx == 0 else "RED TEAM",
                            result, accent, dark, team_kda, team_gold)
    y = _render_col_headers(draw, y)

    mvps = _compute_mvps(players)

    for i, player in enumerate(players):
        is_tracked = tracked == (team_idx, i)
        bg = row_hl if is_tracked else row_bg
        is_mvp = game_mvp == (team_idx, i)
        y = _render_player_row(
            img, draw, y, player, bg,
            highlight=is_tracked, mvp_stats=mvps, player_idx=i,
            is_game_mvp=is_mvp,
        )

    return y


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_scoreboard(
    details: MatchDetails,
    summoner_slug: str,
    game_mode: str = "",
    game_duration: str = "",
) -> bytes | None:
    """Render a premium 5v5 scoreboard PNG.

    Returns PNG bytes or None if details are incomplete.
    """
    if not details.team1_players or not details.team2_players:
        return None

    tracked = _find_tracked_player(details, summoner_slug)
    game_mvp = _find_game_mvp(details)

    n1 = len(details.team1_players)
    n2 = len(details.team2_players)
    has_bans = bool(details.team1_bans or details.team2_bans)
    has_spotlight = tracked is not None

    # Calculate total height
    total_h = _SECTION_GAP  # top padding
    total_h += _GAME_INFO_H + _SECTION_GAP
    if has_spotlight:
        total_h += _SPOTLIGHT_H + _SECTION_GAP
    if has_bans:
        total_h += _BANS_H + _SECTION_GAP
    total_h += _TEAM_HEADER_H + _COL_HEADERS_H + n1 * _ROW_H
    total_h += _TEAM_GAP
    total_h += _TEAM_HEADER_H + _COL_HEADERS_H + n2 * _ROW_H
    total_h += _SECTION_GAP + 4  # bottom padding

    img = Image.new("RGBA", (_WIDTH, total_h), _BG)
    draw = ImageDraw.Draw(img)

    y = _SECTION_GAP

    # Game info bar
    y = _render_game_info(img, draw, y, details, game_mode, game_duration)
    y += _SECTION_GAP

    # Tracked player spotlight
    if has_spotlight:
        y = _render_spotlight(img, draw, y, details, summoner_slug, tracked)
        y += _SECTION_GAP

    # Bans
    if has_bans:
        y = _render_bans(img, draw, y, details)
        y += _SECTION_GAP

    # Blue team
    y = _render_team(
        img, draw, y, details.team1_players, details.team1_result,
        _BLUE_ACCENT, _BLUE_DARK, _ROW_BLUE, _ROW_BLUE_HL,
        tracked, 0, game_mvp,
    )

    y += _TEAM_GAP

    # Red team
    y = _render_team(
        img, draw, y, details.team2_players, details.team2_result,
        _RED_ACCENT, _RED_DARK, _ROW_RED, _ROW_RED_HL,
        tracked, 1, game_mvp,
    )

    # -- Final touches: rounded corners on full image --
    mask = Image.new("L", img.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    try:
        mask_draw.rounded_rectangle([0, 0, _WIDTH, total_h], radius=_CORNER_R, fill=255)
    except AttributeError:
        mask_draw.rectangle([0, 0, _WIDTH, total_h], fill=255)

    final = Image.new("RGBA", img.size, (0, 0, 0, 0))
    final.paste(img, (0, 0), mask)

    buf = BytesIO()
    final.save(buf, format="PNG")
    return buf.getvalue()
