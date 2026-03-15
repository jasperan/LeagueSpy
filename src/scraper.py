import logging
import asyncio
import hashlib
import re
from typing import List, Optional

from scrapling.fetchers import StealthyFetcher
from src.models import SummonerConfig, MatchResult

logger = logging.getLogger("leaguespy.scraper")

# CSS variable patterns that distinguish wins from losses in op.gg game items.
# Wins use theme(colors.main.*), losses use theme(colors.red.*).
_WIN_PATTERN = re.compile(r"colors\.main\.\d+")
_LOSS_PATTERN = re.compile(r"colors\.red\.\d+")

# KDA tooltip format: "(K 2 + A 20) / D 2"
_KDA_TOOLTIP_RE = re.compile(r"\(K\s*(\d+)\s*\+\s*A\s*(\d+)\)\s*/\s*D\s*(\d+)")

# Duration pattern: "37m 48s"
_DURATION_RE = re.compile(r"(\d+m\s*\d+s)")


class OpGGScraper:
    """Scrapes op.gg summoner profile pages for match history."""

    # The game-item container selector. op.gg renders each game as a div
    # with a 6px left border colored by win/loss CSS variables.
    GAME_ITEM_SELECTOR = 'div[class*="border-l-[6px]"]'

    def __init__(self, delay_between_requests: float = 2.0):
        self.delay = delay_between_requests

    @staticmethod
    def _sync_fetch(url: str):
        """Run the synchronous StealthyFetcher in a thread.

        scrapling's ``async_fetch`` crashes with a TargetClosedError on
        headless Chromium in some environments.  The sync ``fetch`` works
        reliably, so we wrap it with ``asyncio.to_thread`` to keep the
        public API async.
        """
        return StealthyFetcher.fetch(url, headless=True, network_idle=True)

    async def fetch_page(self, summoner: SummonerConfig):
        """Fetch the op.gg profile page for a summoner."""
        url = summoner.op_gg_url
        logger.info("Fetching %s", url)
        page = await asyncio.to_thread(self._sync_fetch, url)
        if page.status != 200:
            logger.warning("Got status %d for %s", page.status, url)
            return None
        return page

    def _determine_win(self, game_html: str) -> bool:
        """Determine win/loss from the game container's CSS variable colors.

        Wins use ``theme(colors.main.*)``, losses use ``theme(colors.red.*)``.
        Falls back to searching for 'Victory'/'Defeat' text.
        """
        if _LOSS_PATTERN.search(game_html):
            return False
        if _WIN_PATTERN.search(game_html):
            return True
        # Fallback: look for Victory/Defeat text
        if "Defeat" in game_html:
            return False
        return True  # default to win if ambiguous

    def _extract_kda(self, game_html: str) -> tuple:
        """Extract kills, deaths, assists from the KDA tooltip.

        The tooltip has format: ``(K 2 + A 20) / D 2``
        """
        m = _KDA_TOOLTIP_RE.search(game_html)
        if m:
            return int(m.group(1)), int(m.group(3)), int(m.group(2))
        # Fallback: try inline KDA pattern
        # <strong class="text-gray-900">K</strong>/<strong class="text-red-600">D</strong>/<strong class="text-gray-900">A</strong>
        inline = re.findall(
            r'<strong[^>]*>(\d+)</strong>\s*/\s*<strong[^>]*>(\d+)</strong>\s*/\s*<strong[^>]*>(\d+)</strong>',
            game_html,
        )
        if inline:
            k, d, a = inline[0]
            return int(k), int(d), int(a)
        return 0, 0, 0

    def _extract_champion(self, game_html: str) -> str:
        """Extract champion name from the first img alt attribute."""
        m = re.search(r'alt="([^"]+)"', game_html)
        return m.group(1) if m else "Unknown"

    def _extract_duration(self, game_html: str) -> str:
        """Extract game duration (e.g. '37m 48s')."""
        m = _DURATION_RE.search(game_html)
        return m.group(1) if m else "0m 0s"

    def _extract_game_mode(self, game_html: str) -> str:
        """Extract game mode from the styled span.

        op.gg renders the mode inside a span with class containing
        ``md:font-bold md:text-[var(--game-item-color-600)]``.
        """
        m = re.search(
            r'md:font-bold\s+md:text-\[var\(--game-item-color-600\)\]">\s*([^<]+?)\s*</span>',
            game_html,
        )
        return m.group(1).strip() if m else "Unknown"

    def _extract_played_at(self, game_html: str) -> str:
        """Extract the timestamp from the tooltip on the 'X ago' span.

        The tooltip contains the exact date, e.g. ``3/13/2026, 8:20 PM``.
        Falls back to the relative time text (e.g. '2 days ago').
        """
        # Exact date from tooltip
        m = re.search(
            r'data-tooltip-content="(\d+/\d+/\d+,\s*\d+:\d+\s*[AP]M)"',
            game_html,
        )
        if m:
            return m.group(1)
        # Fallback: relative time
        m = re.search(r'>(\d+\s*(?:days?|hours?|minutes?|seconds?)\s*ago)<', game_html)
        return m.group(1) if m else "Unknown"

    def _generate_match_id(self, summoner: SummonerConfig, champion: str, played_at: str) -> str:
        """Generate a stable match ID from available data.

        op.gg doesn't expose Riot match IDs in the HTML, so we hash
        the summoner slug + champion + timestamp to create a unique identifier.
        """
        raw = f"{summoner.slug}:{champion}:{played_at}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def parse_matches(self, page, summoner: SummonerConfig) -> List[MatchResult]:
        """Parse match history from an op.gg page response.

        Uses scrapling's Adaptor CSS selector API to find game containers,
        then falls back to regex on each container's outer HTML to extract
        individual fields. This hybrid approach handles op.gg's Tailwind
        utility classes (which aren't easily targeted with pure CSS selectors).
        """
        matches: List[MatchResult] = []

        game_elements = page.css(self.GAME_ITEM_SELECTOR)
        if not game_elements:
            logger.warning("No game elements found with selector: %s", self.GAME_ITEM_SELECTOR)
            return matches

        logger.info("Found %d game elements", len(game_elements))

        for game in game_elements[:20]:
            try:
                game_html = game.html if hasattr(game, "html") else str(game)

                champion = self._extract_champion(game_html)
                win = self._determine_win(game_html)
                kills, deaths, assists = self._extract_kda(game_html)
                duration = self._extract_duration(game_html)
                mode = self._extract_game_mode(game_html)
                played_at = self._extract_played_at(game_html)
                match_id = self._generate_match_id(summoner, champion, played_at)

                result = MatchResult(
                    match_id=match_id,
                    champion=champion,
                    win=win,
                    kills=kills,
                    deaths=deaths,
                    assists=assists,
                    game_duration=duration,
                    game_mode=mode,
                    played_at=played_at,
                )
                matches.append(result)

            except Exception as e:
                logger.error("Failed to parse match element: %s", e)
                continue

        return matches

    async def fetch_matches(self, summoner: SummonerConfig) -> List[MatchResult]:
        """Fetch and parse matches for a single summoner.

        Returns matches in chronological order (oldest first) so that
        when announced sequentially, the freshest game appears last
        (at the bottom of the Discord channel).
        """
        page = await self.fetch_page(summoner)
        if page is None:
            return []
        matches = self.parse_matches(page, summoner)
        matches.reverse()
        return matches

    async def fetch_all(self, summoners: List[SummonerConfig]) -> dict[str, List[MatchResult]]:
        """Fetch matches for all summoners with a delay between requests."""
        results: dict[str, List[MatchResult]] = {}
        for summoner in summoners:
            matches = await self.fetch_matches(summoner)
            results[summoner.slug] = matches
            if self.delay > 0:
                await asyncio.sleep(self.delay)
        return results
