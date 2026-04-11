from src.analytics import compute_tilt_score


class TestTiltScore:
    def test_zero_on_no_data(self):
        assert compute_tilt_score(streak=0, recent_matches=[]) == 0

    def test_max_streak_factor(self):
        matches = [{"win": 0, "kills": 2, "deaths": 8, "assists": 3, "game_duration": "15min 0s"}] * 5
        score = compute_tilt_score(streak=-5, recent_matches=matches)
        assert score >= 40

    def test_moderate_tilt(self):
        matches = [
            {"win": 0, "kills": 3, "deaths": 6, "assists": 2, "game_duration": "25min 0s"},
            {"win": 0, "kills": 2, "deaths": 7, "assists": 1, "game_duration": "22min 0s"},
            {"win": 1, "kills": 8, "deaths": 2, "assists": 5, "game_duration": "30min 0s"},
        ]
        score = compute_tilt_score(streak=-2, recent_matches=matches)
        assert 15 <= score <= 60

    def test_clamped_to_100(self):
        matches = [{"win": 0, "kills": 0, "deaths": 15, "assists": 0, "game_duration": "12min 0s"}] * 5
        score = compute_tilt_score(streak=-10, recent_matches=matches)
        assert score <= 100

    def test_clamped_to_0(self):
        matches = [{"win": 1, "kills": 10, "deaths": 1, "assists": 8, "game_duration": "35min 0s"}] * 5
        score = compute_tilt_score(streak=5, recent_matches=matches)
        assert score == 0

    def test_ff_factor_short_games(self):
        matches = [
            {"win": 0, "kills": 1, "deaths": 5, "assists": 2, "game_duration": "15min 30s"},
            {"win": 0, "kills": 0, "deaths": 6, "assists": 1, "game_duration": "14min 20s"},
            {"win": 0, "kills": 2, "deaths": 4, "assists": 3, "game_duration": "18min 0s"},
        ]
        score = compute_tilt_score(streak=-3, recent_matches=matches)
        assert score > 30
