import argparse
import asyncio
import logging
import sys
import time
from collections import deque
import discord
from datetime import datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo
from discord.ext import commands, tasks
from src.config import (
    ConfigError,
    build_summoner_list as build_summoner_list_from_config,
    format_config_report,
    load_config as load_config_file,
    read_config,
    validate_config,
)
from src.database import Database
from src.scraper import LeagueOfGraphsScraper
from src.embeds import build_match_announcement
from src.commentary import build_commentary
from src.match_image import render_scoreboard, render_solo_card
from src.daily_summary import group_by_player, build_summary_image
from src.trends import render_trends_chart

logger = logging.getLogger("leaguespy")


def load_config(path: str = "config.yaml") -> dict:
    return load_config_file(path, mode="runtime")


def build_summoner_list(config: dict):
    return build_summoner_list_from_config(config)


_SUMMARY_TIME = dt_time(0, 0)


def should_fire_summary(now: datetime, last_check: datetime) -> bool:
    """Return True if the midnight boundary was crossed between *last_check* and *now*."""
    boundary = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if last_check < boundary <= now:
        return True
    return False


class LeagueSpyBot(commands.Bot):
    def __init__(
        self,
        config: dict,
        *,
        database_factory=Database,
        scraper_factory=LeagueOfGraphsScraper,
    ):
        intents = discord.Intents.default()
        if config.get("features", {}).get("message_content_intent", False):
            intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

        self.config = config
        self.channel_id = config["discord"]["channel_id"]
        self.summoners = build_summoner_list(config)
        self.scraper = scraper_factory(max_concurrent=3)
        self.db = database_factory(
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
        self.new_matches_analyst: deque = deque(maxlen=100)
        self.llm_config = config.get("llm", {})
        self.features = config.get("features", {})

        self._madrid_tz = ZoneInfo("Europe/Madrid")
        self._last_summary_check = datetime.now(self._madrid_tz)

    async def resolve_channel(self):
        """Return the announcement channel, fetching via REST if not in cache."""
        channel = self.get_channel(self.channel_id)
        if channel is not None:
            return channel
        try:
            return await self.fetch_channel(self.channel_id)
        except Exception as exc:
            logger.warning("Channel %d not reachable: %s", self.channel_id, exc)
            return None

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
        if self.features.get("analyst", False) and self.llm_config:
            from src.cogs.analyst import AnalystCog
            await self.add_cog(AnalystCog(self))
            logger.info("Loaded AnalystCog")
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
        channel = await self.resolve_channel()
        if channel is None:
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
                        self.new_matches_analyst.append({"summoner": summoner, "match": match, "db_id": db_id})
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
            logger.info("Generating daily summary...")
            since = now - timedelta(hours=24)
            since_str = since.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S")

            matches = self.db.get_matches_since(since_str)
            if not matches:
                logger.info("No matches in the last 24 hours, skipping summary")
                return

            grouped = group_by_player(matches)
            result = await asyncio.get_event_loop().run_in_executor(
                None, build_summary_image, grouped,
            )
            if result is None:
                return

            img_buf, filename = result
            channel = await self.resolve_channel()
            if channel is None:
                return

            await channel.send(
                content="**Daily Match Summary**",
                file=discord.File(img_buf, filename=filename),
            )
            logger.info("Summary sent as %s (%d players, %d matches)", filename, len(grouped), len(matches))

            # Generate trend charts for each active player
            await self._send_daily_trends(channel, grouped)
        except Exception as e:
            logger.error("Summary generation failed: %s", e)

    async def _send_daily_trends(self, channel, grouped: dict):
        """Generate and send trend charts for all players who played today."""
        try:
            player_names = list(grouped.keys())
            for player_name in player_names:
                ids = self.db.get_all_summoner_ids_for_player(player_name)
                if not ids:
                    continue
                all_matches = []
                for sid in ids:
                    all_matches.extend(self.db.get_recent_matches_extended(sid, limit=50))
                if len(all_matches) < 3:
                    continue
                chart = await asyncio.get_event_loop().run_in_executor(
                    None, render_trends_chart, all_matches, player_name,
                )
                if chart is None:
                    continue
                await channel.send(
                    content=f"**Tendencias: {player_name}**",
                    file=discord.File(chart, filename=f"trends_{player_name}.png"),
                )
                logger.info("Trend chart sent for %s", player_name)
        except Exception as e:
            logger.error("Daily trends generation failed: %s", e)

    @summary_check.before_loop
    async def before_summary(self):
        await self.wait_until_ready()

    def _enrich_match_from_details(self, match, summoner, details):
        """Copy enhanced stats from match details into the MatchResult."""
        parts = summoner.slug.rsplit("-", 1)
        slug_as_name = (parts[0] + "#" + parts[1]).lower() if len(parts) == 2 else summoner.slug.lower()
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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.bot",
        description="Run the LeagueSpy Discord bot or validate local setup.",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to the LeagueSpy YAML config file (default: config.yaml).",
    )
    parser.add_argument(
        "--check-config",
        "--validate-config",
        action="store_true",
        help="Validate the config and exit without connecting to Discord or Oracle.",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run the LeagueSpy doctor/preflight checks and exit.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="With --doctor, skip live connectivity checks for Oracle/vLLM.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if not (args.check_config or args.doctor):
        handlers.append(logging.FileHandler("bot.log"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=handlers,
    )

    if args.check_config:
        try:
            report = validate_config(read_config(args.config), mode="runtime")
        except ConfigError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(format_config_report(report, args.config))
        return 0 if report.ok else 1

    if args.doctor:
        from src.doctor import main as doctor_main

        doctor_args = ["--config", args.config]
        if args.offline:
            doctor_args.append("--offline")
        return doctor_main(doctor_args)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1

    bot = LeagueSpyBot(config)
    bot.run(config["discord"]["token"], log_handler=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
