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
        # /no_think disables Qwen's reasoning mode so all tokens go to the answer
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"/no_think\n{user_prompt}"},
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
                msg = choices[0]["message"]
                content = msg.get("content") or ""
                # Fallback: Ollama may put output in 'reasoning' when content is empty
                if not content.strip():
                    content = msg.get("reasoning") or msg.get("reasoning_content") or ""
                if not content.strip():
                    logger.warning("LLM returned empty content. Keys: %s", list(msg.keys()))
                    return None
                # Strip <think>...</think> blocks just in case
                content = _THINK_RE.sub("", content).strip()
                if not content:
                    logger.warning("LLM content was only thinking tags")
                    return None
                return content
        except Exception as e:
            logger.warning("LLM request failed: %s", e)
            return None
