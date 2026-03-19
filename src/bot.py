import asyncio
import logging
import time
from collections import deque
import yaml
import discord
from datetime import datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo
from discord.ext import commands, tasks
from src.database import Database
from src.scraper import LeagueOfGraphsScraper
from src.embeds import build_match_announcement
from src.commentary import build_commentary
from src.match_image import render_scoreboard, render_solo_card
from src.daily_summary import group_by_player, build_summary_image
from src.models import SummonerConfig, MatchDetails

logger = logging.getLogger("leaguespy")


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def build_summoner_list(config: dict) -> list[SummonerConfig]:
    default_region = config.get("scraping", {}).get("region", "euw")
    summoners = []
    for player in config.get("players", []):
        name = player["name"]
        for s in player.get("summoners", []):
            summoners.append(
                SummonerConfig(
                    player_name=name,
                    slug=s["slug"],
                    region=s.get("region", default_region),
                )
            )
    return summoners


_SUMMARY_TIMES = [dt_time(0, 0), dt_time(8, 0), dt_time(16, 0)]


def should_fire_summary(now: datetime, last_check: datetime) -> bool:
    """Return True if a summary boundary was crossed between *last_check* and *now*."""
    for t in _SUMMARY_TIMES:
        boundary = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        if last_check < boundary <= now:
            return True
    return False


class LeagueSpyBot(commands.Bot):
    def __init__(self, config: dict):
        intents = discord.Intents.default()
        if config.get("features", {}).get("message_content_intent", False):
            intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

        self.config = config
        self.channel_id = config["discord"]["channel_id"]
        self.summoners = build_summoner_list(config)
        self.scraper = LeagueOfGraphsScraper(max_concurrent=3)
        self.db = Database(
            user=config["oracle"]["user"],
            password=config["oracle"]["password"],
            dsn=config["oracle"]["dsn"],
        )

        # Ensure all summoners exist in DB
        self.summoner_db_ids = {}
        for s in self.summoners:
            db_id = self.db.get_or_create_summoner(s.player_name, s.slug, s.region)
            self.summoner_db_ids[s.slug] = db_id

        self.new_matches: deque = deque(maxlen=100)
        self.llm_config = config.get("llm", {})
        self.features = config.get("features", {})

        self._madrid_tz = ZoneInfo("Europe/Madrid")
        self._last_summary_check = datetime.now(self._madrid_tz)

    async def on_ready(self):
        logger.info("LeagueSpy bot logged in as %s", self.user)
        logger.info("Tracking %d summoner(s)", len(self.summoners))
        await self.scraper.start()
        self.db.truncate_live_games()
        if not self.check_matches.is_running():
            interval = self.config.get("scraping", {}).get("interval_minutes", 5)
            self.check_matches.change_interval(minutes=interval)
            self.check_matches.start()
        if not self.summary_check.is_running():
            self.summary_check.start()
        await self._load_cogs()

    async def _load_cogs(self):
        if self.features.get("slash_commands", False):
            from src.cogs.commands import SpyCog
            await self.add_cog(SpyCog(self))
            logger.info("Loaded SpyCog")
        if self.features.get("roast", False) and self.llm_config:
            from src.cogs.roast import RoastCog
            await self.add_cog(RoastCog(self))
            logger.info("Loaded RoastCog")
        if self.features.get("analytics", False):
            from src.cogs.analytics import AnalyticsCog
            await self.add_cog(AnalyticsCog(self))
            logger.info("Loaded AnalyticsCog")
        if self.features.get("live_alerts", False):
            from src.cogs.live import LiveCog
            await self.add_cog(LiveCog(self))
            logger.info("Loaded LiveCog")
        if self.features.get("ask", True) and self.llm_config:
            from src.cogs.ask import AskCog
            await self.add_cog(AskCog(self))
            logger.info("Loaded AskCog")
        try:
            cmds = await self.tree.sync()
            logger.info("Slash commands synced globally: %s", [c.name for c in cmds])
            channel = self.get_channel(self.channel_id)
            if channel and channel.guild:
                self.tree.copy_global_to(guild=channel.guild)
                guild_cmds = await self.tree.sync(guild=channel.guild)
                logger.info("Slash commands synced to guild %s: %s",
                            channel.guild.name, [c.name for c in guild_cmds])
        except Exception as e:
            logger.warning("Failed to sync slash commands: %s", e)

    async def on_app_command_error(self, interaction: discord.Interaction, error: Exception):
        logger.error("Slash command error: %s", error, exc_info=True)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"Error: {error}", ephemeral=True)
            else:
                await interaction.response.send_message(f"Error: {error}", ephemeral=True)
        except Exception:
            pass

    @tasks.loop(minutes=5)
    async def check_matches(self):
        t0 = time.monotonic()
        logger.info("Checking for new matches across %d summoner(s)...", len(self.summoners))
        channel = self.get_channel(self.channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(self.channel_id)
            except Exception as e:
                logger.error("Channel %d not found: %s", self.channel_id, e)
                return

        # Scrape all summoners in parallel (concurrency limited inside scraper)
        async def scrape_one(summoner):
            return summoner, await self.scraper.fetch_matches(summoner)

        tasks_list = [scrape_one(s) for s in self.summoners]
        results = await asyncio.gather(*tasks_list, return_exceptions=True)

        scrape_time = time.monotonic() - t0
        logger.info("Scraping done in %.1fs, announcing new matches...", scrape_time)

        # Announce sequentially (preserves order in Discord)
        total_new = 0
        for result in results:
            if isinstance(result, Exception):
                logger.error("Scrape failed: %s", result)
                continue
            summoner, matches = result
            try:
                db_id = self.summoner_db_ids[summoner.slug]
                new_count = 0
                for match in matches:
                    if not self.db.is_match_known(db_id, match.match_id):
                        if match.match_url:
                            try:
                                details = await self.scraper.fetch_match_details(
                                    match.match_url, summoner.region,
                                )
                                if details:
                                    match.details = details
                                    self._enrich_match_from_details(match, summoner, details)
                            except Exception as e:
                                logger.warning("Failed to fetch match details for %s: %s", match.match_id, e)
                        commentary = await build_commentary(summoner, match)
                        scoreboard_img = None
                        if match.details:
                            scoreboard_img = render_scoreboard(
                                match.details, summoner.slug,
                                game_mode=match.game_mode,
                                game_duration=match.game_duration,
                            )
                        if scoreboard_img is None:
                            scoreboard_img = render_solo_card(
                                champion=match.champion,
                                player_name=summoner.player_name,
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
                        payload = build_match_announcement(summoner, match, commentary, scoreboard_img)
                        await channel.send(**payload)
                        self.db.insert_match(db_id, match)
                        self.db.mark_announced(db_id, match.match_id)
                        self.db.update_streak(db_id, match.win)
                        self.new_matches.append({"summoner": summoner, "match": match, "db_id": db_id})
                        new_count += 1

                        # Check for rivalry match
                        analytics_cog = self.get_cog("AnalyticsCog")
                        if analytics_cog:
                            await analytics_cog.check_rivalry(
                                match.match_id, db_id, summoner.player_name, match.win,
                            )

                if new_count > 0:
                    logger.info("Announced %d new match(es) for %s", new_count, summoner.slug)
                else:
                    logger.info("No new matches for %s (%d known)", summoner.slug, len(matches))
                total_new += new_count
            except Exception as e:
                logger.error("Error announcing %s: %s", summoner.slug, e)

        elapsed = time.monotonic() - t0
        logger.info("Cycle complete: %d new match(es) total in %.1fs", total_new, elapsed)

    @check_matches.before_loop
    async def before_check(self):
        await self.wait_until_ready()

    @tasks.loop(seconds=60)
    async def summary_check(self):
        now = datetime.now(self._madrid_tz)
        if not should_fire_summary(now, self._last_summary_check):
            self._last_summary_check = now
            return
        self._last_summary_check = now

        try:
            logger.info("Generating 8-hour summary...")
            since = now - timedelta(hours=8)
            since_str = since.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S")

            matches = self.db.get_matches_since(since_str)
            if not matches:
                logger.info("No matches in the last 8 hours, skipping summary")
                return

            grouped = group_by_player(matches)
            result = await asyncio.get_event_loop().run_in_executor(
                None, build_summary_image, grouped,
            )
            if result is None:
                return

            img_buf, filename = result
            channel = self.get_channel(self.channel_id)
            if channel is None:
                channel = await self.fetch_channel(self.channel_id)

            await channel.send(
                content="**8-Hour Match Summary**",
                file=discord.File(img_buf, filename=filename),
            )
            logger.info("Summary sent as %s (%d players, %d matches)", filename, len(grouped), len(matches))
        except Exception as e:
            logger.error("Summary generation failed: %s", e)

    @summary_check.before_loop
    async def before_summary(self):
        await self.wait_until_ready()

    def _enrich_match_from_details(self, match, summoner, details):
        """Copy enhanced stats from match details into the MatchResult."""
        slug_as_name = summoner.slug.replace("-", "#").lower()
        for player in details.team1_players + details.team2_players:
            player_name_clean = player.summoner_name.lower().replace(" ", "")
            if player_name_clean == slug_as_name.replace(" ", ""):
                match.cs = player.cs
                match.gold = player.gold
                match.kill_participation = player.kill_participation
                match.vision_score = player.vision_score
                break

    async def close(self):
        await self.scraper.stop()
        self.db.close()
        await super().close()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("bot.log"),
        ],
    )

    config = load_config()
    bot = LeagueSpyBot(config)
    bot.run(config["discord"]["token"], log_handler=None)


if __name__ == "__main__":
    main()
