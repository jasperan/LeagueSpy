"""Offline artifact generator for README-style LeagueSpy walkthroughs."""

from __future__ import annotations

import json
from pathlib import Path

from src.commentary import build_result_line
from src.daily_summary import build_summary_image, group_by_player
from src.embeds import build_match_announcement
from src.match_image import render_scoreboard, render_solo_card
from src.rankings import render_power_rankings
from src.sample_data import (
    SAMPLE_SUMMONER,
    sample_animated_summary_matches,
    sample_match_details,
    sample_match_result,
    sample_summary_matches,
    sample_trend_matches,
    sample_weekly_rankings,
)
from src.trends import render_trends_chart


def generate_showcase(output_dir: str | Path) -> dict[str, str]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    match = sample_match_result()
    details = sample_match_details()
    summary_matches = sample_summary_matches()
    trend_matches = sample_trend_matches()
    rankings = sample_weekly_rankings()

    artifacts: dict[str, str] = {}

    scoreboard_bytes = render_scoreboard(details, SAMPLE_SUMMONER.slug, match.game_mode, match.game_duration)
    if scoreboard_bytes:
        artifacts["scoreboard"] = str(_write_bytes(output_dir / "scoreboard.png", scoreboard_bytes))

    solo_card = render_solo_card(
        champion=match.champion,
        player_name=SAMPLE_SUMMONER.player_name,
        win=match.win,
        kills=match.kills,
        deaths=match.deaths,
        assists=match.assists,
        game_mode=match.game_mode,
        game_duration=match.game_duration,
        cs=match.cs,
        gold=match.gold,
        kill_participation=match.kill_participation,
        vision_score=match.vision_score,
    )
    if solo_card:
        artifacts["solo_card"] = str(_write_bytes(output_dir / "solo_card.png", solo_card))

    summary = build_summary_image(group_by_player(summary_matches))
    if summary:
        summary_buf, summary_name = summary
        artifacts["summary"] = str(_write_bytes(output_dir / summary_name, summary_buf.getvalue()))

    animated_summary = build_summary_image(group_by_player(sample_animated_summary_matches()))
    if animated_summary:
        animated_buf, _animated_name = animated_summary
        artifacts["animated_summary"] = str(
            _write_bytes(output_dir / "animated_leaguespy_summary.gif", animated_buf.getvalue())
        )

    trends_buf = render_trends_chart(trend_matches, SAMPLE_SUMMONER.player_name)
    if trends_buf:
        artifacts["trends"] = str(_write_bytes(output_dir / "trends.png", trends_buf.getvalue()))

    rankings_img = render_power_rankings(rankings)
    if rankings_img:
        ranking_path = output_dir / "power_rankings.png"
        rankings_img.save(ranking_path, format="PNG")
        artifacts["power_rankings"] = str(ranking_path)

    commentary = build_result_line(SAMPLE_SUMMONER, match)
    payload = build_match_announcement(
        SAMPLE_SUMMONER,
        match,
        commentary=commentary,
        scoreboard_image=scoreboard_bytes,
    )
    announcement_path = output_dir / "announcement.json"
    announcement_path.write_text(
        json.dumps(
            {
                "content": payload.get("content"),
                "embed": payload["embed"].to_dict(),
                "has_file": "file" in payload,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    artifacts["announcement"] = str(announcement_path)

    announcement_text_path = output_dir / "announcement.txt"
    announcement_text_path.write_text(
        (
            f"{payload.get('content', '')}\n"
            f"{payload['embed'].title}\n"
            f"{payload['embed'].description}\n"
        ).strip() + "\n",
        encoding="utf-8",
    )
    artifacts["announcement_text"] = str(announcement_text_path)

    notes_path = output_dir / "README.txt"
    notes_path.write_text(_build_notes(artifacts), encoding="utf-8")
    artifacts["readme"] = str(notes_path)

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(artifacts, indent=2), encoding="utf-8")
    artifacts["manifest"] = str(manifest_path)

    return artifacts


def format_showcase_report(artifacts: dict[str, str]) -> str:
    lines = ["LeagueSpy showcase artifacts:"]
    lines.extend(f"- {name}: {path}" for name, path in artifacts.items())
    return "\n".join(lines)


def _write_bytes(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path


def _build_notes(artifacts: dict[str, str]) -> str:
    names = "\n".join(f"- {name}: {Path(path).name}" for name, path in artifacts.items())
    return (
        "LeagueSpy showcase output\n"
        "========================\n"
        "These files are generated from bundled sample data so you can validate the visual/rendering path\n"
        "without Discord, Oracle, or live LeagueOfGraphs scraping.\n\n"
        f"Generated files:\n{names}\n"
    )
