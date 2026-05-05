import io
import discord
from src.models import MatchResult, SummonerConfig


def build_match_announcement(
    summoner: SummonerConfig,
    match: MatchResult,
    commentary: str | None = None,
    scoreboard_image: bytes | None = None,
    view: discord.ui.View | None = None,
) -> dict:
    if match.win:
        color = discord.Colour.green()
        emoji = "\U0001f7e2"
        result = "VICTORY"
    else:
        color = discord.Colour.red()
        emoji = "\U0001f534"
        result = "DEFEAT"

    embed = discord.Embed(
        title=f"{emoji} {result} - {summoner.player_name}",
        url=summoner.profile_url,
        description=f"**{match.champion}** {match.kda} | {match.game_mode} | {match.game_duration}",
        colour=color,
    )

    if scoreboard_image:
        embed.set_image(url="attachment://scoreboard.png")

    if match.played_at:
        embed.set_footer(text=f"Played: {match.played_at}")

    payload = {"embed": embed}
    if commentary:
        payload["content"] = commentary
    if scoreboard_image:
        payload["file"] = discord.File(io.BytesIO(scoreboard_image), filename="scoreboard.png")
    if view is not None:
        payload["view"] = view
    return payload
