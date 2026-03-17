"""Live game alert cog. Detects when tracked players start a game."""

import logging

import discord
from discord.ext import commands, tasks

from src.champion_icons import get_icon_url

logger = logging.getLogger("leaguespy.live")


class LiveCog(commands.Cog):
    """Polls summoner pages for in-game indicators and sends alerts."""

    def __init__(self, bot):
        self.bot = bot
        interval = bot.config.get("scraping", {}).get("live_check_minutes", 2)
        self.live_check.change_interval(minutes=interval)
        self.live_check.start()

    def cog_unload(self):
        self.live_check.cancel()

    async def _check_summoner(self, summoner, db_id: int):
        """Check one summoner's in-game status and alert if new."""
        status = await self.bot.scraper.check_in_game(summoner)
        was_live = self.bot.db.is_live_game(db_id)

        if status["in_game"] and not was_live:
            self.bot.db.set_live_game(db_id, status.get("champion"), None)

            embed = discord.Embed(
                title=f"\U0001f3ae {summoner.player_name} acaba de entrar en partida",
                url=summoner.profile_url,
                colour=discord.Colour.blue(),
            )
            if status.get("champion"):
                embed.add_field(name="Champion", value=status["champion"], inline=True)
                embed.set_thumbnail(url=get_icon_url(status["champion"]))

            channel = self.bot.get_channel(self.bot.channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(self.bot.channel_id)
                except Exception:
                    return
            await channel.send(embed=embed)
            logger.info("%s started a game (%s)", summoner.player_name, status.get("champion"))

        elif not status["in_game"] and was_live:
            self.bot.db.clear_live_game(db_id)
            logger.info("%s game ended", summoner.player_name)

    @tasks.loop(minutes=2)
    async def live_check(self):
        for summoner in self.bot.summoners:
            db_id = self.bot.summoner_db_ids.get(summoner.slug)
            if db_id is None:
                continue
            try:
                await self._check_summoner(summoner, db_id)
            except Exception as e:
                logger.error("Live check failed for %s: %s", summoner.slug, e)

    @live_check.before_loop
    async def before_live(self):
        await self.bot.wait_until_ready()
