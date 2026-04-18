"""Tests for ScheduleManager."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from db.entity import ScheduleEntity, TaskEntity
from scheduler.manager import ScheduleManager


@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session


@pytest.fixture
def manager(mock_session):
    return ScheduleManager(mock_session)


@pytest.fixture
def sample_schedule():
    schedule = MagicMock(spec=ScheduleEntity)
    schedule.id = 1
    schedule.task_id = 100
    schedule.cron_expression = "0 * * * *"
    schedule.enabled = True
    schedule.last_run_at = None
    schedule.next_run_at = datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc)
    schedule.task = MagicMock(spec=TaskEntity)
    schedule.task.name = "Test Task"
    schedule.task.task_type = "scheduled"
    schedule.task.content = "Test content"
    schedule.task.agent_id = 1
    schedule.task.parameters = {"key": "value"}
    return schedule


@pytest.mark.asyncio
async def test_load_enabled_schedules(manager, mock_session):
    mock_schedule = MagicMock(spec=ScheduleEntity)
    mock_schedule.id = 1
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_schedule]
    mock_session.execute.return_value = mock_result

    result = await manager.load_enabled_schedules()

    assert result == [mock_schedule]
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_mark_schedule_executed(manager, mock_session):
    schedule = MagicMock(spec=ScheduleEntity)
    schedule.id = 1
    new_next_run = datetime(2026, 4, 18, 11, 0, tzinfo=timezone.utc)

    await manager.mark_schedule_executed(schedule, new_next_run)

    assert schedule.last_run_at is not None
    assert schedule.next_run_at == new_next_run
    mock_session.flush.assert_called()
    mock_session.refresh.assert_called()


@pytest.mark.asyncio
async def test_create_task_record(manager, mock_session, sample_schedule):
    mock_task_dao = AsyncMock()
    created_entity = MagicMock(spec=TaskEntity)
    created_entity.id = 200
    mock_task_dao.create = AsyncMock(return_value=created_entity)

    with patch.object(manager, "_task_dao", mock_task_dao):
        result = await manager.create_task_record(sample_schedule)

        assert result is not None
        mock_task_dao.create.assert_called_once()


@pytest.mark.asyncio
async def test_create_task_record_missing_task(mock_session):
    manager = ScheduleManager(mock_session)
    mock_task_dao = AsyncMock()
    manager._task_dao = mock_task_dao

    schedule = MagicMock(spec=ScheduleEntity)
    schedule.id = 2
    schedule.task = None

    result = await manager.create_task_record(schedule)

    assert result is None
    mock_task_dao.create.assert_not_called()


@pytest.mark.asyncio
async def test_load_enabled_schedules_empty(manager, mock_session):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    result = await manager.load_enabled_schedules()

    assert result == []
    mock_session.execute.assert_called_once()
