"""Tests for daily summary image generation."""

import pytest
from io import BytesIO
from unittest.mock import patch
from PIL import Image

from src.daily_summary import (
    group_by_player, render_player_frame, build_summary_image, build_summary_gif,
)


def _sample_matches():
    return [
        {"player_name": "jasper", "summoner_slug": "jasper-1971", "region": "euw",
         "match_id": "100", "champion": "Jinx", "win": 1, "kills": 8, "deaths": 2,
         "assists": 5, "game_duration": "32:15", "game_mode": "Ranked", "played_at": "...",
         "cs": 210, "gold": 14200, "kill_participation": 52, "vision_score": 30},
        {"player_name": "jasper", "summoner_slug": "jasper-1971", "region": "euw",
         "match_id": "101", "champion": "Lux", "win": 0, "kills": 2, "deaths": 7,
         "assists": 3, "game_duration": "28:10", "game_mode": "Normal", "played_at": "...",
         "cs": 180, "gold": 11500, "kill_participation": 28, "vision_score": 18},
        {"player_name": "jasper", "summoner_slug": "jasper-1971", "region": "euw",
         "match_id": "102", "champion": "Jinx", "win": 1, "kills": 10, "deaths": 1,
         "assists": 7, "game_duration": "25:00", "game_mode": "Ranked", "played_at": "...",
         "cs": 245, "gold": 16800, "kill_participation": 68, "vision_score": 25},
        {"player_name": "friend1", "summoner_slug": "friend1-tag", "region": "na",
         "match_id": "200", "champion": "Leona", "win": 1, "kills": 1, "deaths": 3,
         "assists": 15, "game_duration": "35:00", "game_mode": "Ranked", "played_at": "...",
         "cs": 42, "gold": 9800, "kill_participation": 80, "vision_score": 65},
    ]


def _sample_matches_no_enhanced():
    """Matches without enhanced stats (backward compat)."""
    return [
        {"player_name": "jasper", "summoner_slug": "jasper-1971", "region": "euw",
         "match_id": "100", "champion": "Jinx", "win": 1, "kills": 8, "deaths": 2,
         "assists": 5, "game_duration": "32:15", "game_mode": "Ranked", "played_at": "..."},
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
        assert frame.size[0] == 800

    @patch("src.daily_summary.download_icon", return_value=None)
    def test_frame_height_scales_with_matches(self, mock_dl):
        one_match = _sample_matches()[:1]
        three_matches = _sample_matches()[:3]
        frame1 = render_player_frame("jasper", one_match)
        frame3 = render_player_frame("jasper", three_matches)
        assert frame3.size[1] > frame1.size[1]

    @patch("src.daily_summary.download_icon", return_value=None)
    def test_handles_missing_enhanced_stats(self, mock_dl):
        matches = _sample_matches_no_enhanced()
        frame = render_player_frame("jasper", matches)
        assert isinstance(frame, Image.Image)
        assert frame.size[0] == 800


class TestBuildSummaryImage:
    @patch("src.daily_summary.download_icon", return_value=None)
    def test_two_players_returns_png(self, mock_dl):
        grouped = group_by_player(_sample_matches())
        result = build_summary_image(grouped)
        assert result is not None
        buf, filename = result
        assert isinstance(buf, BytesIO)
        assert filename.endswith(".png")
        buf.seek(0)
        img = Image.open(buf)
        assert img.format == "PNG"

    @patch("src.daily_summary.download_icon", return_value=None)
    def test_png_is_composite_of_all_players(self, mock_dl):
        grouped = group_by_player(_sample_matches())
        result = build_summary_image(grouped)
        buf, _ = result
        buf.seek(0)
        img = Image.open(buf)
        # Composite height should be > single frame height
        single = render_player_frame("jasper", grouped["jasper"])
        assert img.size[1] > single.size[1]

    @patch("src.daily_summary.download_icon", return_value=None)
    def test_five_plus_players_returns_gif(self, mock_dl):
        # Create 5 players
        matches = []
        for i in range(5):
            matches.append({
                "player_name": f"player{i}", "summoner_slug": f"p{i}-tag",
                "region": "euw", "match_id": str(300 + i), "champion": "Jinx",
                "win": 1, "kills": 5, "deaths": 2, "assists": 3,
                "game_duration": "25:00", "game_mode": "Ranked", "played_at": "...",
                "cs": 200, "gold": 13000, "kill_participation": 50, "vision_score": 30,
            })
        grouped = group_by_player(matches)
        result = build_summary_image(grouped)
        assert result is not None
        buf, filename = result
        assert filename.endswith(".gif")
        buf.seek(0)
        img = Image.open(buf)
        assert img.format == "GIF"
        assert img.is_animated
        assert img.n_frames == 5

    def test_empty_grouped_returns_none(self):
        result = build_summary_image({})
        assert result is None


class TestBuildSummaryGifBackwardCompat:
    @patch("src.daily_summary.download_icon", return_value=None)
    def test_returns_bytes_buffer(self, mock_dl):
        grouped = group_by_player(_sample_matches())
        buf = build_summary_gif(grouped)
        assert isinstance(buf, BytesIO)

    def test_empty_grouped_returns_none(self):
        result = build_summary_gif({})
        assert result is None
