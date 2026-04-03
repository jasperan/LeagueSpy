import pytest

from src.config import ConfigError, build_summoner_list, load_config, read_config, summarize_config, validate_config


def _config_template():
    return {
        "discord": {
            "token": "YOUR_DISCORD_BOT_TOKEN",
            "channel_id": 0,
        },
        "oracle": {
            "user": "leaguespy",
            "password": "leaguespy",
            "dsn": "localhost:1523/FREEPDB1",
        },
        "scraping": {
            "interval_minutes": 5,
            "live_check_minutes": 2,
            "region": "euw",
        },
        "llm": {
            "base_url": "http://localhost:8000/v1",
            "model": "qwen3.5:9b",
            "max_tokens": 200,
        },
        "features": {
            "roast": True,
            "analytics": True,
            "analyst": True,
            "live_alerts": True,
            "slash_commands": True,
        },
        "players": [
            {
                "name": "jasper",
                "summoners": [
                    {"slug": "jasper-1971", "region": "euw"},
                    {"slug": "smurf-1234"},
                ],
            },
        ],
    }


def test_validate_config_doctor_mode_allows_placeholders_as_warnings():
    report = validate_config(_config_template(), mode="doctor")

    assert report.ok is True
    warning_keys = {issue.key for issue in report.warnings}
    assert "discord.token" in warning_keys
    assert "discord.channel_id" in warning_keys


def test_validate_config_runtime_mode_rejects_placeholders():
    report = validate_config(_config_template(), mode="runtime")

    assert report.ok is False
    error_keys = {issue.key for issue in report.errors}
    assert "discord.token" in error_keys
    assert "discord.channel_id" in error_keys


def test_validate_config_detects_duplicate_slugs():
    config = _config_template()
    config["players"][0]["summoners"].append({"slug": "jasper-1971", "region": "euw"})

    report = validate_config(config, mode="doctor")

    assert report.ok is False
    assert any("duplicate summoner slug" in issue.message for issue in report.errors)


def test_summarize_config_counts_players_and_features():
    summary = summarize_config(_config_template())

    assert summary["player_count"] == 1
    assert summary["summoner_count"] == 2
    assert "analytics" in summary["enabled_features"]


def test_build_summoner_list_uses_default_region():
    summoners = build_summoner_list(_config_template())
    assert [s.region for s in summoners] == ["euw", "euw"]


def test_read_config_raises_for_missing_file(tmp_path):
    missing_path = tmp_path / "missing.yaml"

    with pytest.raises(ConfigError):
        read_config(missing_path)


def test_load_config_runtime_raises_on_invalid_runtime_values(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
discord:
  token: "YOUR_DISCORD_BOT_TOKEN"
  channel_id: 0
oracle:
  user: "leaguespy"
  password: "leaguespy"
  dsn: "localhost:1523/FREEPDB1"
scraping:
  interval_minutes: 5
  live_check_minutes: 2
  region: "euw"
features:
  analytics: true
players:
  - name: "jasper"
    summoners:
      - slug: "jasper-1971"
        region: "euw"
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_config(config_path, mode="runtime")


def test_load_config_resolves_environment_placeholders(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
discord:
  token: ${DISCORD_TOKEN}
  channel_id: 123
oracle:
  user: leaguespy
  password: leaguespy
  dsn: localhost:1523/FREEPDB1
scraping:
  interval_minutes: 5
  live_check_minutes: 2
  region: euw
players:
  - name: jasper
    summoners:
      - slug: jasper-1971
        region: euw
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("DISCORD_TOKEN", "env-token")

    config = load_config(config_path)

    assert config["discord"]["token"] == "env-token"


def test_load_config_rejects_unresolved_runtime_env_placeholders(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
discord:
  token: token
  channel_id: 123
oracle:
  user: leaguespy
  password: leaguespy
  dsn: ${LEAGUESPY_DSN}
scraping:
  interval_minutes: 5
  live_check_minutes: 2
  region: euw
players:
  - name: jasper
    summoners:
      - slug: jasper-1971
        region: euw
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_config(config_path)
