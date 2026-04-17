"""LLM roast engine cog. Fires Spanish roasts on losses via vLLM."""

import logging
from discord.ext import commands, tasks
from src.llm import VLLMClient

logger = logging.getLogger("leaguespy.roast")

SYSTEM_PROMPT = (
    "Eres el comentarista mas acido del League of Legends. Tu trabajo es "
    "destrozar a los jugadores cuando pierden. Se creativo, breve (2-3 frases "
    "maximo), y usa humor espanol coloquial. Puedes hacer referencias al futbol, "
    "a la cultura espanola, y al juego. Nunca seas ofensivo con temas personales, "
    "solo sobre su gameplay. Se despiadado pero gracioso."
)

SYSTEM_PROMPT_COMPLIMENT = (
    "Eres el comentarista mas sarcastico del League of Legends. Alguien acaba de "
    "jugar una partida perfecta sin morir. Hazle un cumplido que suene a insulto. "
    "Breve (2-3 frases maximo), humor espanol coloquial. Insinua que fue suerte, "
    "que los rivales eran bots, o que seguro manana vuelve a feedear."
)


def classify_trigger(win: bool, streak: int, kills: int = 0, deaths: int = 0) -> str | None:
    """Determine the roast trigger type, or None if no roast should fire."""
    if not win and kills == 0:
        return "zero_kills"
    if not win and streak <= -2:
        return "streak"
    if not win:
        return "single_loss"
    if win and deaths == 0:
        return "perfect_kda"
    return None


def build_roast_context(
    player_name: str,
    champion: str,
    kda: str,
    duration: str,
    streak: int,
    recent_roasts: list[str],
) -> str:
    """Build the user prompt with match context for the LLM."""
    if streak <= -2:
        ctx = (
            f"{player_name} lleva {abs(streak)} derrotas seguidas. "
            f"Ultima partida: {champion}, {kda}, {duration}."
        )
    else:
        ctx = f"{player_name} perdio con {champion}, {kda}, {duration}."

    if recent_roasts:
        ctx += "\n\nNo repitas estas frases:\n"
        for r in recent_roasts:
            ctx += f"- {r}\n"

    return ctx


class RoastCog(commands.Cog):
    """Monitors new matches and fires Spanish roasts on losses."""

    def __init__(self, bot):
        self.bot = bot
        self.llm = VLLMClient(
            base_url=bot.llm_config.get("base_url", "http://localhost:8000/v1"),
            model=bot.llm_config.get("model", "qwen3.5:9b"),
            max_tokens=bot.llm_config.get("max_tokens", 200),
        )
        self.roast_loop.start()

    def cog_unload(self):
        self.roast_loop.cancel()

    @tasks.loop(seconds=10)
    async def roast_loop(self):
        """Check for new matches and roast losses."""
        while self.bot.new_matches:
            entry = self.bot.new_matches.popleft()
            summoner = entry["summoner"]
            match = entry["match"]
            db_id = entry["db_id"]

            streak, _, _ = self.bot.db.get_streak(db_id)
            trigger = classify_trigger(
                win=match.win, streak=streak, kills=match.kills, deaths=match.deaths,
            )
            if trigger is None:
                continue

            recent_roasts = self.bot.db.get_recent_roasts(db_id, limit=5)

            if trigger == "perfect_kda":
                system = SYSTEM_PROMPT_COMPLIMENT
                user_prompt = (
                    f"{summoner.player_name} fue {match.kda} con {match.champion} "
                    f"en {match.game_duration}. Partida perfecta sin morir."
                )
            else:
                system = SYSTEM_PROMPT
                user_prompt = build_roast_context(
                    player_name=summoner.player_name,
                    champion=match.champion,
                    kda=match.kda,
                    duration=match.game_duration,
                    streak=streak,
                    recent_roasts=recent_roasts,
                )

            roast = await self.llm.generate(system, user_prompt)
            if not roast:
                continue

            channel = await self.bot.resolve_channel()
            if channel is None:
                continue

            await channel.send(roast)
            self.bot.db.store_roast(db_id, match.match_id, roast, trigger)
            logger.info("Roasted %s (%s): %s", summoner.player_name, trigger, roast[:80])

    @roast_loop.before_loop
    async def before_roast(self):
        await self.bot.wait_until_ready()
