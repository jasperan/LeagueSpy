from src.awards import compute_daily_awards, format_daily_awards


def _match(player, champion, win, kills, deaths, assists, *, kp=50, vision=10, duration="30:00"):
    return {
        "player_name": player,
        "champion": champion,
        "win": win,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "kill_participation": kp,
        "vision_score": vision,
        "game_duration": duration,
    }


def test_compute_daily_awards_returns_social_recap_categories():
    matches = [
        _match("jasper", "Jinx", 1, 14, 2, 9, kp=68, vision=19),
        _match("jasper", "Lux", 0, 4, 7, 8, kp=58, vision=28),
        _match("friend1", "Leona", 1, 2, 4, 18, kp=72, vision=44),
    ]

    awards = compute_daily_awards(matches)

    assert [award.title for award in awards] == [
        "MVP",
        "Tilt Watch",
        "Cleanest Game",
        "Grinder",
        "Vision Lead",
    ]
    assert awards[0].player_name == "jasper"
    assert awards[1].reason.startswith("7 deaths")
    assert awards[3].player_name == "jasper"
    assert awards[4].player_name == "friend1"


def test_compute_daily_awards_handles_empty_input():
    assert compute_daily_awards([]) == []


def test_compute_daily_awards_respects_limit():
    matches = [
        _match("jasper", "Jinx", 1, 14, 2, 9),
        _match("friend1", "Leona", 0, 1, 8, 11),
    ]

    awards = compute_daily_awards(matches, max_awards=2)

    assert len(awards) == 2
    assert [award.title for award in awards] == ["MVP", "Tilt Watch"]


def test_format_daily_awards_renders_discord_markdown():
    awards = compute_daily_awards([
        _match("jasper", "Jinx", 1, 14, 2, 9),
        _match("friend1", "Leona", 0, 1, 8, 11),
    ])

    rendered = format_daily_awards(awards)

    assert rendered.startswith("**Daily Awards**")
    assert "**MVP:** jasper on Jinx" in rendered
    assert "**Tilt Watch:** friend1 on Leona" in rendered


def test_format_daily_awards_empty_returns_empty_string():
    assert format_daily_awards([]) == ""
