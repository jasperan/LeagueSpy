"""Tests for the visual match scoreboard renderer."""

import pytest
from unittest.mock import patch
from PIL import Image
from io import BytesIO

from src.match_image import render_scoreboard, _find_tracked_player
from src.models import MatchDetails, MatchParticipant


def _make_player(name="Player1", rank="Gold IV", champion="Jinx",
                 kills=5, deaths=2, assists=3, cs=200, gold=12000,
                 kp=45, vs=30):
    return MatchParticipant(
        summoner_name=name, rank=rank, champion=champion,
        kills=kills, deaths=deaths, assists=assists,
        cs=cs, gold=gold, kill_participation=kp, vision_score=vs,
    )


def _make_details(tracked_name="jasper#1971"):
    team1 = [
        _make_player(tracked_name, "Platinum II", "Jinx", 10, 2, 5, 245, 16800, 68, 25),
        _make_player("Ally1", "Gold I", "Leona", 1, 3, 15, 42, 9800, 80, 65),
        _make_player("Ally2", "Silver III", "Lux", 3, 4, 8, 180, 11500, 55, 40),
        _make_player("Ally3", "Gold IV", "Lee Sin", 7, 5, 6, 160, 13200, 60, 35),
        _make_player("Ally4", "Platinum IV", "Ahri", 6, 3, 9, 210, 14500, 70, 28),
    ]
    team2 = [
        _make_player("Enemy1", "Gold II", "Zed", 4, 6, 3, 190, 11000, 40, 18),
        _make_player("Enemy2", "Silver I", "Thresh", 2, 5, 10, 35, 8500, 65, 72),
        _make_player("Enemy3", "Gold III", "Yasuo", 5, 5, 2, 220, 13000, 38, 22),
        _make_player("Enemy4", "Silver II", "Ashe", 3, 6, 4, 195, 10800, 42, 20),
        _make_player("Enemy5", "Gold IV", "Nautilus", 1, 5, 8, 40, 8200, 50, 55),
    ]
    return MatchDetails(
        team1_players=team1, team2_players=team2,
        team1_result="WIN", team2_result="LOSS",
        team1_bans=["Vayne", "Yone", "Katarina"],
        team2_bans=["Caitlyn", "Samira", "Draven"],
    )


class TestFindTrackedPlayer:
    def test_finds_on_team1(self):
        details = _make_details("jasper#1971")
        result = _find_tracked_player(details, "jasper-1971")
        assert result == (0, 0)

    def test_finds_on_team2(self):
        details = _make_details()
        # Put tracked player on team 2
        details.team2_players[2] = _make_player("myplayer#tag")
        result = _find_tracked_player(details, "myplayer-tag")
        assert result == (1, 2)

    def test_returns_none_when_not_found(self):
        details = _make_details()
        result = _find_tracked_player(details, "nobody-9999")
        assert result is None


class TestRenderScoreboard:
    @patch("src.match_image.download_icon", return_value=None)
    def test_returns_png_bytes(self, mock_dl):
        details = _make_details()
        result = render_scoreboard(details, "jasper-1971")
        assert result is not None
        assert isinstance(result, bytes)
        img = Image.open(BytesIO(result))
        assert img.format == "PNG"

    @patch("src.match_image.download_icon", return_value=None)
    def test_image_dimensions(self, mock_dl):
        details = _make_details()
        result = render_scoreboard(details, "jasper-1971")
        img = Image.open(BytesIO(result))
        assert img.size[0] == 800
        # 5 players per team, headers, margins
        assert img.size[1] > 200

    @patch("src.match_image.download_icon", return_value=None)
    def test_empty_team_returns_none(self, mock_dl):
        details = MatchDetails(
            team1_players=[], team2_players=[],
            team1_result="WIN", team2_result="LOSS",
            team1_bans=[], team2_bans=[],
        )
        assert render_scoreboard(details, "jasper-1971") is None

    @patch("src.match_image.download_icon", return_value=None)
    def test_untracked_player_still_renders(self, mock_dl):
        details = _make_details()
        result = render_scoreboard(details, "nobody-9999")
        assert result is not None
        img = Image.open(BytesIO(result))
        assert img.format == "PNG"

    @patch("src.match_image.download_icon", return_value=None)
    def test_fewer_than_five_players(self, mock_dl):
        details = _make_details()
        details.team1_players = details.team1_players[:3]
        details.team2_players = details.team2_players[:3]
        result = render_scoreboard(details, "jasper-1971")
        assert result is not None
        img = Image.open(BytesIO(result))
        assert img.format == "PNG"
