"""Tests for TaskScheduler."""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from db.entity import ScheduleEntity
from scheduler.scheduler import TaskScheduler


@pytest.fixture
def mock_schedule():
    schedule = MagicMock(spec=ScheduleEntity)
    schedule.id = 1
    schedule.cron_expression = "0 * * * *"
    schedule.enabled = True
    schedule.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=2)
    return schedule


@pytest.fixture
def scheduler():
    return TaskScheduler()


def test_add_schedule_to_heap(scheduler, mock_schedule):
    scheduler._add_to_heap(mock_schedule)
    assert len(scheduler._heap) == 1


def test_get_due_schedules(scheduler, mock_schedule):
    # 設置為已經到期
    mock_schedule.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    scheduler._add_to_heap(mock_schedule)

    due = scheduler._get_due_schedules()
    assert len(due) == 1
    assert due[0] == mock_schedule


def test_get_sleep_time_with_future_schedule(scheduler, mock_schedule):
    future_time = datetime.now(timezone.utc) + timedelta(seconds=30)
    mock_schedule.next_run_at = future_time
    scheduler._add_to_heap(mock_schedule)

    sleep_time = scheduler._get_sleep_time()
    assert 0 < sleep_time <= 30


def test_get_sleep_time_with_due_schedule(scheduler, mock_schedule):
    mock_schedule.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    scheduler._add_to_heap(mock_schedule)

    sleep_time = scheduler._get_sleep_time()
    assert sleep_time < 1


def test_get_sleep_time_empty_heap(scheduler):
    sleep_time = scheduler._get_sleep_time()
    assert sleep_time == 60  # Default max wait


def test_scatter_schedules_single(scheduler):
    schedules = [MagicMock()]
    result = scheduler._scatter_schedules(schedules)
    assert len(result) == 1
    assert result[0][1] == 0  # Immediate execution


def test_scatter_schedules_multiple(scheduler):
    schedules = [MagicMock() for _ in range(3)]
    result = scheduler._scatter_schedules(schedules)
    assert len(result) == 3
    # All delays should be within 5 minutes
    for _, delay in result:
        assert 0 <= delay <= 300
    # Delays should be sorted (ascending)
    delays = [d for _, d in result]
    assert delays == sorted(delays)
