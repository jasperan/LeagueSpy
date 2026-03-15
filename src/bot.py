import logging
import yaml
import discord
from discord.ext import commands, tasks
from src.database import Database
from src.scraper import OpGGScraper
from src.embeds import build_match_embed
from src.models import SummonerConfig

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


class LeagueSpyBot(commands.Bot):
    def __init__(self, config: dict):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

        self.config = config
        self.channel_id = config["discord"]["channel_id"]
        self.summoners = build_summoner_list(config)
        self.scraper = OpGGScraper(delay_between_requests=2.0)
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

    async def on_ready(self):
        logger.info("LeagueSpy bot logged in as %s", self.user)
        logger.info("Tracking %d summoner(s)", len(self.summoners))
        if not self.check_matches.is_running():
            interval = self.config.get("scraping", {}).get("interval_minutes", 5)
            self.check_matches.change_interval(minutes=interval)
            self.check_matches.start()

    @tasks.loop(minutes=5)
    async def check_matches(self):
        logger.info("Checking for new matches...")
        channel = self.get_channel(self.channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(self.channel_id)
            except Exception as e:
                logger.error("Channel %d not found: %s", self.channel_id, e)
                return

        for summoner in self.summoners:
            try:
                matches = await self.scraper.fetch_matches(summoner)
                db_id = self.summoner_db_ids[summoner.slug]

                new_count = 0
                for match in matches:
                    if not self.db.is_match_known(db_id, match.match_id):
                        self.db.insert_match(db_id, match)
                        embed = build_match_embed(summoner, match)
                        await channel.send(embed=embed)
                        self.db.mark_announced(db_id, match.match_id)
                        new_count += 1

                if new_count > 0:
                    logger.info("Announced %d new match(es) for %s", new_count, summoner.slug)
            except Exception as e:
                logger.error("Error checking %s: %s", summoner.slug, e)

    @check_matches.before_loop
    async def before_check(self):
        await self.wait_until_ready()

    async def close(self):
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
