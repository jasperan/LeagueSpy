import logging
import asyncio
import re
from typing import List
from datetime import datetime, timezone

from playwright.async_api import async_playwright
from src.models import SummonerConfig, MatchResult, MatchParticipant, MatchDetails

logger = logging.getLogger("leaguespy.scraper")

# KDA spans: <span class="kills">1</span> / <span class="deaths">0</span> / <span class="assists">12</span>
_KDA_RE = re.compile(
    r'class="kills">(\d+)</span>.*?class="deaths">(\d+)</span>.*?class="assists">(\d+)</span>',
    re.DOTALL,
)

# Match ID from href: /match/euw/7781974656#participant5
_MATCH_ID_RE = re.compile(r'/match/\w+/(\d+)')

# Full match URL path including participant anchor: /match/euw/7781974656#participant5
_MATCH_URL_RE = re.compile(r'(/match/\w+/\d+#participant\d+)')

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

    def _extract_match_url(self, row: str) -> str | None:
        m = _MATCH_URL_RE.search(row)
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

    def parse_in_game_status(self, html: str) -> dict:
        """Check if the summoner page shows an active game indicator."""
        in_game = "current-game" in html
        champion = None
        if in_game:
            m = re.search(r'current-game.*?alt="([^"]+)"', html, re.DOTALL)
            if m:
                champion = m.group(1)
        return {"in_game": in_game, "champion": champion}

    async def check_in_game(self, summoner) -> dict:
        """Fetch a summoner page and check if they're currently in game."""
        async with self.sem:
            html = await self._fetch_page_html(summoner.profile_url)
        if not html:
            return {"in_game": False, "champion": None}
        return self.parse_in_game_status(html)

    def parse_matches(self, html: str, summoner: SummonerConfig) -> List[MatchResult]:
        rows = self._parse_rows(html)
        matches: List[MatchResult] = []

        for row in rows:
            match_id = self._extract_match_id(row)
            if not match_id:
                continue

            try:
                kills, deaths, assists = self._extract_kda(row)
                matches.append(MatchResult(
                    match_id=match_id,
                    champion=self._extract_champion(row),
                    win=self._extract_win(row),
                    kills=kills,
                    deaths=deaths,
                    assists=assists,
                    game_duration=self._extract_duration(row),
                    game_mode=self._extract_game_mode(row),
                    played_at=self._extract_played_at(row),
                    match_url=self._extract_match_url(row),
                ))
            except Exception as e:
                logger.error("Failed to parse match %s: %s", match_id, e)

        logger.info("Found %d matches for %s", len(matches), summoner.slug)
        return matches

    def _parse_kda_stats(self, kda_section: str) -> tuple:
        """Parse a kdaColumn section for KDA + CS/gold/KP/vision from visible divs.

        Returns (kills, deaths, assists, cs, gold, kill_participation, vision_score).
        """
        kills = deaths = assists = cs = gold = kp = vision = 0

        # KDA from spans
        k_m = re.search(r'class="kills">(\d+)', kda_section)
        d_m = re.search(r'class="deaths">(\d+)', kda_section)
        a_m = re.search(r'class="assists">(\d+)', kda_section)
        if k_m:
            kills = int(k_m.group(1))
        if d_m:
            deaths = int(d_m.group(1))
        if a_m:
            assists = int(a_m.group(1))

        # CS and gold from visible div: "352 CS - 16.3k gold"
        cs_divs = re.findall(r'<div\s+class="cs"[^>]*>\s*(.*?)\s*</div>', kda_section, re.DOTALL)
        if cs_divs:
            # First cs div: "352 CS - 16.3k gold"
            cs_gold_text = cs_divs[0]
            cs_m = re.search(r'(\d+)\s*CS', cs_gold_text)
            if cs_m:
                cs = int(cs_m.group(1))
            gold_m = re.search(r'([\d.]+)k\s*gold', cs_gold_text)
            if gold_m:
                gold = int(float(gold_m.group(1)) * 1000)

        if len(cs_divs) > 1:
            # Second cs div: "26% Kills P. - Vision: 55"
            kp_vision_text = cs_divs[1]
            kp_m = re.search(r'(\d+)%', kp_vision_text)
            if kp_m:
                kp = int(kp_m.group(1))
            vis_m = re.search(r'Vision:\s*(\d+)', kp_vision_text)
            if vis_m:
                vision = int(vis_m.group(1))

        return (kills, deaths, assists, cs, gold, kp, vision)

    def _parse_player_left(self, row: str) -> MatchParticipant | None:
        """Parse the left (team1) player from a playerRow."""
        # Extract left summoner column
        col = re.search(r'<td[^>]*text-left[^>]*summoner_column[^>]*>(.*?)</td>', row, re.DOTALL)
        if not col:
            return None

        col_html = col.group(1)
        name_m = re.search(r'<div class="name">\s*([^<]+?)\s*</div>', col_html)
        champ_m = re.search(r'alt="([^"]+)"', col_html)
        rank_m = re.search(r'subname[^>]*>.*?<i[^>]*>\s*(.*?)\s*</i>', col_html, re.DOTALL)

        summoner_name = name_m.group(1).strip() if name_m else "Unknown"
        champion = champ_m.group(1) if champ_m else "Unknown"
        rank = rank_m.group(1).strip() if rank_m else "Unranked"

        # First kdaColumn in the row is for team1 (left)
        kda_cols = list(re.finditer(r'<td[^>]*kdaColumn[^>]*>(.*?)</td>', row, re.DOTALL))
        if not kda_cols:
            return None

        kills, deaths, assists, cs, gold, kp, vision = self._parse_kda_stats(kda_cols[0].group(1))

        return MatchParticipant(
            summoner_name=summoner_name,
            rank=rank,
            champion=champion,
            kills=kills,
            deaths=deaths,
            assists=assists,
            cs=cs,
            gold=gold,
            kill_participation=kp,
            vision_score=vision,
        )

    def _parse_player_right(self, row: str) -> MatchParticipant | None:
        """Parse the right (team2) player from a playerRow."""
        # Extract right summoner column
        col = re.search(r'<td[^>]*text-right[^>]*summoner_column[^>]*>(.*?)</td>', row, re.DOTALL)
        if not col:
            return None

        col_html = col.group(1)
        name_m = re.search(r'<div class="name">\s*([^<]+?)\s*</div>', col_html)
        champ_m = re.search(r'alt="([^"]+)"', col_html)
        rank_m = re.search(r'subname[^>]*>.*?<i[^>]*>\s*(.*?)\s*</i>', col_html, re.DOTALL)

        summoner_name = name_m.group(1).strip() if name_m else "Unknown"
        champion = champ_m.group(1) if champ_m else "Unknown"
        rank = rank_m.group(1).strip() if rank_m else "Unranked"

        # Second kdaColumn in the row is for team2 (right)
        kda_cols = list(re.finditer(r'<td[^>]*kdaColumn[^>]*>(.*?)</td>', row, re.DOTALL))
        if len(kda_cols) < 2:
            return None

        kills, deaths, assists, cs, gold, kp, vision = self._parse_kda_stats(kda_cols[1].group(1))

        return MatchParticipant(
            summoner_name=summoner_name,
            rank=rank,
            champion=champion,
            kills=kills,
            deaths=deaths,
            assists=assists,
            cs=cs,
            gold=gold,
            kill_participation=kp,
            vision_score=vision,
        )

    def parse_match_details(self, html: str) -> MatchDetails | None:
        """Parse a match detail page for all 10 players and bans.

        Expects the HTML from a page like /match/euw/7782016191.
        Returns None if the matchTable is not found.
        """
        # Find the matchTable
        table_m = re.search(r'<table[^>]*matchTable[^>]*>(.*?)</table>', html, re.DOTALL)
        if not table_m:
            return None

        table_html = table_m.group(0)

        # Team results from header row
        result_spans = re.findall(r'<span class="(victory|defeat)">\s*(\w+)\s*</span>', table_html)
        team1_result = result_spans[0][1] if result_spans else "Unknown"
        team2_result = result_spans[1][1] if len(result_spans) > 1 else "Unknown"

        # Player rows
        player_rows = re.findall(
            r'<tr[^>]*class="[^"]*playerRow[^"]*"[^>]*>(.*?)</tr>',
            table_html, re.DOTALL,
        )

        team1_players = []
        team2_players = []
        for row_content in player_rows:
            # Wrap back in <tr> so TD patterns work consistently
            row = f"<tr>{row_content}</tr>"

            left = self._parse_player_left(row)
            if left:
                team1_players.append(left)

            right = self._parse_player_right(row)
            if right:
                team2_players.append(right)

        # Bans: two bansColumn TDs
        bans_cols = re.findall(r'<td[^>]*bansColumn[^>]*>(.*?)</td>', table_html, re.DOTALL)
        team1_bans = []
        team2_bans = []
        if bans_cols:
            team1_bans = re.findall(r'bannedChampion[^>]*tooltip="([^"]+)"', bans_cols[0])
        if len(bans_cols) > 1:
            team2_bans = re.findall(r'bannedChampion[^>]*tooltip="([^"]+)"', bans_cols[1])

        return MatchDetails(
            team1_players=team1_players,
            team2_players=team2_players,
            team1_result=team1_result,
            team2_result=team2_result,
            team1_bans=team1_bans,
            team2_bans=team2_bans,
        )

    async def fetch_match_details(self, match_url: str, region: str) -> MatchDetails | None:
        """Fetch and parse a match detail page (semaphore-limited).

        Args:
            match_url: Path like /match/euw/7782016191#participant10
            region: Region string (unused but kept for future routing)

        Returns:
            MatchDetails if the page parsed successfully, None otherwise.
        """
        full_url = f"https://www.leagueofgraphs.com{match_url}"
        async with self.sem:
            html = await self._fetch_page_html(full_url)
        if html is None:
            return None
        return self.parse_match_details(html)

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
