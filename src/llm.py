"""Async client for OpenAI-compatible chat completions (vLLM / Ollama)."""

import logging
import re

import httpx

logger = logging.getLogger("leaguespy.llm")

_THINK_TAG_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL | re.IGNORECASE)
_STRONG_REASONING_RE = re.compile(
    r"(?is)^\s*(?:[-*]\s*|\d+[.)]\s*)?(?:\*\*)?\s*"
    r"(thinking process|thought process|reasoning|chain of thought|"
    r"analy[sz]e(?: the)?(?: request| input(?: data)?)?)\b"
)
_PROMPT_FIELD_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*|\d+[.)]\s*)?(?:\*\*)?\s*"
    r"(role|task|tone|references|constraints|input|language|"
    r"player name|champion|result|kda|duration|mode|context)\s*:"
)
_INLINE_REASONING_RE = re.compile(
    r"(?is)\s+(thinking process|thought process|chain of thought|"
    r"analy[sz]e the request|analy[sz]e the input(?: data)?)\s*:"
)


def _is_reasoning_paragraph(paragraph: str) -> bool:
    return bool(_STRONG_REASONING_RE.match(paragraph) or _PROMPT_FIELD_RE.match(paragraph))


def _strip_thinking(text: str) -> str:
    """Remove leaked reasoning blocks and keep only the user-facing answer."""
    text = _THINK_TAG_RE.sub("", text).strip()
    if not text:
        return ""

    inline_match = _INLINE_REASONING_RE.search(text)
    if inline_match and text[:inline_match.start()].strip():
        return text[:inline_match.start()].strip()

    parts = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if not parts:
        return ""

    first_reasoning_idx = next(
        (idx for idx, part in enumerate(parts) if _STRONG_REASONING_RE.match(part)),
        None,
    )
    if first_reasoning_idx is None:
        return text

    leading_answer = "\n\n".join(parts[:first_reasoning_idx]).strip()
    if leading_answer:
        return leading_answer

    for part in reversed(parts[first_reasoning_idx + 1:]):
        if not _is_reasoning_paragraph(part):
            return part

    return ""


class VLLMClient:
    """Thin wrapper around OpenAI-compatible /v1/chat/completions."""

    def __init__(self, base_url: str, model: str, max_tokens: int = 200):
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens

    def _looks_like_ollama(self, data: dict) -> bool:
        return data.get("system_fingerprint") == "fp_ollama" or ":11434" in self.base_url

    def _ollama_api_base(self) -> str:
        return self.base_url.rstrip("/").removesuffix("/v1")

    async def _generate_ollama_native(self, system_prompt: str, user_prompt: str) -> str | None:
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.9,
                "num_predict": self.max_tokens,
            },
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._ollama_api_base()}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return _strip_thinking(data.get("response", "")) or None

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
            "think": False,
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
                content = _strip_thinking(msg.get("content") or "")
                if content:
                    return content

                if self._looks_like_ollama(data):
                    native = await self._generate_ollama_native(system_prompt, user_prompt)
                    if native:
                        return native

                reasoning = _strip_thinking(
                    msg.get("reasoning") or msg.get("reasoning_content") or "",
                )
                if reasoning:
                    return reasoning

                if msg.get("content") or msg.get("reasoning") or msg.get("reasoning_content"):
                    logger.warning("LLM content was only thinking/reasoning")
                else:
                    logger.warning("LLM returned empty content. Keys: %s", list(msg.keys()))
                return None
        except Exception as e:
            logger.warning("LLM request failed: %s", e)
            return None
