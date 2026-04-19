"""Tests for TaskProcessor."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from task_processor.handlers import register_method_handlers
from task_processor.processor import TaskProcessor


@pytest.fixture
def processor():
    return TaskProcessor(max_concurrent=1)


@pytest.mark.asyncio
async def test_start_stop(processor):
    await processor.start()
    assert processor._running is True
    assert processor._task is not None

    await processor.stop()
    assert processor._running is False


@pytest.mark.asyncio
async def test_start_already_running(processor):
    await processor.start()
    await processor.start()  # Should log warning, not crash
    await processor.stop()


@pytest.mark.asyncio
async def test_stop_when_not_running(processor):
    await processor.stop()  # Should not crash


@pytest.mark.asyncio
async def test_poll_and_process_no_tasks(processor):
    with patch("task_processor.processor.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = mock_session

        with patch("task_processor.processor.TaskDAO") as MockDAO:
            mock_dao = AsyncMock()
            mock_dao.get_next_pending_task = AsyncMock(return_value=None)
            MockDAO.return_value = mock_dao

            await processor._poll_and_process()

            mock_dao.get_next_pending_task.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_task_unknown_type(processor):
    from db.entity import AgentEntity, TaskEntity

    task = MagicMock(spec=TaskEntity)
    task.id = 99
    task.task_type = "unknown_type"
    task.agent_id = 100
    task.retry_count = 0
    task.error_message = None

    agent = MagicMock(spec=AgentEntity)
    agent.id = 100
    agent.agent_id = "test-agent"

    with patch("task_processor.processor.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit = AsyncMock()
        mock_factory.return_value = mock_session

        with patch("task_processor.processor.TaskDAO") as MockTaskDAO, \
             patch("task_processor.processor.AgentDAO") as MockAgentDAO:
            mock_task_dao = AsyncMock()
            mock_task_dao.get_by_id = AsyncMock(return_value=task)
            MockTaskDAO.return_value = mock_task_dao

            mock_agent_dao = AsyncMock()
            mock_agent_dao.get_by_id = AsyncMock(return_value=MagicMock(status="idle"))
            MockAgentDAO.return_value = mock_agent_dao

            await processor._process_task(task, agent)

            # Task should be set back to pending with error
            assert task.status == "pending"
            assert task.error_message is not None


@pytest.mark.asyncio
async def test_process_task_method_success(processor):
    from db.entity import AgentEntity, TaskEntity

    task = MagicMock(spec=TaskEntity)
    task.id = 100
    task.task_type = "method"
    task.agent_id = 100
    task.parameters = {}
    task.retry_count = 0

    agent = MagicMock(spec=AgentEntity)
    agent.id = 100
    agent.agent_id = "test-agent"

    register_method_handlers()

    with patch("task_processor.processor.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_factory.return_value = mock_session

        with patch("task_processor.processor.TaskDAO") as MockTaskDAO, \
             patch("task_processor.processor.AgentDAO") as MockAgentDAO:
            mock_task_dao = AsyncMock()
            mock_task_dao.get_by_id = AsyncMock(return_value=task)
            MockTaskDAO.return_value = mock_task_dao

            mock_agent_dao = AsyncMock()
            mock_agent_dao.get_by_id = AsyncMock(return_value=MagicMock(status="idle"))
            MockAgentDAO.return_value = mock_agent_dao

            await processor._process_task(task, agent)

            assert task.status == "completed"
