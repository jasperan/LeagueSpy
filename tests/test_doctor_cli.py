import json
from pathlib import Path

from PIL import Image

from src import cli as cli_module
from src.doctor import CheckResult, format_results, run_preflight
from src.showcase import generate_showcase


def _write_config(path):
    path.write_text(
        """
discord:
  token: YOUR_DISCORD_BOT_TOKEN
  channel_id: 0
oracle:
  user: leaguespy
  password: leaguespy
  dsn: localhost:1523/FREEPDB1
scraping:
  interval_minutes: 5
  live_check_minutes: 2
  region: euw
llm:
  base_url: http://localhost:8000/v1
  model: qwen3.5:9b
  max_tokens: 200
  max_tokens_ask: 500
players:
  - name: jasper
    summoners:
      - slug: jasper-1971
        region: euw
""".strip(),
        encoding="utf-8",
    )


def test_run_preflight_offline_reports_skips(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    monkeypatch.setattr(
        "src.doctor.check_python_modules",
        lambda: [CheckResult("module:discord.py", "ok", "installed")],
    )
    monkeypatch.setattr(
        "src.doctor.check_playwright_ready",
        lambda: CheckResult("playwright", "ok", "/tmp/chromium"),
    )

    results, config = run_preflight(config_path, offline=True)

    assert config is not None
    assert any(result.name == "oracle" and result.status == "skip" for result in results)
    assert any(result.name == "vllm" and result.status == "skip" for result in results)
    assert any(result.name == "discord.token" and result.status == "warn" for result in results)


def test_format_results_renders_status_prefixes():
    rendered = format_results(
        [
            CheckResult("python", "ok", "3.12.2"),
            CheckResult("oracle", "skip", "offline mode"),
            CheckResult("vllm", "fail", "boom"),
        ]
    )

    assert "[PASS] python: 3.12.2" in rendered
    assert "[SKIP] oracle: offline mode" in rendered
    assert "[FAIL] vllm: boom" in rendered


def test_generate_showcase_writes_artifacts(monkeypatch, tmp_path):
    def fake_icon(_champion_name, size=48):
        return Image.new("RGBA", (size, size), (255, 0, 0, 255))

    def fake_splash(_champion_name, width=800, height=200):
        return Image.new("RGBA", (width, height), (30, 30, 30, 255))

    monkeypatch.setattr("src.match_image.download_icon", fake_icon)
    monkeypatch.setattr("src.match_image.download_splash", fake_splash)
    monkeypatch.setattr("src.daily_summary.download_icon", fake_icon)
    monkeypatch.setattr("src.daily_summary.download_splash", fake_splash)
    monkeypatch.setattr("src.rankings.download_icon", fake_icon)
    monkeypatch.setattr("src.trends.download_icon", fake_icon)

    manifest = generate_showcase(tmp_path)

    expected_keys = {"scoreboard", "solo_card", "summary", "daily_awards", "animated_summary", "trends", "power_rankings", "announcement", "announcement_text", "readme", "manifest"}
    assert set(manifest) == expected_keys
    for artifact in manifest.values():
        assert Path(artifact).exists()

    announcement = json.loads((tmp_path / "announcement.json").read_text(encoding="utf-8"))
    assert announcement["embed"]["title"].startswith("🟢 VICTORY")
    assert announcement["has_file"] is True
    assert [action["label"] for action in announcement["actions"]] == ["Ask", "Roast", "Analyze", "Trends", "Profile"]
    assert "Daily Awards" in (tmp_path / "daily_awards.txt").read_text(encoding="utf-8")


def test_cli_doctor_json_output(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    monkeypatch.setattr(
        "src.doctor.check_python_modules",
        lambda: [CheckResult("module:discord.py", "ok", "installed")],
    )
    monkeypatch.setattr(
        "src.doctor.check_playwright_ready",
        lambda: CheckResult("playwright", "ok", "/tmp/chromium"),
    )

    exit_code = cli_module.main(["doctor", "--config", str(config_path), "--offline", "--json"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["ok"] is True
    assert output["config"]["player_count"] == 1
