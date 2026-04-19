"""Tests for TaskProcessor handler registry."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from task_processor.handlers import (
    _HANDLERS,
    get_handler,
    method_handler,
    register_handler,
    register_method_handlers,
)


@pytest.fixture(autouse=True)
def reset_handlers():
    """重置 _HANDLERS 以避免測試間互相影響。"""
    _HANDLERS.clear()
    yield


@pytest.fixture
def mock_task():
    task = MagicMock()
    task.id = 1
    task.task_type = "method"
    task.parameters = {"method_name": "test", "args": [1, 2, 3]}
    task.status = "pending"
    task.return_message = None
    return task


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.id = 1
    agent.agent_id = "test-agent-001"
    agent.status = "idle"
    return agent


@pytest.fixture
def mock_session():
    return AsyncMock()


def test_register_and_get_handler():
    handler = AsyncMock()
    register_handler("test_type", handler)
    assert get_handler("test_type") is handler


def test_get_handler_not_found():
    assert get_handler("nonexistent") is None


def test_register_method_handlers():
    register_method_handlers()
    assert get_handler("method") is method_handler


@pytest.mark.asyncio
async def test_method_handler_sets_completed(mock_task, mock_agent, mock_session):
    await method_handler(mock_task, mock_agent, mock_session)

    assert mock_task.status == "completed"
    assert mock_task.return_message is not None
    assert mock_task.return_message["result"] == "method executed"
    assert mock_task.return_message["parameters"] == mock_task.parameters
    mock_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_method_handler_with_empty_params(mock_task, mock_agent, mock_session):
    mock_task.parameters = None

    await method_handler(mock_task, mock_agent, mock_session)

    assert mock_task.status == "completed"
    assert mock_task.return_message["parameters"] == {}
