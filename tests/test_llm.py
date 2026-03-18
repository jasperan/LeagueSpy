import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.llm import VLLMClient, _strip_thinking


@pytest.fixture
def client():
    return VLLMClient(base_url="http://localhost:8000/v1", model="qwen3.5:9b")


def test_client_stores_config(client):
    assert client.base_url == "http://localhost:8000/v1"
    assert client.model == "qwen3.5:9b"
    assert client.max_tokens == 200


def test_client_custom_max_tokens():
    c = VLLMClient(base_url="http://localhost:8000/v1", model="qwen3.5:9b", max_tokens=150)
    assert c.max_tokens == 150


def test_strip_thinking_removes_trailing_reasoning_dump():
    text = (
        "Vaya tela, colega.\n\n"
        "Thinking Process:\n\n"
        "Analyze the Request:\n"
        "Role: Most acidic LoL commentator."
    )

    assert _strip_thinking(text) == "Vaya tela, colega."


def test_strip_thinking_keeps_answer_after_leading_reasoning_dump():
    text = (
        "Thinking Process:\n\n"
        "1. **Analyze the Request:** brutal roast.\n\n"
        "Gloglito ha jugado Ahri como si cobrara por morir."
    )

    assert _strip_thinking(text) == "Gloglito ha jugado Ahri como si cobrara por morir."


@pytest.mark.asyncio
async def test_generate_falls_back_to_ollama_native_when_chat_completion_is_reasoning_only():
    client = VLLMClient(base_url="http://localhost:11434/v1", model="qwen3.5:9b")

    chat_response = MagicMock()
    chat_response.status_code = 200
    chat_response.json.return_value = {
        "system_fingerprint": "fp_ollama",
        "choices": [{
            "message": {
                "content": "",
                "reasoning": "Thinking Process:\n\nAnalyze the Request:\nRole: acidic caster.",
            },
        }],
    }
    chat_response.raise_for_status = MagicMock()

    native_response = MagicMock()
    native_response.status_code = 200
    native_response.json.return_value = {
        "response": "Vaya tela, colega.",
    }
    native_response.raise_for_status = MagicMock()

    with patch("src.llm.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()

        async def fake_post(url, json):
            if url.endswith("/chat/completions"):
                return chat_response
            if url.endswith("/api/generate"):
                return native_response
            raise AssertionError(f"Unexpected URL: {url}")

        mock_instance.post = AsyncMock(side_effect=fake_post)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        result = await client.generate("system prompt", "user prompt")

    assert result == "Vaya tela, colega."


@pytest.mark.asyncio
async def test_generate_sends_correct_payload(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Vaya tela, colega."}}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("src.llm.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        result = await client.generate("system prompt", "user prompt")

    assert result == "Vaya tela, colega."


@pytest.mark.asyncio
async def test_generate_returns_none_on_error(client):
    with patch("src.llm.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(side_effect=Exception("connection refused"))
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        result = await client.generate("system", "user")

    assert result is None


@pytest.mark.asyncio
async def test_generate_returns_none_on_empty_choices(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": []}
    mock_response.raise_for_status = MagicMock()

    with patch("src.llm.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(return_value=mock_response)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        result = await client.generate("system", "user")

    assert result is None
