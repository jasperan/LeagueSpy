import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.scraper import LeagueOfGraphsScraper, _KDA_RE, _MATCH_ID_RE, _DURATION_RE, _EPOCH_RE
from src.models import SummonerConfig, MatchResult


def _make_summoner():
    return SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")


# ---------------------------------------------------------------------------
# Sample HTML fragments matching leagueofgraphs.com format
# ---------------------------------------------------------------------------

_MATCH_ROW_WIN = (
    '<td class="championCellLight">'
    '<a href="/match/euw/7781974656#participant5">'
    '<img alt="Leona" src="/img/champions/Leona.png">'
    '</a></td>'
    '<td class="victoryDefeatText victory">Victory</td>'
    '<td><span class="kills">2</span> / <span class="deaths">1</span> / <span class="assists">20</span></td>'
    '<td><span>19min 48s</span></td>'
    '<td><span class="gameMode" tooltip="Ranked Solo/Duo">Ranked</span></td>'
    '<td><script>document.write(new Date(1773616809941).toLocaleString())</script>'
    '<span class="gameDate">2 days ago</span></td>'
)

_MATCH_ROW_LOSS = (
    '<td class="championCellLight">'
    '<a href="/match/euw/7781999999#participant2">'
    '<img alt="Janna" src="/img/champions/Janna.png">'
    '</a></td>'
    '<td class="victoryDefeatText defeat">Defeat</td>'
    '<td><span class="kills">1</span> / <span class="deaths">5</span> / <span class="assists">8</span></td>'
    '<td><span>32min 1s</span></td>'
    '<td><span class="gameMode" tooltip="Normal">Normal</span></td>'
    '<td><span class="gameDate">5 days ago</span></td>'
)

_FULL_TABLE_HTML = (
    '<table class="recentGamesTable inverted_rows_color">'
    '<tbody>'
    + _MATCH_ROW_WIN
    + _MATCH_ROW_LOSS
    + '</tbody></table>'
)


# ---------------------------------------------------------------------------
# Constructor / lifecycle tests
# ---------------------------------------------------------------------------


def test_scraper_has_required_methods():
    scraper = LeagueOfGraphsScraper()
    assert hasattr(scraper, "parse_matches")
    assert hasattr(scraper, "fetch_matches")
    assert hasattr(scraper, "start")
    assert hasattr(scraper, "stop")


def test_default_concurrency():
    scraper = LeagueOfGraphsScraper()
    assert scraper.sem._value == 3


def test_custom_concurrency():
    scraper = LeagueOfGraphsScraper(max_concurrent=5)
    assert scraper.sem._value == 5


def test_initial_state_is_none():
    scraper = LeagueOfGraphsScraper()
    assert scraper._pw is None
    assert scraper._browser is None
    assert scraper._ctx is None


# ---------------------------------------------------------------------------
# Regex pattern tests
# ---------------------------------------------------------------------------


class TestKDARegex:
    def test_matches_kda_spans(self):
        html = '<span class="kills">5</span> / <span class="deaths">3</span> / <span class="assists">12</span>'
        m = _KDA_RE.search(html)
        assert m is not None
        assert (m.group(1), m.group(2), m.group(3)) == ("5", "3", "12")

    def test_no_match_on_garbage(self):
        assert _KDA_RE.search("<div>nothing</div>") is None


class TestMatchIDRegex:
    def test_extracts_match_id(self):
        html = '<a href="/match/euw/7781974656#participant5">'
        m = _MATCH_ID_RE.search(html)
        assert m is not None
        assert m.group(1) == "7781974656"

    def test_different_region(self):
        html = '<a href="/match/na/1234567890#participant1">'
        m = _MATCH_ID_RE.search(html)
        assert m.group(1) == "1234567890"


class TestDurationRegex:
    def test_standard(self):
        m = _DURATION_RE.search("19min 48s")
        assert m is not None
        assert m.group(1) == "19min 48s"

    def test_compact_spacing(self):
        m = _DURATION_RE.search("32min 1s")
        assert m is not None
        assert m.group(1) == "32min 1s"


class TestEpochRegex:
    def test_extracts_epoch(self):
        html = "new Date(1773616809941)"
        m = _EPOCH_RE.search(html)
        assert m is not None
        assert m.group(1) == "1773616809941"


# ---------------------------------------------------------------------------
# _parse_rows
# ---------------------------------------------------------------------------


class TestParseRows:
    def test_finds_rows_in_full_table(self):
        scraper = LeagueOfGraphsScraper()
        rows = scraper._parse_rows(_FULL_TABLE_HTML)
        assert len(rows) == 2

    def test_empty_on_no_table(self):
        scraper = LeagueOfGraphsScraper()
        rows = scraper._parse_rows("<html><body>No table here</body></html>")
        assert rows == []

    def test_empty_on_table_without_matches(self):
        scraper = LeagueOfGraphsScraper()
        html = '<table class="recentGamesTable inverted_rows_color"><tbody></tbody></table>'
        rows = scraper._parse_rows(html)
        assert rows == []


# ---------------------------------------------------------------------------
# _extract_win
# ---------------------------------------------------------------------------


class TestExtractWin:
    def test_win_detected(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_win(_MATCH_ROW_WIN) is True

    def test_loss_detected(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_win(_MATCH_ROW_LOSS) is False

    def test_no_victory_text_is_loss(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_win("<div>some random html</div>") is False


# ---------------------------------------------------------------------------
# _extract_kda
# ---------------------------------------------------------------------------


class TestExtractKDA:
    def test_standard_kda(self):
        scraper = LeagueOfGraphsScraper()
        k, d, a = scraper._extract_kda(_MATCH_ROW_WIN)
        assert (k, d, a) == (2, 1, 20)

    def test_loss_kda(self):
        scraper = LeagueOfGraphsScraper()
        k, d, a = scraper._extract_kda(_MATCH_ROW_LOSS)
        assert (k, d, a) == (1, 5, 8)

    def test_no_kda_returns_zeros(self):
        scraper = LeagueOfGraphsScraper()
        k, d, a = scraper._extract_kda("<div>nothing here</div>")
        assert (k, d, a) == (0, 0, 0)


# ---------------------------------------------------------------------------
# _extract_champion
# ---------------------------------------------------------------------------


class TestExtractChampion:
    def test_extracts_first_alt(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_champion(_MATCH_ROW_WIN) == "Leona"

    def test_extracts_janna(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_champion(_MATCH_ROW_LOSS) == "Janna"

    def test_no_alt_returns_unknown(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_champion("<div></div>") == "Unknown"


# ---------------------------------------------------------------------------
# _extract_match_id
# ---------------------------------------------------------------------------


class TestExtractMatchId:
    def test_extracts_id(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_match_id(_MATCH_ROW_WIN) == "7781974656"

    def test_returns_none_on_no_match(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_match_id("<div>no link</div>") is None


# ---------------------------------------------------------------------------
# _extract_duration
# ---------------------------------------------------------------------------


class TestExtractDuration:
    def test_standard_duration(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_duration(_MATCH_ROW_WIN) == "19min 48s"

    def test_longer_duration(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_duration(_MATCH_ROW_LOSS) == "32min 1s"

    def test_no_duration_fallback(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_duration("<div></div>") == "0min 0s"


# ---------------------------------------------------------------------------
# _extract_game_mode
# ---------------------------------------------------------------------------


class TestExtractGameMode:
    def test_ranked(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_game_mode(_MATCH_ROW_WIN) == "Ranked Solo/Duo"

    def test_normal(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_game_mode(_MATCH_ROW_LOSS) == "Normal"

    def test_unknown_fallback(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_game_mode("<div></div>") == "Unknown"


# ---------------------------------------------------------------------------
# _extract_played_at
# ---------------------------------------------------------------------------


class TestExtractPlayedAt:
    def test_epoch_timestamp(self):
        scraper = LeagueOfGraphsScraper()
        result = scraper._extract_played_at(_MATCH_ROW_WIN)
        # Epoch 1773616809941 -> 2026-03-15 23:20 UTC
        assert "2026-03-15" in result
        assert "UTC" in result

    def test_relative_fallback(self):
        scraper = LeagueOfGraphsScraper()
        result = scraper._extract_played_at(_MATCH_ROW_LOSS)
        assert result == "5 days ago"

    def test_unknown_fallback(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_played_at("<div></div>") == "Unknown"


# ---------------------------------------------------------------------------
# parse_matches (integration of all extractors)
# ---------------------------------------------------------------------------


class TestParseMatches:
    def test_parses_win_match(self):
        scraper = LeagueOfGraphsScraper()
        summoner = _make_summoner()
        matches = scraper.parse_matches(_FULL_TABLE_HTML, summoner)

        assert len(matches) == 2
        win_match = matches[0]
        assert isinstance(win_match, MatchResult)
        assert win_match.match_id == "7781974656"
        assert win_match.champion == "Leona"
        assert win_match.win is True
        assert win_match.kills == 2
        assert win_match.deaths == 1
        assert win_match.assists == 20
        assert win_match.kda == "2/1/20"
        assert win_match.game_duration == "19min 48s"
        assert win_match.game_mode == "Ranked Solo/Duo"

    def test_parses_loss_match(self):
        scraper = LeagueOfGraphsScraper()
        summoner = _make_summoner()
        matches = scraper.parse_matches(_FULL_TABLE_HTML, summoner)

        loss_match = matches[1]
        assert loss_match.match_id == "7781999999"
        assert loss_match.champion == "Janna"
        assert loss_match.win is False
        assert loss_match.kills == 1
        assert loss_match.deaths == 5
        assert loss_match.assists == 8
        assert loss_match.kda == "1/5/8"
        assert loss_match.game_duration == "32min 1s"
        assert loss_match.game_mode == "Normal"

    def test_empty_html(self):
        scraper = LeagueOfGraphsScraper()
        summoner = _make_summoner()
        matches = scraper.parse_matches("<html></html>", summoner)
        assert matches == []

    def test_skips_rows_without_match_id(self):
        scraper = LeagueOfGraphsScraper()
        summoner = _make_summoner()
        # Table exists but rows have no match links
        html = (
            '<table class="recentGamesTable inverted_rows_color">'
            '<tbody><td class="championCellLight"><div>no link here</div></td></tbody></table>'
        )
        matches = scraper.parse_matches(html, summoner)
        assert matches == []


# ---------------------------------------------------------------------------
# kda_ratio on parsed matches
# ---------------------------------------------------------------------------


class TestKDARatioFromParsedMatches:
    def test_nonzero_deaths(self):
        scraper = LeagueOfGraphsScraper()
        summoner = _make_summoner()
        matches = scraper.parse_matches(_FULL_TABLE_HTML, summoner)
        # Win match: (2+20)/1 = 22.0
        assert matches[0].kda_ratio == 22.0
        # Loss match: (1+8)/5 = 1.8
        assert matches[1].kda_ratio == 1.8

    def test_zero_deaths_gives_inf(self):
        html = (
            '<table class="recentGamesTable inverted_rows_color"><tbody>'
            '<td class="championCellLight">'
            '<a href="/match/euw/9999999999#participant1">'
            '<img alt="Lux" src="/img/champions/Lux.png">'
            '</a></td>'
            '<td class="victoryDefeatText victory">Victory</td>'
            '<td><span class="kills">5</span> / <span class="deaths">0</span> / <span class="assists">10</span></td>'
            '<td><span>25min 0s</span></td>'
            '<td><span class="gameMode" tooltip="ARAM">ARAM</span></td>'
            '<td><span class="gameDate">1 hour ago</span></td>'
            '</tbody></table>'
        )
        scraper = LeagueOfGraphsScraper()
        summoner = _make_summoner()
        matches = scraper.parse_matches(html, summoner)
        assert len(matches) == 1
        assert matches[0].kda_ratio == float("inf")


# ---------------------------------------------------------------------------
# Async tests (mocked Playwright)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_matches_returns_empty_on_none_html():
    """When _fetch_page_html returns None, fetch_matches returns []."""
    scraper = LeagueOfGraphsScraper()
    summoner = _make_summoner()

    scraper._fetch_page_html = AsyncMock(return_value=None)
    result = await scraper.fetch_matches(summoner)
    assert result == []
    scraper._fetch_page_html.assert_called_once_with(summoner.profile_url)


@pytest.mark.asyncio
async def test_fetch_matches_parses_and_reverses():
    """fetch_matches should parse HTML and reverse the match list."""
    scraper = LeagueOfGraphsScraper()
    summoner = _make_summoner()

    scraper._fetch_page_html = AsyncMock(return_value=_FULL_TABLE_HTML)
    result = await scraper.fetch_matches(summoner)

    assert len(result) == 2
    # Reversed: loss (index 1 in parse order) comes first
    assert result[0].champion == "Janna"
    assert result[1].champion == "Leona"


@pytest.mark.asyncio
async def test_fetch_page_html_returns_none_on_non_200():
    """_fetch_page_html returns None when status != 200."""
    scraper = LeagueOfGraphsScraper()

    mock_page = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status = 403
    mock_page.goto = AsyncMock(return_value=mock_resp)
    mock_page.close = AsyncMock()

    mock_ctx = AsyncMock()
    mock_ctx.new_page = AsyncMock(return_value=mock_page)
    scraper._ctx = mock_ctx

    result = await scraper._fetch_page_html("https://example.com")
    assert result is None
    mock_page.close.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_page_html_returns_content_on_200():
    """_fetch_page_html returns page content when status is 200."""
    scraper = LeagueOfGraphsScraper()

    mock_page = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_page.goto = AsyncMock(return_value=mock_resp)
    mock_page.wait_for_selector = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html>page content</html>")
    mock_page.close = AsyncMock()

    mock_ctx = AsyncMock()
    mock_ctx.new_page = AsyncMock(return_value=mock_page)
    scraper._ctx = mock_ctx

    result = await scraper._fetch_page_html("https://example.com")
    assert result == "<html>page content</html>"
    mock_page.close.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_page_html_returns_none_on_exception():
    """_fetch_page_html returns None when navigation throws."""
    scraper = LeagueOfGraphsScraper()

    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(side_effect=Exception("timeout"))
    mock_page.close = AsyncMock()

    mock_ctx = AsyncMock()
    mock_ctx.new_page = AsyncMock(return_value=mock_page)
    scraper._ctx = mock_ctx

    result = await scraper._fetch_page_html("https://example.com")
    assert result is None
    mock_page.close.assert_called_once()


@pytest.mark.asyncio
async def test_start_and_stop():
    """start() launches browser; stop() closes everything."""
    scraper = LeagueOfGraphsScraper()

    with patch("src.scraper.async_playwright") as mock_pw_factory:
        mock_pw = AsyncMock()
        mock_browser = AsyncMock()
        mock_ctx = AsyncMock()
        mock_warmup_page = AsyncMock()

        mock_pw_factory.return_value.start = AsyncMock(return_value=mock_pw)
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_browser.new_context = AsyncMock(return_value=mock_ctx)
        mock_ctx.add_init_script = AsyncMock()
        mock_ctx.new_page = AsyncMock(return_value=mock_warmup_page)
        mock_warmup_page.goto = AsyncMock()
        mock_warmup_page.wait_for_timeout = AsyncMock()
        mock_warmup_page.locator = MagicMock()
        mock_warmup_page.locator.return_value.count = AsyncMock(return_value=0)
        mock_warmup_page.close = AsyncMock()

        await scraper.start()

        assert scraper._pw is mock_pw
        assert scraper._browser is mock_browser
        assert scraper._ctx is mock_ctx

        mock_ctx.close = AsyncMock()
        mock_browser.close = AsyncMock()
        mock_pw.stop = AsyncMock()

        await scraper.stop()

        mock_ctx.close.assert_called_once()
        mock_browser.close.assert_called_once()
        mock_pw.stop.assert_called_once()
