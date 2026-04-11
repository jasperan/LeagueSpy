"""Discord slash commands for LeagueSpy (/spy group)."""

import logging
import discord
from discord import app_commands
from discord.ext import commands
from src.analytics import compute_tilt_score
from src.models import SummonerConfig

logger = logging.getLogger("leaguespy.commands")


class SpyCog(commands.Cog):
    """Slash commands under the /spy group."""

    def __init__(self, bot):
        self.bot = bot

    def _runtime_health_snapshot(self) -> list[tuple[str, str]]:
        tracked_players = len({s.player_name for s in self.bot.summoners})
        enabled_features = sorted(
            key for key, value in (getattr(self.bot, "features", self.bot.config.get("features", {})) or {}).items()
            if value
        )

        checks: list[tuple[str, str]] = [
            ("Tracked", f"{tracked_players} player(s) / {len(self.bot.summoners)} summoner(s)"),
            ("Features", ", ".join(enabled_features) or "none"),
        ]

        db = getattr(self.bot, "db", None)
        if db is not None and hasattr(db, "ping"):
            try:
                checks.append(("Database", "OK" if db.ping() else "No response"))
            except Exception as exc:
                checks.append(("Database", f"Error: {exc}"))
        else:
            checks.append(("Database", "Unavailable"))

        scraper = getattr(self.bot, "scraper", None)
        browser_ready = bool(getattr(scraper, "_browser", None))
        checks.append(("Browser", "Ready" if browser_ready else "Not started yet"))

        llm_cfg = getattr(self.bot, "llm_config", {}) or {}
        if llm_cfg:
            checks.append(("LLM", f"Configured ({llm_cfg.get('model', 'unknown model')})"))
        else:
            checks.append(("LLM", "Disabled / unconfigured"))

        return checks

    spy = app_commands.Group(name="spy", description="LeagueSpy commands")

    @spy.command(name="add", description="Add a summoner to tracking")
    @app_commands.describe(slug="Summoner URL slug", player_name="Display name", region="Region (default: config)")
    async def _add_summoner(self, interaction: discord.Interaction, slug: str, player_name: str, region: str = None):
        if region is None:
            region = self.bot.config.get("scraping", {}).get("region", "euw")
        existing = self.bot.db.get_summoner_id_by_slug(slug)
        if existing:
            await interaction.response.send_message(f"**{slug}** ya esta siendo rastreado.", ephemeral=True)
            return
        db_id = self.bot.db.get_or_create_summoner(player_name, slug, region)
        summoner = SummonerConfig(player_name=player_name, slug=slug, region=region)
        self.bot.summoners.append(summoner)
        self.bot.summoner_db_ids[slug] = db_id
        await interaction.response.send_message(
            f"Rastreando a **{player_name}** ({slug}) en {region.upper()}.", ephemeral=True,
        )
        logger.info("Added summoner %s (%s) via slash command", player_name, slug)

    @spy.command(name="remove", description="Stop tracking a summoner")
    @app_commands.describe(slug="Summoner URL slug to remove")
    async def _remove_summoner(self, interaction: discord.Interaction, slug: str):
        db_id = self.bot.db.get_summoner_id_by_slug(slug)
        if not db_id:
            await interaction.response.send_message(f"**{slug}** no esta siendo rastreado.", ephemeral=True)
            return
        self.bot.db.deactivate_summoner(db_id)
        self.bot.summoners = [s for s in self.bot.summoners if s.slug != slug]
        self.bot.summoner_db_ids.pop(slug, None)
        await interaction.response.send_message(f"Dejando de rastrear **{slug}**.", ephemeral=True)
        logger.info("Removed summoner %s via slash command", slug)

    @spy.command(name="stats", description="Show player stats")
    @app_commands.describe(player="Player name")
    async def _stats(self, interaction: discord.Interaction, player: str = None):
        await interaction.response.defer()
        if player:
            ids = self.bot.db.get_all_summoner_ids_for_player(player)
        else:
            ids = list(self.bot.summoner_db_ids.values())
        if not ids:
            await interaction.followup.send("No se encontro el jugador.", ephemeral=True)
            return
        embeds = []
        for sid in ids:
            stats = self.bot.db.get_player_stats(sid)
            if stats["total_games"] == 0:
                continue
            streak, lw, ll = self.bot.db.get_streak(sid)
            p_name = player or "Unknown"
            for s in self.bot.summoners:
                if self.bot.summoner_db_ids.get(s.slug) == sid:
                    p_name = s.player_name
                    break
            win_rate = round(stats["wins"] / stats["total_games"] * 100, 1)
            streak_str = f"+{streak}" if streak > 0 else str(streak)
            recent = self.bot.db.get_recent_matches(sid, limit=5)
            tilt = compute_tilt_score(streak=streak, recent_matches=recent)
            embed = discord.Embed(title=f"Stats: {p_name}", colour=discord.Colour.gold())
            embed.add_field(name="Partidas", value=str(stats["total_games"]), inline=True)
            embed.add_field(name="Win Rate", value=f"{win_rate}%", inline=True)
            embed.add_field(name="Racha", value=streak_str, inline=True)
            embed.add_field(
                name="KDA Medio",
                value=f"{stats['avg_kills']}/{stats['avg_deaths']}/{stats['avg_assists']}",
                inline=True,
            )
            embed.add_field(name="Mejor Racha W", value=str(lw), inline=True)
            embed.add_field(name="Peor Racha L", value=str(ll), inline=True)
            embed.add_field(name="Tilt", value=f"{tilt}/100", inline=True)
            embeds.append(embed)
        if embeds:
            await interaction.followup.send(embeds=embeds[:10])
        else:
            await interaction.followup.send("Sin datos todavia.", ephemeral=True)

    @spy.command(name="leaderboard", description="Group rankings by win rate")
    async def _leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        rows = self.bot.db.get_leaderboard(min_games=10)
        if not rows:
            await interaction.followup.send(
                "No hay suficientes datos (min 10 partidas).", ephemeral=True,
            )
            return
        embed = discord.Embed(title="Clasificacion LeagueSpy", colour=discord.Colour.gold())
        for i, row in enumerate(rows):
            wr = round(row["wins"] / row["total_games"] * 100, 1)
            streak = row["current_streak"]
            streak_str = f"+{streak}" if streak > 0 else str(streak)
            medal = ["\U0001f947", "\U0001f948", "\U0001f949"][i] if i < 3 else f"#{i+1}"
            embed.add_field(
                name=f"{medal} {row['player_name']}",
                value=f"{wr}% WR | {row['total_games']}G | Racha: {streak_str}",
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    @spy.command(name="roast", description="Roast a player on demand")
    @app_commands.describe(player="Player name to roast")
    async def _roast_cmd(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer()
        ids = self.bot.db.get_all_summoner_ids_for_player(player)
        if not ids:
            await interaction.followup.send(f"No conozco a **{player}**.", ephemeral=True)
            return
        recent = []
        for sid in ids:
            recent.extend(self.bot.db.get_recent_matches(sid, limit=5))
        if not recent:
            await interaction.followup.send(
                f"**{player}** no tiene partidas registradas.", ephemeral=True,
            )
            return
        roast_cog = self.bot.get_cog("RoastCog")
        if not roast_cog:
            await interaction.followup.send("El motor de roasts no esta activo.", ephemeral=True)
            return
        wins = sum(1 for m in recent if m["win"])
        losses = len(recent) - wins
        avg_deaths = round(sum(m["deaths"] for m in recent) / len(recent), 1)
        champs = ", ".join(set(m["champion"] for m in recent))
        from src.cogs.roast import SYSTEM_PROMPT
        user_prompt = (
            f"Hazle un roast a {player}. Ultimas {len(recent)} partidas: "
            f"{wins}W/{losses}L, media de {avg_deaths} muertes, juega: {champs}."
        )
        roast = await roast_cog.llm.generate(SYSTEM_PROMPT, user_prompt)
        if roast:
            await interaction.followup.send(roast)
        else:
            await interaction.followup.send(
                "El cerebro de roasts esta desconectado.", ephemeral=True,
            )

    @spy.command(name="champions", description="Champion mastery breakdown")
    @app_commands.describe(player="Player name")
    async def _champions(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer()
        ids = self.bot.db.get_all_summoner_ids_for_player(player)
        if not ids:
            await interaction.followup.send(f"No conozco a **{player}**.", ephemeral=True)
            return
        all_champs = []
        for sid in ids:
            all_champs.extend(self.bot.db.get_champion_stats(sid))
        if not all_champs:
            await interaction.followup.send("Sin datos.", ephemeral=True)
            return
        embed = discord.Embed(title=f"Campeones de {player}", colour=discord.Colour.blue())
        for c in all_champs[:10]:
            wr = round(c["wins"] / c["games"] * 100, 1) if c["games"] > 0 else 0
            embed.add_field(
                name=c["champion"],
                value=f"{c['games']}G | {wr}% WR | {c['avg_kills']}/{c['avg_deaths']}/{c['avg_assists']}",
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    @spy.command(name="trends", description="Performance trend chart")
    @app_commands.describe(player="Player name")
    async def _trends(self, interaction: discord.Interaction, player: str):
        await interaction.response.defer()
        ids = self.bot.db.get_all_summoner_ids_for_player(player)
        if not ids:
            await interaction.followup.send(f"No conozco a **{player}**.", ephemeral=True)
            return
        all_matches = []
        for sid in ids:
            all_matches.extend(self.bot.db.get_recent_matches_extended(sid, limit=50))
        if not all_matches:
            await interaction.followup.send(
                f"**{player}** no tiene partidas registradas.", ephemeral=True,
            )
            return
        from src.trends import render_trends_chart
        chart = render_trends_chart(all_matches, player)
        if chart is None:
            await interaction.followup.send("No se pudo generar el grafico.", ephemeral=True)
            return
        await interaction.followup.send(
            file=discord.File(chart, filename=f"trends_{player}.png"),
        )

    @spy.command(name="ask", description="Ask anything about tracked players' data")
    @app_commands.describe(question="Your question about player stats, matches, etc.")
    async def _ask(self, interaction: discord.Interaction, question: str):
        await interaction.response.defer()
        ask_cog = self.bot.get_cog("AskCog")
        if not ask_cog:
            await interaction.followup.send(
                "El sistema de preguntas no esta activo.", ephemeral=True,
            )
            return
        answer = await ask_cog.answer(question)
        embed = discord.Embed(
            title="LeagueSpy",
            description=answer[:4096],
            colour=discord.Colour.blue(),
        )
        embed.set_footer(text=f"Pregunta: {question[:100]}")
        await interaction.followup.send(embed=embed)

    @spy.command(name="help", description="List all LeagueSpy commands")
    async def _help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="LeagueSpy Commands",
            colour=discord.Colour.gold(),
            description="All available `/spy` commands:",
        )
        embed.add_field(
            name="/spy add <slug> <player_name> [region]",
            value="Add a summoner to tracking. Region defaults to EUW.",
            inline=False,
        )
        embed.add_field(
            name="/spy remove <slug>",
            value="Stop tracking a summoner.",
            inline=False,
        )
        embed.add_field(
            name="/spy stats [player]",
            value="Show player stats (games, WR, streak, KDA). All players if no name given.",
            inline=False,
        )
        embed.add_field(
            name="/spy leaderboard",
            value="Group rankings by win rate (min 10 games).",
            inline=False,
        )
        embed.add_field(
            name="/spy champions <player>",
            value="Top 10 champions by games played with win rates.",
            inline=False,
        )
        embed.add_field(
            name="/spy h2h <player1> <player2>",
            value="Head-to-head record between two tracked players.",
            inline=False,
        )
        embed.add_field(
            name="/spy roast <player>",
            value="Generate an LLM roast from recent match history.",
            inline=False,
        )
        embed.add_field(
            name="/spy trends <player>",
            value="Performance trend chart with win rate and KDA over recent games.",
            inline=False,
        )
        embed.add_field(
            name="/spy ask <question>",
            value="Ask anything about tracked players' data in natural language. You can also reply to any bot message to ask a follow-up.",
            inline=False,
        )
        embed.add_field(
            name="/spy health",
            value="Show runtime status for the database, browser session, LLM config, and tracked players.",
            inline=False,
        )
        embed.add_field(
            name="/spy help",
            value="Show this message.",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @spy.command(name="health", description="Show runtime health for LeagueSpy")
    async def _health(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="LeagueSpy Health",
            colour=discord.Colour.green(),
            description="Current runtime snapshot for the bot and local integrations.",
        )
        for name, value in self._runtime_health_snapshot():
            embed.add_field(name=name, value=value, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @spy.command(name="h2h", description="Head-to-head record")
    @app_commands.describe(player1="First player", player2="Second player")
    async def _h2h(self, interaction: discord.Interaction, player1: str, player2: str):
        await interaction.response.defer()
        ids_a = self.bot.db.get_all_summoner_ids_for_player(player1)
        ids_b = self.bot.db.get_all_summoner_ids_for_player(player2)
        if not ids_a or not ids_b:
            await interaction.followup.send("No se encontraron ambos jugadores.", ephemeral=True)
            return
        all_matches = []
        for a in ids_a:
            for b in ids_b:
                all_matches.extend(self.bot.db.get_h2h_record(a, b))
        if not all_matches:
            await interaction.followup.send(
                f"No hay partidas compartidas entre **{player1}** y **{player2}**.\n"
                "Solo cuenta desde que ambos son rastreados.",
                ephemeral=True,
            )
            return
        a_wins = sum(1 for m in all_matches if m["a_win"])
        b_wins = sum(1 for m in all_matches if m["b_win"])
        embed = discord.Embed(title=f"{player1} vs {player2}", colour=discord.Colour.purple())
        embed.add_field(name=player1, value=f"{a_wins} victorias", inline=True)
        embed.add_field(name="VS", value=f"{len(all_matches)} partidas", inline=True)
        embed.add_field(name=player2, value=f"{b_wins} victorias", inline=True)
        recent_text = ""
        for m in all_matches[:5]:
            winner = player1 if m["a_win"] else player2
            recent_text += f"{m['a_champ']} vs {m['b_champ']} -> **{winner}**\n"
        if recent_text:
            embed.add_field(name="Ultimos enfrentamientos", value=recent_text, inline=False)
        embed.set_footer(text="Desde que ambos son rastreados.")
        await interaction.followup.send(embed=embed)
