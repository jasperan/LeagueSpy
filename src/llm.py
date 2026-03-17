"""Async client for vLLM's OpenAI-compatible chat completions endpoint."""

import logging
import httpx

logger = logging.getLogger("leaguespy.llm")


class VLLMClient:
    """Thin wrapper around vLLM /v1/chat/completions."""

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
            "extra_body": {
                "chat_template_kwargs": {"enable_thinking": False},
            },
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return None
                return choices[0]["message"]["content"]
        except Exception as e:
            logger.warning("vLLM request failed: %s", e)
            return None
