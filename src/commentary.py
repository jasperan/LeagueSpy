import asyncio
import logging
import re

import httpx

from src.models import MatchResult, SummonerConfig

logger = logging.getLogger("leaguespy.commentary")

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3.5:9b"
OLLAMA_TIMEOUT = 45

_MINUTE_DURATION_RE = re.compile(r"^\s*(\d+)min\s*(\d+)s\s*$")
_CLOCK_DURATION_RE = re.compile(r"^\s*(\d+):(\d{1,2})\s*$")
_PREFIX_RE = re.compile(r"^(comentario|roast|praise)\s*:\s*", re.IGNORECASE)


def parse_duration_minutes(game_duration: str) -> float:
    if not game_duration:
        return 0.0

    text = game_duration.strip()
    minute_match = _MINUTE_DURATION_RE.match(text)
    if minute_match:
        minutes = int(minute_match.group(1))
        seconds = int(minute_match.group(2))
        return minutes + (seconds / 60)

    clock_match = _CLOCK_DURATION_RE.match(text)
    if clock_match:
        minutes = int(clock_match.group(1))
        seconds = int(clock_match.group(2))
        return minutes + (seconds / 60)

    return 0.0


def deaths_per_minute(match: MatchResult) -> float:
    minutes = parse_duration_minutes(match.game_duration)
    if minutes <= 0:
        return 0.0
    return match.deaths / minutes


def should_roast(match: MatchResult) -> bool:
    return (not match.win) and (
        match.deaths >= 7 or deaths_per_minute(match) >= 0.18
    )


def should_praise(match: MatchResult) -> bool:
    return match.win and match.kills >= 10 and match.deaths <= 3 and match.kda_ratio >= 4.0


def _commentary_kind(match: MatchResult) -> str | None:
    if should_roast(match):
        return "roast"
    if should_praise(match):
        return "praise"
    return None


def _result_label(match: MatchResult) -> str:
    return "Victoria" if match.win else "Derrota"


def build_result_line(summoner: SummonerConfig, match: MatchResult) -> str:
    return (
        f"Resultado de {summoner.player_name}: {_result_label(match)} | "
        f"Campeón: {match.champion} | KDA: {match.kda} | "
        f"Duración: {match.game_duration} | Modo: {match.game_mode}"
    )


def build_prompt(summoner: SummonerConfig, match: MatchResult, kind: str) -> str:
    if kind == "roast":
        style = "roast salvaje, cruel en broma y con mala leche de colega"
        tone_notes = """
Tono: colegas, descarado, cruel en broma, con mucha más pegada que antes.
Esto debe sonar a humillación deportiva, no a comentario tibio.
No suavices el golpe. Si la partida fue terrible, trátala como una catástrofe de museo.
Puedes burlarte del inting, de las visitas al cementerio, de la mecánica dudosa o de la fe suicida del jugador.
Puedes usar palabras coloquiales como mamón, manco, paquete, pedazo de paquete, recital, desastre o paseo al cementerio, pero sin odio, amenazas ni ataques personales reales.
Evita insultos humillantes directos tipo idiota, subnormal o similares.
Energía de referencia (no copies literal): recital de inting, excursión al cementerio, derrota para enmarcar.
""".strip()
    else:
        style = "elogio exagerado y divertido"
        tone_notes = """
Tono: colegas, descarado, gracioso, con chispa.
Tiene que sonar a hype grande, fanfarrón y divertido.
Puedes arrancar con expresiones como buena esa, tío, vaya animal o menuda barbaridad.
Puedes usar palabras coloquiales como animal, bestia, locura o barbaridad.
""".strip()

    return f"""
Eres LeagueSpy, un bot bromista de League of Legends.
Escribe una sola frase corta en español de España para Discord.
Tipo: {style}.
{tone_notes}
No repitas las estadísticas exactas, porque las añade el bot después.
No uses emojis, hashtags, viñetas ni comillas.
Máximo 18 palabras.

Jugador: {summoner.player_name}
Cuenta: {summoner.slug}
Resultado: {_result_label(match)}
Campeón: {match.champion}
KDA: {match.kda}
Duración: {match.game_duration}
Modo: {match.game_mode}
Muertes por minuto: {deaths_per_minute(match):.2f}

Devuelve solo la frase.
""".strip()


def _clean_response_text(text: str) -> str:
    cleaned = " ".join(text.split()).strip(" \t\n\r\"'“”")
    cleaned = _PREFIX_RE.sub("", cleaned)
    return cleaned.strip()


def _request_ollama(prompt: str) -> str:
    response = httpx.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.9,
                "num_predict": 80,
            },
        },
        timeout=OLLAMA_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    return _clean_response_text(data.get("response", ""))


async def build_commentary(summoner: SummonerConfig, match: MatchResult) -> str | None:
    kind = _commentary_kind(match)
    if kind is None:
        return None

    prompt = build_prompt(summoner, match, kind)

    try:
        line = await asyncio.to_thread(_request_ollama, prompt)
    except Exception as exc:
        logger.warning(
            "Commentary generation failed for %s (%s): %s",
            summoner.slug,
            match.match_id,
            exc,
        )
        return None

    if not line:
        return None

    return f"{line}\n\n{build_result_line(summoner, match)}"
