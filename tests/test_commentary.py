import pytest
from unittest.mock import MagicMock, patch

from src.models import MatchResult, SummonerConfig
from src.commentary import (
    _request_ollama,
    build_commentary,
    build_prompt,
    deaths_per_minute,
    parse_duration_minutes,
    should_praise,
    should_roast,
)


def _make_summoner() -> SummonerConfig:
    return SummonerConfig(player_name="jasper", slug="jasper-1971", region="euw")


def _make_match(
    *,
    win: bool,
    kills: int,
    deaths: int,
    assists: int,
    game_duration: str = "24min 10s",
    champion: str = "Lux",
    game_mode: str = "Ranked Solo",
) -> MatchResult:
    return MatchResult(
        match_id="EUW1-123",
        champion=champion,
        win=win,
        kills=kills,
        deaths=deaths,
        assists=assists,
        game_duration=game_duration,
        game_mode=game_mode,
        played_at="2026-03-16 14:32 UTC",
    )


def test_should_roast_bad_loss_by_deaths():
    match = _make_match(win=False, kills=1, deaths=7, assists=2)

    assert should_roast(match) is True
    assert should_praise(match) is False


def test_should_roast_bad_loss_by_deaths_per_minute():
    match = _make_match(win=False, kills=3, deaths=5, assists=1, game_duration="20:00")

    assert deaths_per_minute(match) == pytest.approx(0.25)
    assert should_roast(match) is True


def test_should_praise_huge_win():
    match = _make_match(win=True, kills=10, deaths=2, assists=5, champion="Jinx")

    assert should_praise(match) is True
    assert should_roast(match) is False


def test_no_commentary_for_middle_ground_match():
    match = _make_match(win=False, kills=4, deaths=4, assists=6, game_duration="31:00")

    assert should_roast(match) is False
    assert should_praise(match) is False


def test_parse_duration_minutes_supports_minute_format():
    assert parse_duration_minutes("24min 30s") == pytest.approx(24.5)


def test_parse_duration_minutes_supports_clock_format():
    assert parse_duration_minutes("24:30") == pytest.approx(24.5)


def test_parse_duration_minutes_returns_zero_for_invalid_value():
    assert parse_duration_minutes("Unknown") == 0.0


def test_build_prompt_makes_roasts_more_savage_than_praise():
    summoner = _make_summoner()
    roast_match = _make_match(win=False, kills=1, deaths=8, assists=2)
    praise_match = _make_match(win=True, kills=12, deaths=2, assists=9, champion="Jinx")

    roast_prompt = build_prompt(summoner, roast_match, "roast")
    praise_prompt = build_prompt(summoner, praise_match, "praise")

    assert "humillación deportiva" in roast_prompt
    assert "No suavices el golpe" in roast_prompt
    assert "catástrofe de museo" in roast_prompt
    assert "mamón" in roast_prompt
    assert "pedazo de paquete" in roast_prompt
    assert "humillación deportiva" not in praise_prompt
    assert "buena esa, tío" in praise_prompt


def test_request_ollama_disables_thinking_mode():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "response": "ok",
    }

    with patch("src.commentary.httpx.post", return_value=mock_response) as mock_post:
        _request_ollama("hola")

    assert mock_post.call_args.kwargs["json"]["think"] is False


def test_request_ollama_strips_trailing_thinking_dump():
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "response": (
            "Gloglito, 0 muertes por minuto con Ahri es un recital de inting.\n\n"
            "Thinking Process:\n\n"
            "Analyze the Request:\n"
            "Role: Most acidic LoL commentator."
        ),
    }

    with patch("src.commentary.httpx.post", return_value=mock_response):
        result = _request_ollama("hola")

    assert result == "Gloglito, 0 muertes por minuto con Ahri es un recital de inting."


@pytest.mark.asyncio
async def test_build_commentary_returns_spanish_line_and_results_on_success():
    summoner = _make_summoner()
    match = _make_match(win=False, kills=1, deaths=7, assists=2)

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "response": "Vaya vaya, hoy Lux ha decidido farmear derrotas con entusiasmo.",
    }

    with patch("src.commentary.httpx.post", return_value=mock_response):
        commentary = await build_commentary(summoner, match)

    assert commentary is not None
    assert commentary.startswith("Vaya vaya")
    assert "Resultado de jasper" in commentary
    assert "Derrota" in commentary
    assert "KDA: 1/7/2" in commentary


@pytest.mark.asyncio
async def test_build_commentary_returns_none_when_ollama_fails():
    summoner = _make_summoner()
    match = _make_match(win=False, kills=1, deaths=7, assists=2)

    with patch("src.commentary.httpx.post", side_effect=Exception("boom")):
        commentary = await build_commentary(summoner, match)

    assert commentary is None


@pytest.mark.asyncio
async def test_build_commentary_skips_middle_ground_without_calling_ollama():
    summoner = _make_summoner()
    match = _make_match(win=False, kills=4, deaths=4, assists=6)

    with patch("src.commentary.httpx.post") as mock_post:
        commentary = await build_commentary(summoner, match)

    assert commentary is None
    mock_post.assert_not_called()
