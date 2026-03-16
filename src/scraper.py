import logging
import asyncio
import re
from typing import List
from datetime import datetime, timezone

from playwright.async_api import async_playwright
from src.models import SummonerConfig, MatchResult

logger = logging.getLogger("leaguespy.scraper")

# KDA spans: <span class="kills">1</span> / <span class="deaths">0</span> / <span class="assists">12</span>
_KDA_RE = re.compile(
    r'class="kills">(\d+)</span>.*?class="deaths">(\d+)</span>.*?class="assists">(\d+)</span>',
    re.DOTALL,
)

# Match ID from href: /match/euw/7781974656#participant5
_MATCH_ID_RE = re.compile(r'/match/\w+/(\d+)')

# Duration: "19min 48s" or "32min 1s"
_DURATION_RE = re.compile(r'(\d+min\s*\d+s)')

# Epoch timestamp from tooltip script: new Date(1773616809941)
_EPOCH_RE = re.compile(r'new Date\((\d{13})\)')

# Stealth init script to bypass bot detection
_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = {runtime: {}};
"""


class LeagueOfGraphsScraper:
    """Scrapes leagueofgraphs.com summoner pages for match history.

    Uses a single shared browser with stealth evasions. Concurrent page
    tabs are limited by a semaphore.
    """

    def __init__(self, max_concurrent: int = 3):
        self.sem = asyncio.Semaphore(max_concurrent)
        self._pw = None
        self._browser = None
        self._ctx = None

    async def start(self):
        """Launch a shared stealth browser context."""
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._ctx = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        await self._ctx.add_init_script(_STEALTH_JS)
        # Warm-up: load the site once to accept cookies and prime the session
        warmup = await self._ctx.new_page()
        try:
            await warmup.goto("https://www.leagueofgraphs.com", wait_until="domcontentloaded", timeout=15000)
            await warmup.wait_for_timeout(2000)
            # Click cookie consent button if present
            try:
                btn = warmup.locator("button:has-text('Accept'), button:has-text('Agree'), .fc-cta-consent")
                if await btn.count() > 0:
                    await btn.first.click()
                    await warmup.wait_for_timeout(1000)
                    logger.info("Cookie consent accepted")
            except Exception:
                pass
        except Exception:
            pass
        finally:
            await warmup.close()
        logger.info("Stealth browser launched")

    async def stop(self):
        """Close browser and playwright."""
        if self._ctx:
            await self._ctx.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        logger.info("Browser closed")

    async def _fetch_page_html(self, url: str) -> str | None:
        """Open a new tab, navigate, wait for match data, return HTML."""
        page = await self._ctx.new_page()
        try:
            logger.info("Fetching %s", url)
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            if resp and resp.status != 200:
                logger.warning("Got status %d for %s", resp.status, url)
                return None
            # Wait for match data to load via AJAX (up to 15s)
            try:
                await page.wait_for_selector(
                    "td.championCellLight", timeout=15000,
                )
            except Exception:
                # Fallback: wait a fixed period and hope for the best
                await page.wait_for_timeout(5000)
            return await page.content()
        except Exception as e:
            logger.error("Failed to fetch %s: %s", url, e)
            return None
        finally:
            await page.close()

    def _parse_rows(self, html: str) -> list[str]:
        """Extract match table rows from the page HTML.

        leagueofgraphs renders each match as a <tr> inside a table with
        class ``recentGamesTable inverted_rows_color``. However the rows
        may not parse cleanly with a simple regex because of nested
        elements. Instead we split on match ID anchors.
        """
        table = re.search(
            r'<table[^>]*recentGamesTable inverted_rows_color[^>]*>(.*?)</table>',
            html, re.DOTALL,
        )
        if not table:
            return []

        tbody = table.group(1)
        # Split by match links to get per-match chunks
        parts = re.split(r'(?=<td class="championCellLight")', tbody)
        return [p for p in parts if _MATCH_ID_RE.search(p)]

    def _extract_match_id(self, row: str) -> str | None:
        m = _MATCH_ID_RE.search(row)
        return m.group(1) if m else None

    def _extract_champion(self, row: str) -> str:
        m = re.search(r'alt="([^"]+)"', row)
        return m.group(1) if m else "Unknown"

    def _extract_win(self, row: str) -> bool:
        return "victoryDefeatText victory" in row

    def _extract_kda(self, row: str) -> tuple[int, int, int]:
        m = _KDA_RE.search(row)
        if m:
            return int(m.group(1)), int(m.group(2)), int(m.group(3))
        return 0, 0, 0

    def _extract_duration(self, row: str) -> str:
        m = _DURATION_RE.search(row)
        return m.group(1) if m else "0min 0s"

    def _extract_game_mode(self, row: str) -> str:
        m = re.search(r'gameMode[^>]*tooltip="([^"]+)"', row)
        return m.group(1).strip() if m else "Unknown"

    def _extract_played_at(self, row: str) -> str:
        m = _EPOCH_RE.search(row)
        if m:
            ts = int(m.group(1)) / 1000
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M UTC")
        # Fallback: relative time from gameDate
        m = re.search(r'gameDate[^>]*>\s*([^<]+?)\s*<', row)
        return m.group(1).strip() if m else "Unknown"

    def parse_matches(self, html: str, summoner: SummonerConfig) -> List[MatchResult]:
        rows = self._parse_rows(html)
        matches: List[MatchResult] = []

        for row in rows:
            match_id = self._extract_match_id(row)
            if not match_id:
                continue

            try:
                matches.append(MatchResult(
                    match_id=match_id,
                    champion=self._extract_champion(row),
                    win=self._extract_win(row),
                    kills=self._extract_kda(row)[0],
                    deaths=self._extract_kda(row)[1],
                    assists=self._extract_kda(row)[2],
                    game_duration=self._extract_duration(row),
                    game_mode=self._extract_game_mode(row),
                    played_at=self._extract_played_at(row),
                ))
            except Exception as e:
                logger.error("Failed to parse match %s: %s", match_id, e)

        logger.info("Found %d matches for %s", len(matches), summoner.slug)
        return matches

    async def fetch_matches(self, summoner: SummonerConfig) -> List[MatchResult]:
        """Fetch and parse matches for a single summoner (semaphore-limited).

        Returns matches in chronological order (oldest first) so the
        freshest game appears last (bottom of Discord channel).
        """
        async with self.sem:
            html = await self._fetch_page_html(summoner.profile_url)
        if not html:
            return []
        matches = self.parse_matches(html, summoner)
        matches.reverse()
        return matches
