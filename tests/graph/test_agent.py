from __future__ import annotations

import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from msg_queue.models import StreamChunk


async def fake_stream_llm_response(messages, think_mode):
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert think_mode is True
    yield StreamChunk(chunk_type="think", content="分析中")
    yield StreamChunk(chunk_type="content", content="Hel")
    yield StreamChunk(chunk_type="content", content="lo")


@pytest.mark.asyncio
async def test_stream_agent_reply_raises_when_sys_act_llm_model_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph.agent import stream_agent_reply

    monkeypatch.delenv("SYS_ACT_LLM_MODEL", raising=False)
    monkeypatch.setenv("SYS_ACT_LLM_ENDPOINT", "http://llm.local/v1")
    monkeypatch.setenv("SYS_ACT_LLM_API_KEY", "NO_KEY")

    with pytest.raises(ValueError, match="SYS_ACT_LLM_MODEL"):
        chunks: list[StreamChunk] = []
        async for chunk in stream_agent_reply(
            message="hello",
            system_prompt="你是一個 AI 助手",
        ):
            chunks.append(chunk)


@pytest.mark.asyncio
async def test_stream_agent_reply_yields_think_and_content_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from graph.agent import stream_agent_reply

    monkeypatch.setenv("SYS_ACT_LLM_ENDPOINT", "http://llm.local/v1")
    monkeypatch.setenv("SYS_ACT_LLM_API_KEY", "NO_KEY")
    monkeypatch.setenv("SYS_ACT_LLM_MODEL", "demo-model")
    monkeypatch.setattr(
        "graph.agent._stream_llm_response",
        fake_stream_llm_response,
    )

    parts: list[StreamChunk] = []
    async for chunk in stream_agent_reply(
        message="hello",
        system_prompt="system prompt",
        think_mode=True,
    ):
        parts.append(chunk)

    assert parts == [
        StreamChunk(chunk_type="think", content="分析中"),
        StreamChunk(chunk_type="content", content="Hel"),
        StreamChunk(chunk_type="content", content="lo"),
    ]
