import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.scraper import LeagueOfGraphsScraper, _KDA_RE, _MATCH_ID_RE, _MATCH_URL_RE, _DURATION_RE, _EPOCH_RE
from src.models import SummonerConfig, MatchResult, MatchParticipant, MatchDetails


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
# _extract_match_url
# ---------------------------------------------------------------------------


class TestExtractMatchUrl:
    def test_extracts_full_match_url(self):
        scraper = LeagueOfGraphsScraper()
        result = scraper._extract_match_url(_MATCH_ROW_WIN)
        assert result == "/match/euw/7781974656#participant5"

    def test_returns_none_on_no_link(self):
        scraper = LeagueOfGraphsScraper()
        assert scraper._extract_match_url("<div>no link here</div>") is None


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
        assert win_match.match_url == "/match/euw/7781974656#participant5"

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


# ---------------------------------------------------------------------------
# In-game detection
# ---------------------------------------------------------------------------


class TestCheckInGame:
    def test_detects_in_game(self):
        scraper = LeagueOfGraphsScraper()
        html = '<div class="current-game"><span>In Game</span><img alt="Yasuo"></div>'
        result = scraper.parse_in_game_status(html)
        assert result is not None
        assert result["in_game"] is True

    def test_detects_not_in_game(self):
        scraper = LeagueOfGraphsScraper()
        result = scraper.parse_in_game_status(_FULL_TABLE_HTML)
        assert result is not None
        assert result["in_game"] is False

    def test_extracts_champion_from_game_banner(self):
        scraper = LeagueOfGraphsScraper()
        html = '<div class="current-game"><span>In Game</span><img alt="Yasuo"></div>'
        result = scraper.parse_in_game_status(html)
        assert result["champion"] == "Yasuo"


# ---------------------------------------------------------------------------
# Match detail page parsing
# ---------------------------------------------------------------------------

# Minimal fixture with 2 playerRows (4 players total) + bans
_MATCH_DETAIL_HTML = '''
<table class="data_table matchTable">
<tr>
  <th class="text-left no-padding-right">
    <span class="defeat">Defeat</span>
    <span class="kda kda-left hide-for-small-down-custom">39 / 49 / 52</span>
  </th>
  <th class="text-center no-padding-lateral"></th>
  <th class="text-right no-padding-left">
    <span class="kda kda-right hide-for-small-down-custom">48 / 39 / 60</span>
    <span class="victory">Victory</span>
  </th>
</tr>
<tr class="playerRow">
  <td class="text-left summoner_column">
    <div class="img-align-block"><div class="relative">
      <a href="/summoner/euw/stmlyc-0922">
        <div><img alt="Lee Sin" title="Lee Sin" height="48" width="48"/></div>
      </a>
    </div>
    <div class="txt"><a href="/summoner/euw/stmlyc-0922">
      <div class="name"> stmlyc#0922 </div>
      <div class="subname"><i> Diamond IV </i></div>
    </a></div></div>
  </td>
  <td class="kdaColumn hide-for-small-down requireTooltip noCursor"
      tooltip="<itemname>Farming</itemname> <div> Minions: 352 </div>">
    <div class="kda ">
      <span class="kills">3</span> / <span class="deaths">8</span> / <span class="assists">7</span>
    </div>
    <div class="cs"> 352 CS - 16.3k gold </div>
    <div class="cs"> 26% Kills P. - Vision: 55 </div>
  </td>
  <td class="itemsColumn itemsColumn-100"></td>
  <td class="itemsColumn itemsColumn-200"></td>
  <td class="kdaColumn hide-for-small-down requireTooltip noCursor"
      tooltip="<itemname>Farming</itemname> <div> Minions: 268 </div>">
    <div class="kda ">
      <span class="kills">16</span> / <span class="deaths">4</span> / <span class="assists">7</span>
    </div>
    <div class="cs"> 268 CS - 20.6k gold </div>
    <div class="cs"> 48% Kills P. - Vision: 26 </div>
  </td>
  <td class="text-right summoner_column">
    <div class="img-align-block"><div class="relative">
      <a href="/summoner/euw/Pangea-EUWV1">
        <div><img alt="Jax" title="Jax" height="48" width="48"/></div>
      </a>
    </div>
    <div class="txt"><a href="/summoner/euw/Pangea-EUWV1">
      <div class="name"> Pangea#EUWV1 </div>
      <div class="subname"><i> Diamond I </i></div>
    </a></div></div>
  </td>
</tr>
<tr class="playerRow">
  <td class="text-left summoner_column">
    <div class="img-align-block"><div class="relative">
      <a href="/summoner/euw/nichtnoah-999">
        <div><img alt="Kha'Zix" title="Kha'Zix" height="48" width="48"/></div>
      </a>
    </div>
    <div class="txt"><a href="/summoner/euw/nichtnoah-999">
      <div class="name"> nichtnoah#999 </div>
      <div class="subname"><i> Platinum IV </i></div>
    </a></div></div>
  </td>
  <td class="kdaColumn hide-for-small-down requireTooltip noCursor"
      tooltip="stats">
    <div class="kda ">
      <span class="kills">10</span> / <span class="deaths">10</span> / <span class="assists">9</span>
    </div>
    <div class="cs"> 240 CS - 17.6k gold </div>
    <div class="cs"> 49% Kills P. - Vision: 46 </div>
  </td>
  <td class="itemsColumn itemsColumn-100"></td>
  <td class="itemsColumn itemsColumn-200"></td>
  <td class="kdaColumn hide-for-small-down requireTooltip noCursor"
      tooltip="stats">
    <div class="kda ">
      <span class="kills">15</span> / <span class="deaths">7</span> / <span class="assists">6</span>
    </div>
    <div class="cs"> 266 CS - 18.9k gold </div>
    <div class="cs"> 44% Kills P. - Vision: 45 </div>
  </td>
  <td class="text-right summoner_column">
    <div class="img-align-block"><div class="relative">
      <a href="/summoner/euw/FentaniloLover-1NCEL">
        <div><img alt="Gwen" title="Gwen" height="48" width="48"/></div>
      </a>
    </div>
    <div class="txt"><a href="/summoner/euw/FentaniloLover-1NCEL">
      <div class="name"> FentaniloLover#1NCEL </div>
      <div class="subname"><i> Emerald II </i></div>
    </a></div></div>
  </td>
</tr>
<tr>
  <td class="bansColumn text-center" colspan="2">
    <span class="bansText">Bans:</span>
    <div class="bannedChampion requireTooltip" tooltip="Nautilus"></div>
    <div class="bannedChampion requireTooltip" tooltip="Olaf"></div>
    <div class="bannedChampion requireTooltip" tooltip="Mel"></div>
    <div class="bannedChampion requireTooltip" tooltip="Rammus"></div>
  </td>
  <td class="text-center"></td>
  <td class="bansColumn text-center" colspan="2">
    <span class="bansText">Bans:</span>
    <div class="bannedChampion requireTooltip" tooltip="Malphite"></div>
    <div class="bannedChampion requireTooltip" tooltip="Rengar"></div>
    <div class="bannedChampion requireTooltip" tooltip="Karma"></div>
    <div class="bannedChampion requireTooltip" tooltip="Ekko"></div>
    <div class="bannedChampion requireTooltip" tooltip="Ambessa"></div>
  </td>
</tr>
</table>
'''


class TestParseMatchDetails:
    def test_extracts_both_teams(self):
        scraper = LeagueOfGraphsScraper()
        details = scraper.parse_match_details(_MATCH_DETAIL_HTML)
        assert details is not None
        assert len(details.team1_players) == 2
        assert len(details.team2_players) == 2

    def test_team_results(self):
        scraper = LeagueOfGraphsScraper()
        details = scraper.parse_match_details(_MATCH_DETAIL_HTML)
        assert details.team1_result == "Defeat"
        assert details.team2_result == "Victory"

    def test_left_player_stats(self):
        scraper = LeagueOfGraphsScraper()
        details = scraper.parse_match_details(_MATCH_DETAIL_HTML)
        p = details.team1_players[0]
        assert isinstance(p, MatchParticipant)
        assert p.summoner_name == "stmlyc#0922"
        assert p.rank == "Diamond IV"
        assert p.champion == "Lee Sin"
        assert p.kills == 3
        assert p.deaths == 8
        assert p.assists == 7
        assert p.cs == 352
        assert p.gold == 16300
        assert p.kill_participation == 26
        assert p.vision_score == 55

    def test_right_player_stats(self):
        scraper = LeagueOfGraphsScraper()
        details = scraper.parse_match_details(_MATCH_DETAIL_HTML)
        p = details.team2_players[0]
        assert isinstance(p, MatchParticipant)
        assert p.summoner_name == "Pangea#EUWV1"
        assert p.rank == "Diamond I"
        assert p.champion == "Jax"
        assert p.kills == 16
        assert p.deaths == 4
        assert p.assists == 7
        assert p.cs == 268
        assert p.gold == 20600
        assert p.kill_participation == 48
        assert p.vision_score == 26

    def test_second_row_players(self):
        scraper = LeagueOfGraphsScraper()
        details = scraper.parse_match_details(_MATCH_DETAIL_HTML)
        # Second left player
        p1 = details.team1_players[1]
        assert p1.summoner_name == "nichtnoah#999"
        assert p1.champion == "Kha'Zix"
        assert p1.rank == "Platinum IV"
        assert p1.kills == 10
        assert p1.deaths == 10
        assert p1.assists == 9
        assert p1.cs == 240
        assert p1.gold == 17600
        assert p1.kill_participation == 49
        assert p1.vision_score == 46
        # Second right player
        p2 = details.team2_players[1]
        assert p2.summoner_name == "FentaniloLover#1NCEL"
        assert p2.champion == "Gwen"
        assert p2.rank == "Emerald II"
        assert p2.kills == 15
        assert p2.deaths == 7
        assert p2.assists == 6
        assert p2.cs == 266
        assert p2.gold == 18900
        assert p2.kill_participation == 44
        assert p2.vision_score == 45

    def test_bans_extracted(self):
        scraper = LeagueOfGraphsScraper()
        details = scraper.parse_match_details(_MATCH_DETAIL_HTML)
        assert details.team1_bans == ["Nautilus", "Olaf", "Mel", "Rammus"]
        assert details.team2_bans == ["Malphite", "Rengar", "Karma", "Ekko", "Ambessa"]

    def test_returns_none_on_no_table(self):
        scraper = LeagueOfGraphsScraper()
        result = scraper.parse_match_details("<html><body>No match table</body></html>")
        assert result is None


@pytest.mark.asyncio
async def test_fetch_match_details_returns_details():
    scraper = LeagueOfGraphsScraper()
    scraper._fetch_page_html = AsyncMock(return_value=_MATCH_DETAIL_HTML)
    details = await scraper.fetch_match_details("/match/euw/7782016191#participant10", "euw")
    assert details is not None
    assert len(details.team1_players) > 0


@pytest.mark.asyncio
async def test_fetch_match_details_returns_none_on_failure():
    scraper = LeagueOfGraphsScraper()
    scraper._fetch_page_html = AsyncMock(return_value=None)
    details = await scraper.fetch_match_details("/match/euw/123#participant1", "euw")
    assert details is None


class TestParseMatchDetailsRealPage:
    """Tests against the real match page HTML saved at /tmp/match_page.html."""

    @pytest.fixture
    def real_html(self):
        with open("/tmp/match_page.html", "r", encoding="utf-8") as f:
            return f.read()

    def test_parses_all_10_players(self, real_html):
        scraper = LeagueOfGraphsScraper()
        details = scraper.parse_match_details(real_html)
        assert details is not None
        assert len(details.team1_players) == 5
        assert len(details.team2_players) == 5

    def test_team_results_real(self, real_html):
        scraper = LeagueOfGraphsScraper()
        details = scraper.parse_match_details(real_html)
        assert details.team1_result == "Defeat"
        assert details.team2_result == "Victory"

    def test_first_left_player_real(self, real_html):
        scraper = LeagueOfGraphsScraper()
        details = scraper.parse_match_details(real_html)
        p = details.team1_players[0]
        assert p.summoner_name == "stmlyc#0922"
        assert p.rank == "Diamond IV"
        assert p.champion == "Lee Sin"
        assert p.kills == 3
        assert p.deaths == 8
        assert p.assists == 7
        assert p.cs == 352
        assert p.gold == 16300
        assert p.kill_participation == 26
        assert p.vision_score == 55

    def test_first_right_player_real(self, real_html):
        scraper = LeagueOfGraphsScraper()
        details = scraper.parse_match_details(real_html)
        p = details.team2_players[0]
        assert p.summoner_name == "Pangea#EUWV1"
        assert p.rank == "Diamond I"
        assert p.champion == "Jax"
        assert p.kills == 16
        assert p.deaths == 4
        assert p.assists == 7
        assert p.cs == 268
        assert p.gold == 20600
        assert p.kill_participation == 48
        assert p.vision_score == 26

    def test_bans_real(self, real_html):
        scraper = LeagueOfGraphsScraper()
        details = scraper.parse_match_details(real_html)
        assert details.team1_bans == ["Nautilus", "Olaf", "Mel", "Rammus"]
        assert details.team2_bans == ["Malphite", "Rengar", "Karma", "Ekko", "Ambessa"]

    def test_all_players_have_valid_stats(self, real_html):
        scraper = LeagueOfGraphsScraper()
        details = scraper.parse_match_details(real_html)
        for team in [details.team1_players, details.team2_players]:
            for p in team:
                assert p.summoner_name, "Name should not be empty"
                assert p.champion, "Champion should not be empty"
                assert p.kills >= 0
                assert p.deaths >= 0
                assert p.assists >= 0
                assert p.cs >= 0
                assert p.gold > 0
                assert 0 <= p.kill_participation <= 100
                assert p.vision_score >= 0
