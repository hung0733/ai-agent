from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


from msg_queue.models import StreamChunk


def test_chat_request_accepts_messages_stream_and_think_mode() -> None:
    from api.schemas.openai_chat import OpenAIChatCompletionRequest

    payload = {
        "model": "ignored-by-server",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
        "think_mode": True,
    }

    req = OpenAIChatCompletionRequest(**payload)

    assert req.stream is False
    assert req.think_mode is True
    assert req.messages[-1].role == "user"


def test_extract_queue_payload_uses_last_user_message_and_think_mode() -> None:
    from api.adapters.openai_chat import build_queue_payload
    from api.schemas.openai_chat import OpenAIChatCompletionRequest

    req = OpenAIChatCompletionRequest(
        model="any",
        think_mode=True,
        messages=[
            {"role": "system", "content": "ignore"},
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "ignore too"},
            {"role": "user", "content": "last question"},
        ],
    )

    payload = build_queue_payload(req)

    assert payload["message"] == "last question"
    assert payload["think_mode"] is True
    assert "system_prompt" not in payload


@pytest.fixture
def client() -> TestClient:
    from api.app import app

    return TestClient(app)


def test_chat_completions_route_exists(client: TestClient) -> None:
    route_paths = {route.path for route in client.app.router.routes}

    assert "/api/agents/{agent_id}/v1/chat/completions" in route_paths


def test_models_endpoint_exists_for_agent_base_url(client: TestClient) -> None:
    with patch(
        "api.routes.openai_chat.get_agent_or_404",
        new=AsyncMock(return_value=object()),
    ):
        response = client.get(
            "/api/agents/agent-123e4567-e89b-12d3-a456-426614174000/v1/models"
        )

    body = response.json()
    assert response.status_code == 200
    assert body["object"] == "list"
    assert body["data"][0]["id"] == "gpt-4o"


def test_chat_completion_returns_404_when_agent_missing(client: TestClient) -> None:
    with patch(
        "api.routes.openai_chat.get_agent_or_404",
        new=AsyncMock(side_effect=HTTPException(status_code=404, detail="Agent not found")),
    ):
        response = client.post(
            "/api/agents/agent-123e4567-e89b-12d3-a456-426614174000/v1/chat/completions",
            json={"model": "x", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 404


def test_chat_completion_enqueues_last_user_message(client: TestClient) -> None:
    captured: dict[str, object] = {}

    async def fake_create_msg_queue(**kwargs: object):
        captured.update(kwargs)

        async def _gen():
            yield StreamChunk(chunk_type="content", content="hello")
            yield StreamChunk(chunk_type="done")

        return _gen()

    with patch(
        "api.routes.openai_chat.MsgQueueHandler.create_msg_queue",
        new=AsyncMock(side_effect=fake_create_msg_queue),
    ), patch(
        "api.routes.openai_chat.get_agent_or_404",
        new=AsyncMock(return_value=object()),
    ):
        response = client.post(
            "/api/agents/agent-123e4567-e89b-12d3-a456-426614174000/v1/chat/completions",
            json={
                "model": "x",
                "think_mode": True,
                "messages": [
                    {"role": "user", "content": "first"},
                    {"role": "assistant", "content": "ignore"},
                    {"role": "user", "content": "last"},
                ],
            },
        )

    assert response.status_code == 200
    assert captured["message"] == "last"
    assert captured["think_mode"] is True
    assert "system_prompt" not in captured


def test_chat_completion_accepts_async_generator_queue_bridge(client: TestClient) -> None:
    def fake_create_msg_queue(**kwargs: object):
        async def _gen():
            yield StreamChunk(chunk_type="content", content="hello")
            yield StreamChunk(chunk_type="done")

        return _gen()

    with patch(
        "api.routes.openai_chat.MsgQueueHandler.create_msg_queue",
        new=fake_create_msg_queue,
    ), patch(
        "api.routes.openai_chat.get_agent_or_404",
        new=AsyncMock(return_value=object()),
    ):
        response = client.post(
            "/api/agents/agent-123e4567-e89b-12d3-a456-426614174000/v1/chat/completions",
            json={"model": "demo", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "hello"


def test_chat_completion_non_stream_collects_all_chunks(client: TestClient) -> None:
    async def fake_create_msg_queue(**kwargs: object):
        async def _gen():
            yield StreamChunk(chunk_type="think", content="分析中")
            yield StreamChunk(chunk_type="content", content="Hel")
            yield StreamChunk(chunk_type="content", content="lo")
            yield StreamChunk(chunk_type="done")

        return _gen()

    with patch(
        "api.routes.openai_chat.MsgQueueHandler.create_msg_queue",
        new=AsyncMock(side_effect=fake_create_msg_queue),
    ), patch(
        "api.routes.openai_chat.get_agent_or_404",
        new=AsyncMock(return_value=object()),
    ):
        response = client.post(
            "/api/agents/agent-123e4567-e89b-12d3-a456-426614174000/v1/chat/completions",
            json={"model": "demo", "stream": False, "messages": [{"role": "user", "content": "hi"}]},
        )

    body = response.json()
    assert response.status_code == 200
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "Hello"
    assert body["choices"][0]["message"]["reasoning"] == "分析中"


def test_chat_completion_stream_returns_sse(client: TestClient) -> None:
    async def fake_create_msg_queue(**kwargs: object):
        async def _gen():
            yield StreamChunk(chunk_type="think", content="分析中")
            yield StreamChunk(chunk_type="content", content="Hel")
            yield StreamChunk(chunk_type="content", content="lo")
            yield StreamChunk(chunk_type="done")

        return _gen()

    with patch(
        "api.routes.openai_chat.MsgQueueHandler.create_msg_queue",
        new=AsyncMock(side_effect=fake_create_msg_queue),
    ), patch(
        "api.routes.openai_chat.get_agent_or_404",
        new=AsyncMock(return_value=object()),
    ):
        with client.stream(
            "POST",
            "/api/agents/agent-123e4567-e89b-12d3-a456-426614174000/v1/chat/completions",
            json={"model": "demo", "stream": True, "messages": [{"role": "user", "content": "hi"}]},
        ) as response:
            body = "".join(response.iter_text())

    assert response.status_code == 200
    assert 'data: {"object":"chat.completion.chunk"' in body
    assert '"reasoning_content":' in body
    assert '"content":"Hel"' in body
    assert "data: [DONE]" in body


def test_chat_completion_returns_400_without_user_message(client: TestClient) -> None:
    with patch(
        "api.routes.openai_chat.get_agent_or_404",
        new=AsyncMock(return_value=object()),
    ):
        response = client.post(
            "/api/agents/agent-123e4567-e89b-12d3-a456-426614174000/v1/chat/completions",
            json={"model": "x", "messages": [{"role": "assistant", "content": "hi"}]},
        )

    assert response.status_code == 400


def test_chat_completion_returns_429_when_queue_full(client: TestClient) -> None:
    with patch(
        "api.routes.openai_chat.MsgQueueHandler.create_msg_queue",
        new=AsyncMock(side_effect=ValueError("隊列已滿 (max_size=100)")),
    ), patch(
        "api.routes.openai_chat.get_agent_or_404",
        new=AsyncMock(return_value=object()),
    ):
        response = client.post(
            "/api/agents/agent-123e4567-e89b-12d3-a456-426614174000/v1/chat/completions",
            json={"model": "x", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 429


def test_chat_completion_returns_500_when_queue_fails(client: TestClient) -> None:
    with patch(
        "api.routes.openai_chat.MsgQueueHandler.create_msg_queue",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ), patch(
        "api.routes.openai_chat.get_agent_or_404",
        new=AsyncMock(return_value=object()),
    ):
        response = client.post(
            "/api/agents/agent-123e4567-e89b-12d3-a456-426614174000/v1/chat/completions",
            json={"model": "x", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 500
