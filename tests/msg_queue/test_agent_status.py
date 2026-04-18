"""Tests for agent status management in msg queue."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


class FakeAgentEntity:
    def __init__(self, agent_id: str, status: str = "idle"):
        self.agent_id = agent_id
        self.status = status
        self.id = 1


class FakeSessionContext:
    def __init__(self, agent_status: str = "idle"):
        self.agent_status = agent_status
        self.committed = False
        self.agent_entity = FakeAgentEntity("test_agent", agent_status)

    async def __aenter__(self) -> object:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


class FakeAgentDAO:
    def __init__(self, session: FakeSessionContext):
        self.session = session
        self.get_by_agent_id_calls = 0
        self.update_status_calls = 0

    async def get_by_agent_id(self, agent_id: str) -> FakeAgentEntity:
        self.get_by_agent_id_calls += 1
        return self.session.agent_entity


@pytest.mark.asyncio
async def test_process_task_checks_agent_status_idle():
    """測試 agent 非 idle 時，任務被放回隊列。"""
    from msg_queue.manager import QueueManager
    from msg_queue.models import QueueTaskPriority, QueueTaskState, QueueTaskStatus
    from msg_queue.task import QueueTask

    qm = QueueManager(max_concurrent_tasks=5)
    qm.start()

    session = FakeSessionContext(agent_status="busy")
    task = QueueTask(
        agent_id="test_agent",
        session_id="test_session",
        message="test message",
        priority=QueueTaskPriority.NORMAL,
    )

    with patch("msg_queue.manager.async_session_factory", return_value=session):
        with patch("msg_queue.manager.AgentDAO", FakeAgentDAO):
            await qm._process_task(task)

    qm.stop()

    # 任務應該被放回隊列，狀態仍是 PENDING
    assert task.status == QueueTaskStatus.PENDING
    assert len(qm._queues[QueueTaskPriority.NORMAL]) == 1
    assert qm._queues[QueueTaskPriority.NORMAL][0] == task


@pytest.mark.asyncio
async def test_process_task_sets_agent_status_to_busy():
    """測試處理前 agent status 設為 busy。"""
    from msg_queue.manager import QueueManager
    from msg_queue.models import QueueTaskPriority, QueueTaskState, QueueTaskStatus
    from msg_queue.task import QueueTask

    qm = QueueManager(max_concurrent_tasks=5)

    session = FakeSessionContext(agent_status="idle")
    task = QueueTask(
        agent_id="test_agent",
        session_id="test_session",
        message="test message",
        priority=QueueTaskPriority.NORMAL,
    )

    # 模擬 handler 直接設為 COMPLETED
    async def fake_handler(t: QueueTask) -> None:
        t.update_state(QueueTaskState.COMPLETED)

    qm.register_state_handler(QueueTaskState.INIT, fake_handler)

    with patch("msg_queue.manager.async_session_factory", return_value=session):
        with patch("msg_queue.manager.AgentDAO", FakeAgentDAO):
            await qm._process_task(task)

    # 應該有 commit（設為 busy）
    assert session.committed
    # 任務完成
    assert task.status == QueueTaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_process_task_sets_agent_status_back_to_idle_on_success():
    """測試成功完成後 agent status 設回 idle。"""
    from msg_queue.manager import QueueManager
    from msg_queue.models import QueueTaskPriority, QueueTaskState, QueueTaskStatus
    from msg_queue.task import QueueTask

    qm = QueueManager(max_concurrent_tasks=5)

    session = FakeSessionContext(agent_status="idle")
    task = QueueTask(
        agent_id="test_agent",
        session_id="test_session",
        message="test message",
        priority=QueueTaskPriority.NORMAL,
    )

    async def fake_handler(t: QueueTask) -> None:
        t.update_state(QueueTaskState.COMPLETED)

    qm.register_state_handler(QueueTaskState.INIT, fake_handler)

    with patch("msg_queue.manager.async_session_factory", return_value=session):
        with patch("msg_queue.manager.AgentDAO", FakeAgentDAO):
            await qm._process_task(task)

    # 完成後 agent status 應為 idle
    assert session.agent_entity.status == "idle"
    assert task.status == QueueTaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_process_task_sets_agent_status_back_to_idle_on_error():
    """測試異常情況下 agent status 設回 idle。"""
    from msg_queue.manager import QueueManager
    from msg_queue.models import QueueTaskPriority, QueueTaskState, QueueTaskStatus
    from msg_queue.task import QueueTask

    qm = QueueManager(max_concurrent_tasks=5)

    session = FakeSessionContext(agent_status="idle")
    task = QueueTask(
        agent_id="test_agent",
        session_id="test_session",
        message="test message",
        priority=QueueTaskPriority.NORMAL,
    )

    async def failing_handler(t: QueueTask) -> None:
        raise RuntimeError("測試錯誤")

    qm.register_state_handler(QueueTaskState.INIT, failing_handler)

    with patch("msg_queue.manager.async_session_factory", return_value=session):
        with patch("msg_queue.manager.AgentDAO", FakeAgentDAO):
            await qm._process_task(task)

    # 即使出錯，agent status 也應為 idle
    assert session.agent_entity.status == "idle"
    assert task.status == QueueTaskStatus.FAILED
    assert "測試錯誤" in task.error


@pytest.mark.asyncio
async def test_process_task_handles_missing_agent():
    """測試找不到 agent 時任務標記為 FAILED。"""
    from msg_queue.manager import QueueManager
    from msg_queue.models import QueueTaskPriority, QueueTaskStatus
    from msg_queue.task import QueueTask

    qm = QueueManager(max_concurrent_tasks=5)

    session = FakeSessionContext(agent_status="idle")
    session.agent_entity = None

    class FakeAgentDAONone:
        def __init__(self, session):
            self.session = session

        async def get_by_agent_id(self, agent_id):
            return None

    task = QueueTask(
        agent_id="nonexistent_agent",
        session_id="test_session",
        message="test message",
        priority=QueueTaskPriority.NORMAL,
    )

    with patch("msg_queue.manager.async_session_factory", return_value=session):
        with patch("msg_queue.manager.AgentDAO", FakeAgentDAONone):
            await qm._process_task(task)

    assert task.status == QueueTaskStatus.FAILED
    assert "Agent 不存在" in task.error
