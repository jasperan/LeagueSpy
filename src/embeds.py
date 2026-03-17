import discord
from src.champion_icons import get_icon_url
from src.models import MatchDetails, MatchResult, SummonerConfig


def build_match_announcement(
    summoner: SummonerConfig,
    match: MatchResult,
    commentary: str | None = None,
) -> dict:
    main_embed = build_match_embed(summoner, match)
    details = getattr(match, "details", None)

    if details:
        scoreboard = build_scoreboard_embed(details)
        payload = {"embeds": [main_embed, scoreboard]}
    else:
        payload = {"embed": main_embed}

    if commentary:
        payload["content"] = commentary
    return payload


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

    if match.cs or match.gold:
        embed.add_field(name="CS", value=str(match.cs), inline=True)
        embed.add_field(
            name="Gold",
            value=f"{match.gold / 1000:.1f}k" if match.gold else "0",
            inline=True,
        )
        embed.add_field(
            name="Kill P. / Vision",
            value=f"{match.kill_participation}% / {match.vision_score}",
            inline=True,
        )

    embed.set_thumbnail(url=get_icon_url(match.champion))

    if match.played_at:
        embed.set_footer(text=f"Played: {match.played_at}")

    return embed


def build_scoreboard_embed(details: MatchDetails) -> discord.Embed:
    embed = discord.Embed(
        title="Scoreboard",
        colour=discord.Colour.dark_grey(),
    )

    for players, result, team_kda, bans in [
        (details.team1_players, details.team1_result, details.team1_kda, details.team1_bans),
        (details.team2_players, details.team2_result, details.team2_kda, details.team2_bans),
    ]:
        lines = []
        for p in players:
            lines.append(
                f"**{p.champion}** {p.summoner_name} *{p.rank}*\n"
                f"`{p.kda}` | {p.cs} CS | {p.gold_display} | {p.kill_participation}% KP | Vis: {p.vision_score}"
            )
        embed.add_field(
            name=f"{result} ({team_kda})",
            value="\n".join(lines),
            inline=False,
        )
        if bans:
            embed.add_field(
                name="Bans",
                value=", ".join(bans),
                inline=False,
            )

    return embed
