from unittest.mock import patch
from PIL import Image
from src.rankings import render_power_rankings, compute_power_score


class TestComputePowerScore:
    def test_basic_score(self):
        score = compute_power_score(win_rate=0.6, avg_kda_ratio=3.0, games=10, max_games=20)
        assert 0 < score < 100

    def test_higher_wr_higher_score(self):
        a = compute_power_score(win_rate=0.7, avg_kda_ratio=3.0, games=10, max_games=10)
        b = compute_power_score(win_rate=0.4, avg_kda_ratio=3.0, games=10, max_games=10)
        assert a > b

    def test_zero_games_returns_zero(self):
        assert compute_power_score(win_rate=0, avg_kda_ratio=0, games=0, max_games=10) == 0


class TestRenderPowerRankings:
    @patch("src.rankings.download_icon", return_value=None)
    def test_returns_pil_image(self, mock_dl):
        players = [
            {"player_name": "jasper", "games": 12, "wins": 8,
             "avg_kills": 7.0, "avg_deaths": 2.1, "avg_assists": 6.5,
             "top_champion": "Jinx"},
            {"player_name": "friend1", "games": 8, "wins": 3,
             "avg_kills": 3.0, "avg_deaths": 5.0, "avg_assists": 8.0,
             "top_champion": "Leona"},
        ]
        img = render_power_rankings(players)
        assert isinstance(img, Image.Image)
        assert img.size[0] == 600

    @patch("src.rankings.download_icon", return_value=None)
    def test_empty_returns_none(self, mock_dl):
        assert render_power_rankings([]) is None
