"""Async client for OpenAI-compatible chat completions (vLLM / Ollama)."""

import logging
import re
import httpx

logger = logging.getLogger("leaguespy.llm")

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


class VLLMClient:
    """Thin wrapper around OpenAI-compatible /v1/chat/completions."""

    def __init__(self, base_url: str, model: str, max_tokens: int = 200):
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens

    async def generate(self, system_prompt: str, user_prompt: str) -> str | None:
        """Send a chat completion request. Returns the text or None on failure."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self.max_tokens,
            "temperature": 0.9,
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    logger.warning("LLM returned no choices")
                    return None
                content = choices[0]["message"]["content"]
                if not content:
                    logger.warning("LLM returned empty content")
                    return None
                # Strip <think>...</think> blocks from reasoning models
                content = _THINK_RE.sub("", content).strip()
                if not content:
                    logger.warning("LLM content was only thinking tags")
                    return None
                logger.debug("LLM response: %s", content[:200])
                return content
        except Exception as e:
            logger.warning("LLM request failed: %s", e)
            return None
