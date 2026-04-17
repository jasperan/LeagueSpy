"""AI match analyst cog. Posts tactical breakdowns after every match via vLLM."""

import logging
from discord.ext import commands, tasks
import discord
from src.llm import VLLMClient

logger = logging.getLogger("leaguespy.analyst")

ANALYST_SYSTEM_PROMPT = (
    "Eres un analista de esports profesional de League of Legends. Tu trabajo es "
    "dar un analisis tactico breve (3-4 frases) de la partida de un jugador. "
    "Compara sus estadisticas con sus medias historicas en ese campeon. "
    "Se objetivo: senala tanto lo bueno como lo malo. Usa datos concretos "
    "(numeros, porcentajes). Habla en espanol coloquial pero profesional, "
    "como un caster de la LEC. No uses emojis."
)


def build_analysis_context(
    player_name: str,
    champion: str,
    win: bool,
    kills: int,
    deaths: int,
    assists: int,
    cs: int,
    gold: int,
    kill_participation: int,
    vision_score: int,
    game_duration: str,
    game_mode: str,
    averages: dict | None,
) -> str:
    """Build the user prompt with match context and historical comparison."""
    result = "VICTORIA" if win else "DERROTA"
    kda_ratio = (kills + assists) / deaths if deaths > 0 else float("inf")
    kda_str = f"{kda_ratio:.1f}" if kda_ratio != float("inf") else "PERFECTO"

    ctx = (
        f"Jugador: {player_name}\n"
        f"Campeon: {champion}\n"
        f"Resultado: {result}\n"
        f"KDA: {kills}/{deaths}/{assists} (ratio: {kda_str})\n"
        f"CS: {cs} | Oro: {gold} | Participacion en kills: {kill_participation}% | Ward score: {vision_score}\n"
        f"Duracion: {game_duration} | Modo: {game_mode}\n"
    )

    if averages and averages["games"] >= 2:
        ctx += (
            f"\nMedias historicas en {champion} ({averages['games']} partidas):\n"
            f"KDA medio: {averages['avg_kills']}/{averages['avg_deaths']}/{averages['avg_assists']}\n"
            f"CS medio: {averages['avg_cs']} | Oro medio: {averages['avg_gold']}\n"
            f"KP medio: {averages['avg_kp']}% | Vision medio: {averages['avg_vision']}\n"
        )
    else:
        ctx += f"\nPrimera o segunda partida registrada con {champion}, sin medias historicas disponibles.\n"

    return ctx


class AnalystCog(commands.Cog, name="AnalystCog"):
    """Posts tactical match analysis after every new match."""

    def __init__(self, bot):
        self.bot = bot
        self.llm = VLLMClient(
            base_url=bot.llm_config.get("base_url", "http://localhost:8000/v1"),
            model=bot.llm_config.get("model", "qwen3.5:9b"),
            max_tokens=bot.llm_config.get("max_tokens", 300),
        )
        self.analyst_loop.start()

    def cog_unload(self):
        self.analyst_loop.cancel()

    @tasks.loop(seconds=10)
    async def analyst_loop(self):
        """Check for new matches and generate tactical analysis."""
        while self.bot.new_matches_analyst:
            entry = self.bot.new_matches_analyst.popleft()
            summoner = entry["summoner"]
            match = entry["match"]
            db_id = entry["db_id"]

            try:
                averages = self.bot.db.get_champion_averages(db_id, match.champion)

                user_prompt = build_analysis_context(
                    player_name=summoner.player_name,
                    champion=match.champion,
                    win=match.win,
                    kills=match.kills,
                    deaths=match.deaths,
                    assists=match.assists,
                    cs=match.cs,
                    gold=match.gold,
                    kill_participation=match.kill_participation,
                    vision_score=match.vision_score,
                    game_duration=match.game_duration,
                    game_mode=match.game_mode,
                    averages=averages,
                )

                analysis = await self.llm.generate(ANALYST_SYSTEM_PROMPT, user_prompt)
                if not analysis:
                    continue

                channel = await self.bot.resolve_channel()
                if channel is None:
                    continue

                color = discord.Colour.green() if match.win else discord.Colour.red()
                embed = discord.Embed(
                    title=f"Analisis: {summoner.player_name} - {match.champion}",
                    description=analysis,
                    colour=color,
                )
                embed.set_footer(text=f"{match.kda} | {match.game_duration} | {match.game_mode}")
                await channel.send(embed=embed)
                logger.info("Analysis posted for %s on %s", summoner.player_name, match.champion)

            except Exception as e:
                logger.error("Analyst error for %s: %s", summoner.player_name, e)

    @analyst_loop.before_loop
    async def before_analyst(self):
        await self.bot.wait_until_ready()
