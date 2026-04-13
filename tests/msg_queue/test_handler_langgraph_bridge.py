from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from msg_queue.models import StreamChunk


@pytest.mark.asyncio
async def test_pack_sys_prompt_builds_packed_prompt_from_agent_db_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from msg_queue.handler import MsgQueueHandler
    from msg_queue.models import QueueTaskState
    from msg_queue.task import QueueTask

    captured: dict[str, object] = {}

    async def fake_apply_prompt_template(*, agent_db_id: int, agent_name: str | None = None, **kwargs: object) -> str:
        captured["agent_db_id"] = agent_db_id
        captured["agent_name"] = agent_name
        captured["kwargs"] = kwargs
        return "base prompt"

    monkeypatch.setattr(
        "msg_queue.handler.apply_prompt_template",
        fake_apply_prompt_template,
    )

    task = QueueTask(
        agent_id="agent-123",
        session_id="session-123",
        message="hello",
        system_prompt="custom prompt",
    )
    task.agent = type(
        "FakeAgent",
        (),
        {"agent_db_id": 42, "recv_agent_name": "小丸"},
    )()

    await MsgQueueHandler.pack_sys_prompt(task)

    assert captured["agent_db_id"] == 42
    assert captured["agent_name"] == "小丸"
    assert task.packed_prompt == "base prompt\ncustom prompt"
    assert task.state == QueueTaskState.PACKED_SYS_PROMPT


@pytest.mark.asyncio
async def test_send_llm_msg_prefers_packed_prompt_over_system_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from msg_queue.handler import MsgQueueHandler
    from msg_queue.task import QueueTask

    captured: dict[str, object] = {}

    class FakeAgent:
        async def send(self, **kwargs: object):
            captured.update(kwargs)
            yield StreamChunk(chunk_type="done")

    task = QueueTask(
        agent_id="agent-123",
        session_id="session-123",
        message="hello",
        system_prompt="fallback prompt",
    )
    task.packed_message = "hello"
    task.packed_prompt = "packed prompt"
    task.agent = FakeAgent()

    await MsgQueueHandler.send_llm_msg(task)

    assert captured["sys_prompt"] == "packed prompt"


@pytest.mark.asyncio
async def test_send_llm_msg_streams_graph_chunks_to_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from msg_queue.handler import MsgQueueHandler
    from msg_queue.models import QueueTaskState
    from msg_queue.task import QueueTask

    class FakeAgent:
        async def send(self, **kwargs: object):
            assert kwargs["think_mode"] is False
            yield StreamChunk(chunk_type="think", content="分析中")
            yield StreamChunk(chunk_type="content", content="Hel")
            yield StreamChunk(chunk_type="content", content="lo")

    task = QueueTask(
        agent_id="agent-123",
        session_id="session-123",
        message="hello",
        system_prompt="system prompt",
    )
    task.packed_message = "hello"
    task.agent = FakeAgent()
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
async def test_select_llm_model_does_not_require_task_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from msg_queue.handler import MsgQueueHandler
    from msg_queue.models import QueueTaskState
    from msg_queue.task import QueueTask

    task = QueueTask(
        agent_id="agent-123",
        session_id="session-123",
        message="hello",
    )

    monkeypatch.setenv("SYS_ACT_LLM_ENDPOINT", "http://llm.local/v1")
    monkeypatch.setenv("SYS_ACT_LLM_API_KEY", "NO_KEY")
    monkeypatch.setenv("SYS_ACT_LLM_MODEL", "demo-model")

    await MsgQueueHandler.select_llm_model(task)

    assert task.state == QueueTaskState.SELECTED_LLM_MODEL
