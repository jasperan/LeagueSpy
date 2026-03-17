"""Weekly power rankings renderer."""

from __future__ import annotations

import logging
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from src.champion_icons import download_icon

logger = logging.getLogger("leaguespy.rankings")

_BG_COLOR = (43, 45, 49)
_TEXT_WHITE = (255, 255, 255)
_TEXT_GRAY = (148, 155, 164)
_GREEN = (87, 242, 135)
_RED = (237, 66, 69)
_GOLD = (254, 185, 56)
_FRAME_WIDTH = 600
_MARGIN = 30
_ICON_SIZE = 36


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


def compute_power_score(win_rate: float, avg_kda_ratio: float, games: int, max_games: int) -> float:
    if games == 0:
        return 0
    games_norm = games / max_games if max_games > 0 else 0
    return round((win_rate * 50) + (min(avg_kda_ratio, 10) * 3) + (games_norm * 20), 1)


def render_power_rankings(players: list[dict]) -> Image.Image | None:
    if not players:
        return None

    max_games = max(p["games"] for p in players)
    scored = []
    for p in players:
        wr = p["wins"] / p["games"] if p["games"] > 0 else 0
        deaths = p["avg_deaths"] or 1
        kda_r = (p["avg_kills"] + p["avg_assists"]) / deaths
        score = compute_power_score(wr, kda_r, p["games"], max_games)
        scored.append({**p, "score": score, "win_rate": wr})

    scored.sort(key=lambda x: x["score"], reverse=True)

    row_height = 55
    header_height = 80
    frame_height = header_height + len(scored) * row_height + _MARGIN

    img = Image.new("RGB", (_FRAME_WIDTH, frame_height), _BG_COLOR)
    draw = ImageDraw.Draw(img)

    title_font = _load_font(22)
    name_font = _load_font(18)
    stats_font = _load_font(14)

    draw.rectangle([0, 0, 5, frame_height], fill=_GOLD)
    draw.text((_MARGIN, _MARGIN), "POWER RANKINGS SEMANAL", fill=_GOLD, font=title_font)

    y = header_height
    decorations = ["\U0001f451", "\U0001f948", "\U0001f949"]

    for i, p in enumerate(scored):
        if i < len(decorations):
            deco = decorations[i]
        elif i == len(scored) - 1 and len(scored) > 3:
            deco = "\U0001f921"
        else:
            deco = f"#{i+1}"

        icon = download_icon(p.get("top_champion", ""), size=_ICON_SIZE)
        if icon:
            img.paste(icon, (_MARGIN, y + 5), icon if icon.mode == "RGBA" else None)

        x_name = _MARGIN + _ICON_SIZE + 10
        draw.text((x_name, y + 2), f"{deco} {p['player_name']}", fill=_TEXT_WHITE, font=name_font)

        wr_pct = round(p["win_rate"] * 100, 1)
        wr_color = _GREEN if wr_pct >= 50 else _RED
        info = f"{p['games']}G | {wr_pct}% WR | Score: {p['score']}"
        draw.text((x_name, y + 25), info, fill=_TEXT_GRAY, font=stats_font)

        bar_x = _FRAME_WIDTH - _MARGIN - 100
        bar_w = 80
        bar_h = 8
        bar_y = y + 20
        draw.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], fill=(60, 63, 68))
        fill_w = int(bar_w * p["win_rate"])
        if fill_w > 0:
            draw.rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], fill=wr_color)

        y += row_height

    return img
