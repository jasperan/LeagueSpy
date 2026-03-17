"""Analytics cog: rivalry detection, weekly power rankings."""

import logging
from datetime import datetime, time as dt_time
from io import BytesIO
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

from src.rankings import render_power_rankings

logger = logging.getLogger("leaguespy.analytics")

_RANKING_TIME = dt_time(10, 0)


class AnalyticsCog(commands.Cog):
    """Weekly power rankings and rivalry detection."""

    def __init__(self, bot):
        self.bot = bot
        self._madrid_tz = ZoneInfo("Europe/Madrid")
        self._last_ranking_check = datetime.now(self._madrid_tz)
        self.weekly_ranking_check.start()

    def cog_unload(self):
        self.weekly_ranking_check.cancel()

    async def check_rivalry(self, match_id: str, summoner_id: int, summoner_player: str, match_win: bool):
        rival = self.bot.db.check_rivalry(match_id, summoner_id)
        if rival is None:
            return
        if rival["win"] == (1 if match_win else 0):
            return

        winner = summoner_player if match_win else rival["player_name"]
        loser = rival["player_name"] if match_win else summoner_player

        h2h = self.bot.db.get_h2h_record(summoner_id, rival["summoner_id"])
        a_total = sum(1 for m in h2h if m["a_win"])
        b_total = sum(1 for m in h2h if m["b_win"])

        embed = discord.Embed(title="RIVALIDAD DETECTADA", colour=discord.Colour.purple())
        embed.add_field(name="Ganador", value=f"**{winner}**", inline=True)
        embed.add_field(name="Perdedor", value=f"**{loser}**", inline=True)
        embed.add_field(name="Historico", value=f"{summoner_player} {a_total} - {b_total} {rival['player_name']}", inline=False)

        channel = self.bot.get_channel(self.bot.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(self.bot.channel_id)
            except Exception:
                return
        await channel.send(embed=embed)
        logger.info("Rivalry: %s vs %s (match %s)", summoner_player, rival["player_name"], match_id)

    @tasks.loop(seconds=60)
    async def weekly_ranking_check(self):
        now = datetime.now(self._madrid_tz)
        if now.weekday() != 0:
            self._last_ranking_check = now
            return
        boundary = now.replace(hour=10, minute=0, second=0, microsecond=0)
        if not (self._last_ranking_check < boundary <= now):
            self._last_ranking_check = now
            return
        self._last_ranking_check = now

        try:
            players = self.bot.db.get_weekly_stats()
            if not players:
                return
            img = render_power_rankings(players)
            if img is None:
                return
            buf = BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            channel = self.bot.get_channel(self.bot.channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(self.bot.channel_id)
            await channel.send(
                content="**Power Rankings Semanal**",
                file=discord.File(buf, filename="power_rankings.png"),
            )
            logger.info("Weekly power rankings posted (%d players)", len(players))
        except Exception as e:
            logger.error("Weekly rankings failed: %s", e)

    @weekly_ranking_check.before_loop
    async def before_ranking(self):
        await self.bot.wait_until_ready()
