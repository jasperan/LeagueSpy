from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src import bot


def _write_config(path: Path, *, token: str = "token", channel_id: int = 123) -> Path:
    config = {
        "discord": {"token": token, "channel_id": channel_id},
        "oracle": {"user": "user", "password": "pw", "dsn": "dsn"},
        "scraping": {"interval_minutes": 5, "live_check_minutes": 2, "region": "euw"},
        "features": {"analytics": True, "slash_commands": True},
        "players": [{"name": "jasper", "summoners": [{"slug": "jasper-1971", "region": "euw"}]}],
    }
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_bot_help_exits_cleanly():
    with pytest.raises(SystemExit) as exc:
        bot.main(["--help"])

    assert exc.value.code == 0


def test_bot_check_config_success(tmp_path, capsys):
    config_path = _write_config(tmp_path / "config.yaml")

    exit_code = bot.main(["--check-config", "--config", str(config_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Errors: none" in output
    assert "Summary:" in output


def test_bot_check_config_failure(tmp_path, capsys):
    config_path = _write_config(tmp_path / "config.yaml", token="YOUR_DISCORD_BOT_TOKEN", channel_id=0)

    exit_code = bot.main(["--check-config", "--config", str(config_path)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "discord.token" in output
    assert "discord.channel_id" in output
