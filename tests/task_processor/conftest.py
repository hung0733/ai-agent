"""Test fixtures for TaskProcessor tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_task():
    task = MagicMock()
    task.id = 1
    task.task_type = "method"
    task.parameters = {"method_name": "test"}
    task.status = "pending"
    task.agent_id = 100
    task.created_at = MagicMock()
    return task


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.id = 100
    agent.agent_id = "test-agent-001"
    agent.status = "idle"
    return agent


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def processor():
    from task_processor.processor import TaskProcessor
    return TaskProcessor(max_concurrent=1)
