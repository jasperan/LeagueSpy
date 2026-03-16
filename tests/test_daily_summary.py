"""Tests for daily summary GIF generation."""

import pytest
from io import BytesIO
from unittest.mock import patch
from PIL import Image

from src.daily_summary import group_by_player, render_player_frame, build_summary_gif


def _sample_matches():
    return [
        {"player_name": "jasper", "summoner_slug": "jasper-1971", "region": "euw",
         "match_id": "100", "champion": "Jinx", "win": 1, "kills": 8, "deaths": 2,
         "assists": 5, "game_duration": "32:15", "game_mode": "Ranked", "played_at": "..."},
        {"player_name": "jasper", "summoner_slug": "jasper-1971", "region": "euw",
         "match_id": "101", "champion": "Lux", "win": 0, "kills": 2, "deaths": 7,
         "assists": 3, "game_duration": "28:10", "game_mode": "Normal", "played_at": "..."},
        {"player_name": "jasper", "summoner_slug": "jasper-1971", "region": "euw",
         "match_id": "102", "champion": "Jinx", "win": 1, "kills": 10, "deaths": 1,
         "assists": 7, "game_duration": "25:00", "game_mode": "Ranked", "played_at": "..."},
        {"player_name": "friend1", "summoner_slug": "friend1-tag", "region": "na",
         "match_id": "200", "champion": "Leona", "win": 1, "kills": 1, "deaths": 3,
         "assists": 15, "game_duration": "35:00", "game_mode": "Ranked", "played_at": "..."},
    ]


class TestGroupByPlayer:
    def test_groups_correctly(self):
        grouped = group_by_player(_sample_matches())
        assert len(grouped) == 2
        assert "jasper" in grouped
        assert "friend1" in grouped
        assert len(grouped["jasper"]) == 3
        assert len(grouped["friend1"]) == 1

    def test_empty_input(self):
        assert group_by_player([]) == {}


class TestRenderPlayerFrame:
    @patch("src.daily_summary.download_icon", return_value=None)
    def test_returns_pil_image(self, mock_dl):
        matches = _sample_matches()[:3]
        frame = render_player_frame("jasper", matches)
        assert isinstance(frame, Image.Image)
        assert frame.size[0] == 600

    @patch("src.daily_summary.download_icon", return_value=None)
    def test_frame_dimensions(self, mock_dl):
        matches = _sample_matches()[:1]
        frame = render_player_frame("jasper", matches)
        assert frame.size[0] == 600
        assert frame.size[1] > 0


class TestBuildSummaryGif:
    @patch("src.daily_summary.download_icon", return_value=None)
    def test_returns_bytes_buffer(self, mock_dl):
        grouped = group_by_player(_sample_matches())
        buf = build_summary_gif(grouped)
        assert isinstance(buf, BytesIO)
        buf.seek(0)
        img = Image.open(buf)
        assert img.format == "GIF"
        assert img.is_animated

    @patch("src.daily_summary.download_icon", return_value=None)
    def test_frame_count_matches_players(self, mock_dl):
        grouped = group_by_player(_sample_matches())
        buf = build_summary_gif(grouped)
        buf.seek(0)
        img = Image.open(buf)
        assert img.n_frames == 2

    def test_empty_grouped_returns_none(self):
        result = build_summary_gif({})
        assert result is None
