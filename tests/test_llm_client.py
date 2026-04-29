import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.llm_client import create_llm_client, OpenAIClient, GeminiClient

@pytest.mark.asyncio
async def test_create_llm_client():
    client = create_llm_client("openai", api_key="fake-key")
    assert isinstance(client, OpenAIClient)
    
    client = create_llm_client("gemini", api_key="fake-key")
    assert isinstance(client, GeminiClient)
    
    client = create_llm_client("builtin", api_key="fake-key")
    assert client is None

@pytest.mark.asyncio
async def test_openaiclient_success():
    client = OpenAIClient("fake-key")
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"pkg1": "包1", "pkg2": "包2"}'
    
    mock_create = AsyncMock(return_value=mock_response)
    client.client.chat.completions.create = mock_create
    
    result = await client.translate_summaries([{"name": "pkg1", "summary": "pkg1"}, {"name": "pkg2", "summary": "pkg2"}])
    assert result == {"pkg1": "包1", "pkg2": "包2"}

@pytest.mark.asyncio
async def test_geminiclient_success():
    client = GeminiClient("fake-key")
    
    mock_response = MagicMock()
    # Gemini sometimes returns markdown wrapped JSON
    mock_response.text = '```json\n{"pkg1": "包1"}\n```'
    
    mock_generate = AsyncMock(return_value=mock_response)
    client.client.aio.models.generate_content = mock_generate
    
    result = await client.translate_summaries([{"name": "pkg1", "summary": "pkg1"}])
    assert result == {"pkg1": "包1"}

@pytest.mark.asyncio
async def test_client_empty_items():
    client = OpenAIClient("fake-key")
    result = await client.translate_summaries([])
    assert result == {}
