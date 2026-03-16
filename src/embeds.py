import discord
from src.champion_icons import get_icon_url
from src.models import MatchResult, SummonerConfig


def build_match_embed(summoner: SummonerConfig, match: MatchResult) -> discord.Embed:
    if match.win:
        color = discord.Colour.green()
        title = "VICTORY"
        emoji = "\U0001f7e2"  # green circle
    else:
        color = discord.Colour.red()
        title = "DEFEAT"
        emoji = "\U0001f534"  # red circle

    embed = discord.Embed(
        title=f"{emoji} {title}",
        url=summoner.profile_url,
        colour=color,
    )

    embed.add_field(
        name="Player",
        value=f"**{summoner.player_name}** ({summoner.slug})",
        inline=False,
    )
    embed.add_field(name="Champion", value=match.champion, inline=True)
    embed.add_field(name="KDA", value=f"{match.kda} ({match.kda_ratio})", inline=True)
    embed.add_field(name="Duration", value=match.game_duration, inline=True)
    embed.add_field(name="Mode", value=match.game_mode, inline=True)

    embed.set_thumbnail(url=get_icon_url(match.champion))

    if match.played_at:
        embed.set_footer(text=f"Played: {match.played_at}")

    return embed
