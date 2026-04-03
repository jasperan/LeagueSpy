from __future__ import annotations

from pathlib import Path

from PIL import Image

from src.demo import generate_demo
import src.daily_summary as daily_summary
import src.match_image as match_image
import src.rankings as rankings
import src.trends as trends


def _fake_icon(*args, size=32, **kwargs):
    return Image.new("RGBA", (size, size), (255, 0, 0, 255))


def _fake_splash(*args, width=800, height=220, **kwargs):
    return Image.new("RGBA", (width, height), (20, 20, 60, 255))


def test_generate_demo_writes_expected_artifacts(tmp_path, monkeypatch):
    for module in (match_image, daily_summary, rankings, trends):
        monkeypatch.setattr(module, "download_icon", _fake_icon)
    for module in (match_image, daily_summary):
        monkeypatch.setattr(module, "download_splash", _fake_splash)

    generated = generate_demo(tmp_path)
    names = {path.name for path in generated}

    expected = {
        "scoreboard.png",
        "solo_card.png",
        "leaguespy_summary.png",
        "animated_leaguespy_summary.gif",
        "trends.png",
        "power_rankings.png",
        "announcement.json",
        "announcement.txt",
        "README.txt",
        "manifest.json",
    }

    assert expected.issubset(names)
    for name in expected:
        assert (tmp_path / name).exists(), name
