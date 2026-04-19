"""Tests for TaskDAO.get_next_pending_task."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.dao.task_dao import TaskDAO
from db.entity import AgentEntity, TaskEntity


def _make_task(status: str = "pending", next_process_dt: Optional[datetime] = None) -> MagicMock:
    """建立 mock task。"""
    task = MagicMock(spec=TaskEntity)
    task.id = 1
    task.status = status
    task.task_type = "method"
    task.agent_id = 100
    task.created_at = datetime.now(timezone.utc)
    task.next_process_dt = next_process_dt
    return task


def _make_agent(status: str = "idle") -> MagicMock:
    """建立 mock agent。"""
    agent = MagicMock(spec=AgentEntity)
    agent.id = 100
    agent.agent_id = "test-agent-001"
    agent.status = status
    return agent


@pytest.mark.asyncio
async def test_get_next_pending_task_returns_task_and_agent():
    task = _make_task()
    agent = _make_agent()

    mock_result = MagicMock()
    mock_result.first.return_value = (task, agent)

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    dao = TaskDAO(mock_session)
    result = await dao.get_next_pending_task()

    assert result is not None
    returned_task, returned_agent = result
    assert returned_task is task
    assert returned_agent is agent
    mock_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_next_pending_task_returns_none_when_no_results():
    mock_result = MagicMock()
    mock_result.first.return_value = None

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    dao = TaskDAO(mock_session)
    result = await dao.get_next_pending_task()

    assert result is None
