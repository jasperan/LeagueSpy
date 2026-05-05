"""Interactive Discord actions attached to match announcement cards."""

from __future__ import annotations

import asyncio
import logging
import re

import discord

from src.cogs.analyst import ANALYST_SYSTEM_PROMPT, build_analysis_context
from src.models import MatchResult, SummonerConfig

logger = logging.getLogger("leaguespy.match_actions")

ACTION_TIMEOUT_SECONDS = 24 * 60 * 60
_CUSTOM_ID_PREFIX = "leaguespy:match"
_CUSTOM_ID_SAFE_RE = re.compile(r"[^A-Za-z0-9_.:-]+")


def describe_match_actions(summoner: SummonerConfig, match: MatchResult) -> list[dict[str, str]]:
    """Return offline-friendly metadata for the controls shown on a match card."""
    return [
        {
            "label": "Ask",
            "kind": "button",
            "description": "Ask LeagueSpy for a data-grounded read on this match.",
        },
        {
            "label": "Roast",
            "kind": "button",
            "description": "Generate a match-specific roast or fallback jab.",
        },
        {
            "label": "Analyze",
            "kind": "button",
            "description": "Show a quick tactical read with LLM support when available.",
        },
        {
            "label": "Trends",
            "kind": "button",
            "description": f"Render recent trend data for {summoner.player_name}.",
        },
        {
            "label": "Profile",
            "kind": "link",
            "description": f"Open {summoner.player_name}'s LeagueOfGraphs profile.",
            "url": summoner.profile_url,
        },
    ]


def build_match_action_view(
    bot,
    summoner: SummonerConfig,
    match: MatchResult,
    *,
    db_id: int | None = None,
    timeout: float | None = ACTION_TIMEOUT_SECONDS,
) -> "MatchActionView":
    """Build the interactive view for a live Discord match announcement."""
    return MatchActionView(bot, summoner, match, db_id=db_id, timeout=timeout)


class MatchActionView(discord.ui.View):
    """Short-lived buttons that make a match announcement replayable."""

    def __init__(
        self,
        bot,
        summoner: SummonerConfig,
        match: MatchResult,
        *,
        db_id: int | None = None,
        timeout: float | None = ACTION_TIMEOUT_SECONDS,
    ):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.summoner = summoner
        self.match = match
        self.db_id = db_id

        self.ask_button = self._add_action_button(
            "Ask",
            discord.ButtonStyle.primary,
            "ask",
            self._ask_callback,
        )
        self.roast_button = self._add_action_button(
            "Roast",
            discord.ButtonStyle.danger,
            "roast",
            self._roast_callback,
        )
        self.analyze_button = self._add_action_button(
            "Analyze",
            discord.ButtonStyle.secondary,
            "analyze",
            self._analyze_callback,
        )
        self.trends_button = self._add_action_button(
            "Trends",
            discord.ButtonStyle.success,
            "trends",
            self._trends_callback,
        )
        self.profile_button = discord.ui.Button(
            label="Profile",
            style=discord.ButtonStyle.link,
            url=summoner.profile_url,
        )
        self.add_item(self.profile_button)

    def _add_action_button(self, label: str, style: discord.ButtonStyle, action: str, callback):
        button = discord.ui.Button(
            label=label,
            style=style,
            custom_id=_custom_id(action, self.match.match_id),
        )
        button.callback = callback
        self.add_item(button)
        return button

    async def _ask_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        question = (
            f"Resume la partida de {self.summoner.player_name} con {self.match.champion}: "
            "que fue bien, que fue mal y que deberia vigilar despues."
        )
        ask_cog = _get_cog(self.bot, "AskCog")
        if ask_cog is not None and hasattr(ask_cog, "answer"):
            try:
                answer = await ask_cog.answer(question)
            except Exception as exc:
                logger.warning("Ask action failed for %s: %s", self.match.match_id, exc)
            else:
                if answer:
                    embed = discord.Embed(
                        title=f"Ask: {self.summoner.player_name} - {self.match.champion}",
                        description=answer[:4096],
                        colour=discord.Colour.blue(),
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

        await interaction.followup.send(
            _fallback_snapshot(
                self.summoner,
                self.match,
                "El sistema de preguntas no esta activo, pero este es el resumen del partido:",
            ),
            ephemeral=True,
        )

    async def _roast_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        roast_cog = _get_cog(self.bot, "RoastCog")
        if roast_cog is not None and hasattr(roast_cog, "llm"):
            try:
                from src.cogs.roast import SYSTEM_PROMPT

                prompt = (
                    f"Haz un roast breve a {self.summoner.player_name} por esta partida: "
                    f"{_result_label(self.match)}, {self.match.champion}, {self.match.kda}, "
                    f"{self.match.game_mode}, {self.match.game_duration}. "
                    "No inventes datos y no repitas las estadisticas exactas."
                )
                roast = await roast_cog.llm.generate(SYSTEM_PROMPT, prompt)
            except Exception as exc:
                logger.warning("Roast action failed for %s: %s", self.match.match_id, exc)
            else:
                if roast:
                    await interaction.followup.send(roast[:2000], ephemeral=True)
                    return

        await interaction.followup.send(_fallback_roast(self.summoner, self.match), ephemeral=True)

    async def _analyze_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        analysis = await self._llm_analysis()
        if not analysis:
            analysis = _fallback_analysis(self.summoner, self.match)

        embed = discord.Embed(
            title=f"Analisis: {self.summoner.player_name} - {self.match.champion}",
            description=analysis[:4096],
            colour=discord.Colour.green() if self.match.win else discord.Colour.red(),
        )
        embed.set_footer(text=f"{self.match.kda} | {self.match.game_duration} | {self.match.game_mode}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _trends_callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        db = getattr(self.bot, "db", None)
        if db is None or not hasattr(db, "get_all_summoner_ids_for_player"):
            await interaction.followup.send(
                "No puedo generar tendencias porque la base de datos no esta disponible.",
                ephemeral=True,
            )
            return

        try:
            ids = db.get_all_summoner_ids_for_player(self.summoner.player_name)
            matches = []
            for sid in ids:
                matches.extend(db.get_recent_matches_extended(sid, limit=50))
        except Exception as exc:
            logger.warning("Trend action failed to load data for %s: %s", self.summoner.player_name, exc)
            await interaction.followup.send(
                "No pude cargar los datos recientes para las tendencias.",
                ephemeral=True,
            )
            return

        if len(matches) < 3:
            await interaction.followup.send(
                "Aun no hay suficientes partidas recientes para dibujar una tendencia.",
                ephemeral=True,
            )
            return

        from src.trends import render_trends_chart

        loop = asyncio.get_running_loop()
        chart = await loop.run_in_executor(None, render_trends_chart, matches, self.summoner.player_name)
        if chart is None:
            await interaction.followup.send("No se pudo generar el grafico de tendencias.", ephemeral=True)
            return

        await interaction.followup.send(
            file=discord.File(chart, filename=f"trends_{self.summoner.player_name}.png"),
            ephemeral=True,
        )

    async def _llm_analysis(self) -> str | None:
        analyst_cog = _get_cog(self.bot, "AnalystCog")
        if analyst_cog is None or not hasattr(analyst_cog, "llm"):
            return None

        averages = None
        db = getattr(self.bot, "db", None)
        if self.db_id is not None and db is not None and hasattr(db, "get_champion_averages"):
            try:
                averages = db.get_champion_averages(self.db_id, self.match.champion)
            except Exception as exc:
                logger.warning("Failed to load champion averages for %s: %s", self.match.match_id, exc)

        prompt = build_analysis_context(
            player_name=self.summoner.player_name,
            champion=self.match.champion,
            win=self.match.win,
            kills=self.match.kills,
            deaths=self.match.deaths,
            assists=self.match.assists,
            cs=self.match.cs,
            gold=self.match.gold,
            kill_participation=self.match.kill_participation,
            vision_score=self.match.vision_score,
            game_duration=self.match.game_duration,
            game_mode=self.match.game_mode,
            averages=averages,
        )
        try:
            return await analyst_cog.llm.generate(ANALYST_SYSTEM_PROMPT, prompt)
        except Exception as exc:
            logger.warning("Analysis action failed for %s: %s", self.match.match_id, exc)
            return None


def _custom_id(action: str, match_id: str) -> str:
    safe_match_id = _CUSTOM_ID_SAFE_RE.sub("-", match_id)[:48]
    return f"{_CUSTOM_ID_PREFIX}:{action}:{safe_match_id}"[:100]


def _get_cog(bot, name: str):
    getter = getattr(bot, "get_cog", None)
    if not callable(getter):
        return None
    return getter(name)


def _result_label(match: MatchResult) -> str:
    return "victoria" if match.win else "derrota"


def _fallback_snapshot(summoner: SummonerConfig, match: MatchResult, prefix: str) -> str:
    return (
        f"{prefix}\n"
        f"**{summoner.player_name}** jugo **{match.champion}** en {match.game_mode}: "
        f"{_result_label(match)} con KDA {match.kda} en {match.game_duration}."
    )


def _fallback_roast(summoner: SummonerConfig, match: MatchResult) -> str:
    if match.win:
        return (
            f"{summoner.player_name} gano con {match.champion}, asi que hoy el boton de roast "
            "solo puede hacerle cosquillas al ego."
        )
    if match.deaths >= 8:
        return (
            f"{summoner.player_name} con {match.champion}: derrota y {match.deaths} muertes. "
            "Eso no fue una partida, fue una visita guiada al cementerio."
        )
    return (
        f"{summoner.player_name} perdio con {match.champion}. No fue el apocalipsis, "
        "pero tampoco material para ponerlo en el CV."
    )


def _fallback_analysis(summoner: SummonerConfig, match: MatchResult) -> str:
    kda_ratio = match.kda_ratio
    kda_label = "perfecto" if kda_ratio == float("inf") else f"{kda_ratio:.2f}"
    result = "cerrar una victoria" if match.win else "salvar una derrota"
    return (
        f"{summoner.player_name} intento {result} con {match.champion}. "
        f"El KDA fue {match.kda} ({kda_label}), con {match.cs} CS, {match.gold} de oro, "
        f"{match.kill_participation}% de participacion y {match.vision_score} de vision. "
        "Sin el analista LLM activo, esto queda como lectura rapida basada solo en datos registrados."
    )
