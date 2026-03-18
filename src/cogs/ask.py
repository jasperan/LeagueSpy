"""Natural language Q&A about LeagueSpy data via /spy ask and message replies."""

import logging
import discord
from discord.ext import commands
from src.llm import VLLMClient

logger = logging.getLogger("leaguespy.ask")

SYSTEM_PROMPT = """\
Eres el asistente de datos de LeagueSpy, un bot de Discord que rastrea partidas de League of Legends.
Respondes preguntas sobre las estadisticas de los jugadores rastreados.
Responde siempre en espanol, de forma concisa y directa.
Si los datos no contienen la respuesta, dilo claramente.
No inventes datos. Usa solo la informacion proporcionada.
Puedes usar formato Discord (negrita, cursiva) para resaltar datos clave."""


def _fmt_player_context(player_name: str, stats: dict, streak: tuple,
                        champions: list[dict], recent: list[dict]) -> str:
    """Format a single player's data into a text block for the LLM."""
    lines = [f"## {player_name}"]
    if stats["total_games"] > 0:
        wr = round(stats["wins"] / stats["total_games"] * 100, 1)
        lines.append(
            f"Partidas: {stats['total_games']} | Wins: {stats['wins']} | "
            f"Losses: {stats['losses']} | WR: {wr}%"
        )
        lines.append(
            f"KDA medio: {stats['avg_kills']}/{stats['avg_deaths']}/{stats['avg_assists']}"
        )
        s, lw, ll = streak
        streak_str = f"+{s}" if s > 0 else str(s)
        lines.append(f"Racha actual: {streak_str} | Mejor racha W: {lw} | Peor racha L: {ll}")
    else:
        lines.append("Sin partidas registradas.")

    if champions:
        lines.append("Campeones mas jugados:")
        for c in champions[:5]:
            cwr = round(c["wins"] / c["games"] * 100, 1) if c["games"] > 0 else 0
            lines.append(
                f"  - {c['champion']}: {c['games']}G {cwr}% WR "
                f"({c['avg_kills']}/{c['avg_deaths']}/{c['avg_assists']})"
            )

    if recent:
        lines.append("Ultimas partidas:")
        for m in recent[:5]:
            result = "W" if m["win"] else "L"
            lines.append(
                f"  - {result} {m['champion']} {m['kills']}/{m['deaths']}/{m['assists']} "
                f"({m['game_mode']}, {m.get('game_duration', '?')})"
            )

    return "\n".join(lines)


def _detect_players(question: str, known_players: list[str]) -> list[str]:
    """Return player names mentioned in the question (case-insensitive)."""
    q_lower = question.lower()
    return [p for p in known_players if p.lower() in q_lower]


class AskCog(commands.Cog):
    """Natural language Q&A about tracked player data. Handles reply-based questions."""

    def __init__(self, bot):
        self.bot = bot
        self.llm = VLLMClient(
            base_url=bot.llm_config.get("base_url", "http://localhost:8000/v1"),
            model=bot.llm_config.get("model", "qwen3.5:9b"),
            max_tokens=bot.llm_config.get("max_tokens_ask", 500),
        )

    def _get_known_players(self) -> list[str]:
        seen = set()
        result = []
        for s in self.bot.summoners:
            if s.player_name not in seen:
                seen.add(s.player_name)
                result.append(s.player_name)
        return result

    def _gather_context(self, question: str) -> str:
        """Build the data context string for the LLM based on the question."""
        known = self._get_known_players()
        mentioned = _detect_players(question, known)

        if not mentioned:
            mentioned = known

        blocks = []
        for player in mentioned:
            ids = self.bot.db.get_all_summoner_ids_for_player(player)
            if not ids:
                continue
            combined_stats = {"total_games": 0, "wins": 0, "losses": 0,
                              "avg_kills": 0, "avg_deaths": 0, "avg_assists": 0}
            all_champs = []
            all_recent = []
            streak = (0, 0, 0)
            for sid in ids:
                st = self.bot.db.get_player_stats(sid)
                combined_stats["total_games"] += st["total_games"]
                combined_stats["wins"] += st["wins"]
                combined_stats["losses"] += st["losses"]
                combined_stats["avg_kills"] += st["avg_kills"] * st["total_games"]
                combined_stats["avg_deaths"] += st["avg_deaths"] * st["total_games"]
                combined_stats["avg_assists"] += st["avg_assists"] * st["total_games"]
                all_champs.extend(self.bot.db.get_champion_stats(sid))
                all_recent.extend(self.bot.db.get_recent_matches(sid, limit=5))
                s = self.bot.db.get_streak(sid)
                if abs(s[0]) > abs(streak[0]):
                    streak = s

            total = combined_stats["total_games"]
            if total > 0:
                combined_stats["avg_kills"] = round(combined_stats["avg_kills"] / total, 1)
                combined_stats["avg_deaths"] = round(combined_stats["avg_deaths"] / total, 1)
                combined_stats["avg_assists"] = round(combined_stats["avg_assists"] / total, 1)

            blocks.append(_fmt_player_context(player, combined_stats, streak, all_champs, all_recent))

        lb = self.bot.db.get_leaderboard(min_games=1)
        if lb:
            lines = ["## Clasificacion general"]
            for i, row in enumerate(lb):
                wr = round(row["wins"] / row["total_games"] * 100, 1)
                lines.append(f"  {i+1}. {row['player_name']}: {row['total_games']}G {wr}% WR")
            blocks.append("\n".join(lines))

        if len(mentioned) == 2:
            ids_a = self.bot.db.get_all_summoner_ids_for_player(mentioned[0])
            ids_b = self.bot.db.get_all_summoner_ids_for_player(mentioned[1])
            h2h_matches = []
            for a in ids_a:
                for b in ids_b:
                    h2h_matches.extend(self.bot.db.get_h2h_record(a, b))
            if h2h_matches:
                a_wins = sum(1 for m in h2h_matches if m["a_win"])
                b_wins = sum(1 for m in h2h_matches if m["b_win"])
                lines = [
                    f"## Head-to-head: {mentioned[0]} vs {mentioned[1]}",
                    f"Total: {len(h2h_matches)} partidas | {mentioned[0]}: {a_wins}W | {mentioned[1]}: {b_wins}W",
                ]
                for m in h2h_matches[:5]:
                    winner = mentioned[0] if m["a_win"] else mentioned[1]
                    lines.append(f"  - {m['a_champ']} vs {m['b_champ']} -> {winner}")
                blocks.append("\n".join(lines))

        return "\n\n".join(blocks) if blocks else "No hay datos disponibles para los jugadores."

    async def answer(self, question: str) -> str:
        """Generate an answer to the question using LLM + DB context."""
        context = self._gather_context(question)
        user_prompt = (
            f"Datos disponibles:\n{context}\n\n"
            f"Pregunta del usuario: {question}"
        )
        answer = await self.llm.generate(SYSTEM_PROMPT, user_prompt)
        if not answer:
            return "El cerebro de LeagueSpy esta desconectado. Intentalo mas tarde."
        return answer

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != self.bot.channel_id:
            return

        content = message.content.strip()
        question = None

        # Text-based /spy ask <question> fallback
        lower = content.lower()
        if lower.startswith("/spy ask "):
            question = content[9:].strip()
            logger.info("Text-based /spy ask from %s: %s", message.author, question)
        # Reply to a bot message
        elif message.reference and message.reference.message_id:
            try:
                ref_msg = message.reference.cached_message
                if ref_msg is None:
                    ref_msg = await message.channel.fetch_message(message.reference.message_id)
                if ref_msg.author.id != self.bot.user.id:
                    return
                question = content
                logger.info("Reply-based question from %s: %s", message.author, question)
            except Exception as e:
                logger.warning("Failed to fetch referenced message: %s", e)
                return

        if not question:
            return

        async with message.channel.typing():
            try:
                answer = await self.answer(question)
            except Exception as e:
                logger.error("Failed to generate answer: %s", e, exc_info=True)
                answer = "Error al procesar la pregunta."

        embed = discord.Embed(
            description=answer[:4096],
            colour=discord.Colour.blue(),
        )
        await message.reply(embed=embed, mention_author=False)
