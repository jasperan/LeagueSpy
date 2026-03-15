import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.scraper import OpGGScraper
from src.models import SummonerConfig, MatchResult


def _make_summoner():
    return SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_scraper_has_required_methods():
    scraper = OpGGScraper()
    assert hasattr(scraper, "parse_matches")
    assert hasattr(scraper, "fetch_matches")
    assert hasattr(scraper, "fetch_all")


def test_default_delay():
    scraper = OpGGScraper()
    assert scraper.delay == 2.0


def test_custom_delay():
    scraper = OpGGScraper(delay_between_requests=5.0)
    assert scraper.delay == 5.0


class TestDetermineWin:
    def test_win_from_main_colors(self):
        scraper = OpGGScraper()
        html = '[--game-item-color-100:theme(colors.main.100)]'
        assert scraper._determine_win(html) is True

    def test_loss_from_red_colors(self):
        scraper = OpGGScraper()
        html = '[--game-item-color-100:theme(colors.red.100)]'
        assert scraper._determine_win(html) is False

    def test_loss_from_defeat_text(self):
        scraper = OpGGScraper()
        html = '<strong>Defeat</strong>'
        assert scraper._determine_win(html) is False

    def test_win_from_victory_text(self):
        scraper = OpGGScraper()
        html = '<strong>Victory</strong>'
        assert scraper._determine_win(html) is True


class TestExtractKDA:
    def test_from_tooltip(self):
        scraper = OpGGScraper()
        html = 'data-tooltip-content="(K 2 + A 20) / D 2"'
        k, d, a = scraper._extract_kda(html)
        assert (k, d, a) == (2, 2, 20)

    def test_from_inline(self):
        scraper = OpGGScraper()
        html = (
            '<strong class="text-gray-900">5</strong>/'
            '<strong class="text-red-600">3</strong>/'
            '<strong class="text-gray-900">12</strong>'
        )
        k, d, a = scraper._extract_kda(html)
        assert (k, d, a) == (5, 3, 12)

    def test_no_kda_returns_zeros(self):
        scraper = OpGGScraper()
        k, d, a = scraper._extract_kda("<div>nothing here</div>")
        assert (k, d, a) == (0, 0, 0)


class TestExtractChampion:
    def test_extracts_first_alt(self):
        scraper = OpGGScraper()
        html = '<img alt="Leona" src="..."><img alt="Flash" src="...">'
        assert scraper._extract_champion(html) == "Leona"

    def test_no_alt_returns_unknown(self):
        scraper = OpGGScraper()
        assert scraper._extract_champion("<div></div>") == "Unknown"


class TestExtractDuration:
    def test_standard_duration(self):
        scraper = OpGGScraper()
        html = "<span>37m 48s</span>"
        assert scraper._extract_duration(html) == "37m 48s"

    def test_short_duration(self):
        scraper = OpGGScraper()
        html = "<span>4m 19s</span>"
        assert scraper._extract_duration(html) == "4m 19s"

    def test_no_duration(self):
        scraper = OpGGScraper()
        assert scraper._extract_duration("<div></div>") == "0m 0s"


class TestExtractGameMode:
    def test_normal(self):
        scraper = OpGGScraper()
        html = 'md:font-bold md:text-[var(--game-item-color-600)]">Normal</span>'
        assert scraper._extract_game_mode(html) == "Normal"

    def test_unknown_fallback(self):
        scraper = OpGGScraper()
        assert scraper._extract_game_mode("<div></div>") == "Unknown"


class TestExtractPlayedAt:
    def test_tooltip_date(self):
        scraper = OpGGScraper()
        html = 'data-tooltip-content="3/13/2026, 8:20 PM" class="">2 days ago</span>'
        assert scraper._extract_played_at(html) == "3/13/2026, 8:20 PM"

    def test_relative_fallback(self):
        scraper = OpGGScraper()
        html = ">5 days ago<"
        assert scraper._extract_played_at(html) == "5 days ago"


class TestGenerateMatchId:
    def test_stable_id(self):
        scraper = OpGGScraper()
        s = _make_summoner()
        id1 = scraper._generate_match_id(s, "Leona", "3/13/2026, 8:20 PM")
        id2 = scraper._generate_match_id(s, "Leona", "3/13/2026, 8:20 PM")
        assert id1 == id2
        assert len(id1) == 16

    def test_different_inputs_different_ids(self):
        scraper = OpGGScraper()
        s = _make_summoner()
        id1 = scraper._generate_match_id(s, "Leona", "3/13/2026, 8:20 PM")
        id2 = scraper._generate_match_id(s, "Braum", "3/13/2026, 8:20 PM")
        assert id1 != id2


# ---------------------------------------------------------------------------
# Async integration tests (mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_matches_calls_stealthy_fetcher():
    scraper = OpGGScraper()
    summoner = _make_summoner()

    with patch("src.scraper.StealthyFetcher") as mock_fetcher:
        mock_page = MagicMock()
        mock_page.status = 200
        mock_page.css = MagicMock(return_value=[])
        mock_fetcher.fetch = MagicMock(return_value=mock_page)

        result = await scraper.fetch_matches(summoner)

        mock_fetcher.fetch.assert_called_once()
        assert isinstance(result, list)
        assert len(result) == 0


@pytest.mark.asyncio
async def test_fetch_matches_returns_empty_on_non_200():
    scraper = OpGGScraper()
    summoner = _make_summoner()

    with patch("src.scraper.StealthyFetcher") as mock_fetcher:
        mock_page = MagicMock()
        mock_page.status = 403
        mock_fetcher.fetch = MagicMock(return_value=mock_page)

        result = await scraper.fetch_matches(summoner)
        assert result == []


@pytest.mark.asyncio
async def test_fetch_all_processes_multiple_summoners():
    scraper = OpGGScraper(delay_between_requests=0)
    s1 = SummonerConfig("p1", "p1-123", "euw")
    s2 = SummonerConfig("p2", "p2-456", "na")

    with patch("src.scraper.StealthyFetcher") as mock_fetcher:
        mock_page = MagicMock()
        mock_page.status = 200
        mock_page.css = MagicMock(return_value=[])
        mock_fetcher.fetch = MagicMock(return_value=mock_page)

        results = await scraper.fetch_all([s1, s2])

        assert "p1-123" in results
        assert "p2-456" in results
        assert mock_fetcher.fetch.call_count == 2


@pytest.mark.asyncio
async def test_parse_matches_with_mock_html():
    """Test parse_matches with a realistic mock game element."""
    scraper = OpGGScraper()
    summoner = _make_summoner()

    mock_game_html = (
        '<div class="box-border flex w-full border-l-[6px] border-[var(--game-item-color-500)] '
        '[--game-item-color-100:theme(colors.main.100)] [--game-item-color-600:theme(colors.main.600)]">'
        '<span class="md:font-bold md:text-[var(--game-item-color-600)]">Normal</span>'
        '<span data-tooltip-content="3/13/2026, 8:20 PM" class="">2 days ago</span>'
        '<img alt="Leona" src="champion.png">'
        '<div data-tooltip-content="(K 2 + A 20) / D 2">11.00:1 KDA</div>'
        '<span>37m 48s</span>'
        '<strong>Victory</strong>'
        '</div>'
    )

    mock_element = MagicMock()
    mock_element.html = mock_game_html

    mock_page = MagicMock()
    mock_page.css = MagicMock(return_value=[mock_element])

    matches = scraper.parse_matches(mock_page, summoner)

    assert len(matches) == 1
    m = matches[0]
    assert isinstance(m, MatchResult)
    assert m.champion == "Leona"
    assert m.win is True
    assert m.kills == 2
    assert m.deaths == 2
    assert m.assists == 20
    assert m.kda == "2/2/20"
    assert m.game_duration == "37m 48s"
    assert m.game_mode == "Normal"
    assert m.played_at == "3/13/2026, 8:20 PM"
    assert len(m.match_id) == 16


@pytest.mark.asyncio
async def test_parse_matches_loss():
    """Test that a loss game is correctly parsed."""
    scraper = OpGGScraper()
    summoner = _make_summoner()

    mock_game_html = (
        '<div class="box-border flex w-full border-l-[6px] '
        '[--game-item-color-100:theme(colors.red.100)] [--game-item-color-600:theme(colors.red.600)]">'
        '<span class="md:font-bold md:text-[var(--game-item-color-600)]">Normal</span>'
        '<span data-tooltip-content="3/11/2026, 3:45 AM">5 days ago</span>'
        '<img alt="Janna" src="champion.png">'
        '<div data-tooltip-content="(K 1 + A 8) / D 5">1.80:1 KDA</div>'
        '<span>30m 04s</span>'
        '<strong>Defeat</strong>'
        '</div>'
    )

    mock_element = MagicMock()
    mock_element.html = mock_game_html

    mock_page = MagicMock()
    mock_page.css = MagicMock(return_value=[mock_element])

    matches = scraper.parse_matches(mock_page, summoner)

    assert len(matches) == 1
    m = matches[0]
    assert m.champion == "Janna"
    assert m.win is False
    assert m.kills == 1
    assert m.deaths == 5
    assert m.assists == 8
    assert m.game_duration == "30m 04s"


@pytest.mark.asyncio
async def test_parse_matches_handles_exception_gracefully():
    """If a game element raises during parsing, it's skipped."""
    scraper = OpGGScraper()
    summoner = _make_summoner()

    bad_element = MagicMock()
    bad_element.html = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
    type(bad_element).html = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))

    mock_page = MagicMock()
    mock_page.css = MagicMock(return_value=[bad_element])

    matches = scraper.parse_matches(mock_page, summoner)
    assert matches == []
