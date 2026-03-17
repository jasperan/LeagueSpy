import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.llm import VLLMClient


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
