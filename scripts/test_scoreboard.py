#!/usr/bin/env python3
"""Generate test scoreboard images for before/after comparison."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import MatchParticipant, MatchDetails
from src.match_image import render_scoreboard


def make_test_details():
    return MatchDetails(
        team1_players=[
            MatchParticipant("jasperan#GOAT", "Diamond II", "Jinx", 8, 2, 12, 312, 16300, 68, 42),
            MatchParticipant("ShadowMid#EUW", "Platinum I", "Thresh", 1, 3, 18, 32, 8200, 72, 88),
            MatchParticipant("YoneMain99#EUW", "Emerald III", "Yone", 12, 5, 4, 245, 14100, 52, 18),
            MatchParticipant("JungleDiff#EUW", "Gold II", "Lee Sin", 6, 4, 14, 168, 11800, 65, 35),
            MatchParticipant("MidOrFeed#EUW", "Diamond IV", "Orianna", 5, 3, 10, 278, 13400, 58, 28),
        ],
        team2_players=[
            MatchParticipant("xKaisaBotx#EUW", "Platinum II", "Kai'Sa", 6, 8, 5, 289, 14800, 45, 22),
            MatchParticipant("HookCity#EUW", "Gold I", "Nautilus", 2, 7, 9, 28, 7600, 55, 62),
            MatchParticipant("WindWall#EUW", "Emerald I", "Yasuo", 4, 6, 3, 201, 11200, 38, 15),
            MatchParticipant("GravesJG#EUW", "Platinum III", "Graves", 3, 5, 7, 178, 10500, 48, 30),
            MatchParticipant("LaserBeam#EUW", "Diamond III", "Viktor", 2, 6, 6, 256, 12100, 42, 25),
        ],
        team1_result="WIN",
        team2_result="LOSS",
        team1_bans=["Zed", "Katarina", "Sylas", "Viego", "Skarner"],
        team2_bans=["Corki", "Ahri", "Aatrox", "Senna", "Lulu"],
    )


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "/tmp/scoreboard_test.png"
    details = make_test_details()
    slug = "jasperan-goat"

    try:
        png_bytes = render_scoreboard(details, slug, game_mode="Ranked Solo/Duo", game_duration="24min 32s")
    except TypeError:
        png_bytes = render_scoreboard(details, slug)

    if png_bytes:
        with open(output, "wb") as f:
            f.write(png_bytes)
        print(f"Saved {output} ({len(png_bytes):,} bytes)")
    else:
        print("Failed to render")
