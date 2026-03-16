"""Champion icon URL resolution and download via Riot Data Dragon CDN."""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------
_current_version: str | None = None
_version_fetched_at: float = 0.0
_VERSION_TTL = 6 * 3600  # re-fetch DDragon version every 6 hours

DDRAGON_BASE = "https://ddragon.leagueoflegends.com"
ICON_CACHE_DIR = Path("/tmp/leaguespy_icons")

# ---------------------------------------------------------------------------
# Special-case mappings (display name -> DDragon key)
# ---------------------------------------------------------------------------
_SPECIAL_CASES: dict[str, str] = {
    "Wukong": "MonkeyKing",
    "Renata Glasc": "Renata",
    "Nunu & Willump": "Nunu",
}


def normalize_champion_name(display_name: str) -> str:
    """Convert a human-readable champion name to its DDragon key.

    Rules applied in order:
    1. Check special-case map first.
    2. Strip apostrophes.
    3. Remove spaces.
    """
    if display_name in _SPECIAL_CASES:
        return _SPECIAL_CASES[display_name]

    # DDragon lowercases the letter immediately following an apostrophe in all
    # current champion keys (e.g. Kha'Zix -> Khazix, Vel'Koz -> Velkoz).
    # If Riot ever deviates from this, add the champion to _SPECIAL_CASES.
    name = re.sub(r"'(\w)", lambda m: m.group(1).lower(), display_name)
    name = name.replace(" ", "")
    return name


def fetch_ddragon_version() -> str:
    """Fetch the latest DDragon version string, caching the result.

    Falls back to ``"14.6.1"`` on any network or parsing error.
    """
    global _current_version, _version_fetched_at  # noqa: PLW0603

    if _current_version is not None and (time.monotonic() - _version_fetched_at) < _VERSION_TTL:
        return _current_version

    try:
        resp = httpx.get(f"{DDRAGON_BASE}/api/versions.json", timeout=10)
        resp.raise_for_status()
        versions = resp.json()
        _current_version = versions[0]
        _version_fetched_at = time.monotonic()
    except Exception:
        logger.warning("Failed to fetch DDragon version, falling back to 14.6.1")
        if _current_version is None:
            _current_version = "14.6.1"
            _version_fetched_at = time.monotonic()

    return _current_version


def get_icon_url(champion_name: str, version: str | None = None) -> str:
    """Return the DDragon champion square icon URL.

    Parameters
    ----------
    champion_name:
        Display name (e.g. ``"Lee Sin"``).
    version:
        DDragon patch version. Fetched automatically when *None*.
    """
    if version is None:
        version = fetch_ddragon_version()

    key = normalize_champion_name(champion_name)
    return f"{DDRAGON_BASE}/cdn/{version}/img/champion/{key}.png"


def download_icon(champion_name: str, size: int = 48):
    """Download a champion icon, resize it, and cache locally.

    Returns a ``PIL.Image.Image`` or *None* on failure.
    """
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        logger.error("Pillow is not installed; cannot download icons")
        return None

    key = normalize_champion_name(champion_name)
    cache_path = ICON_CACHE_DIR / f"{key}_{size}.png"

    if cache_path.exists():
        return Image.open(cache_path)

    url = get_icon_url(champion_name)

    try:
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
    except Exception:
        logger.warning("Failed to download icon for %s from %s", champion_name, url)
        return None

    try:
        import io  # noqa: PLC0415

        img = Image.open(io.BytesIO(resp.content))
        img = img.resize((size, size), Image.LANCZOS)

        os.makedirs(ICON_CACHE_DIR, exist_ok=True)
        img.save(cache_path, format="PNG")
        return img
    except Exception:
        logger.warning("Failed to process icon for %s", champion_name)
        return None
