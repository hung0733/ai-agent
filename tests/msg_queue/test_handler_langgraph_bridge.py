from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from msg_queue.models import StreamChunk


@pytest.mark.asyncio
async def test_send_llm_msg_streams_graph_chunks_to_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from msg_queue.handler import MsgQueueHandler
    from msg_queue.models import QueueTaskState
    from msg_queue.task import QueueTask

    async def fake_stream_agent_reply(
        message: str,
        system_prompt: str | None = None,
        think_mode: bool | None = None,
    ):
        assert think_mode is None
        yield StreamChunk(chunk_type="think", content="分析中")
        yield StreamChunk(chunk_type="content", content="Hel")
        yield StreamChunk(chunk_type="content", content="lo")

    monkeypatch.setattr(
        "msg_queue.handler.stream_agent_reply",
        fake_stream_agent_reply,
    )

    task = QueueTask(
        agent_id="agent-123",
        session_id="session-123",
        message="hello",
        system_prompt="system prompt",
    )
    task.packed_message = "hello"
    stream_callback = AsyncMock()
    complete_callback = AsyncMock()
    object.__setattr__(task, "stream_callback", stream_callback)
    object.__setattr__(task, "complete_callback", complete_callback)

    await MsgQueueHandler.send_llm_msg(task)

    assert task.state == QueueTaskState.STREAMING_TO_CLIENT
    assert stream_callback.await_count == 3
    assert stream_callback.await_args_list[0].args[0] == StreamChunk(
        chunk_type="think",
        content="分析中",
    )
    complete_callback.assert_awaited_once_with({})


@pytest.mark.asyncio
async def test_send_llm_msg_raises_when_message_not_packed() -> None:
    from msg_queue.handler import MsgQueueHandler
    from msg_queue.task import QueueTask

    task = QueueTask(
        agent_id="agent-123",
        session_id="session-123",
        message="hello",
    )

    with pytest.raises(ValueError, match="訊息未打包"):
        await MsgQueueHandler.send_llm_msg(task)


@pytest.mark.asyncio
async def test_select_llm_model_does_not_require_task_agent() -> None:
    from msg_queue.handler import MsgQueueHandler
    from msg_queue.models import QueueTaskState
    from msg_queue.task import QueueTask

    task = QueueTask(
        agent_id="agent-123",
        session_id="session-123",
        message="hello",
    )

    await MsgQueueHandler.select_llm_model(task)

    assert task.state == QueueTaskState.SELECTED_LLM_MODEL
