"""Tests for TaskProcessor handler registry."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_method_handler_function(mock_agent, mock_session):
    """測試直接函數調用：/agent/summary@review_ltm"""
    mock_task = MagicMock()
    mock_task.id = 1
    mock_task.content = "/agent/summary@review_ltm"
    mock_task.status = "pending"
    mock_task.return_message = None

    expected_result = {"processed": 5, "errors": 0, "memories": []}

    with patch("task_processor.handlers.importlib.import_module") as mock_import:
        mock_module = MagicMock()
        mock_review_ltm = AsyncMock(return_value=expected_result)
        mock_module.review_ltm = mock_review_ltm
        mock_import.return_value = mock_module

        await method_handler(mock_task, mock_agent, mock_session)

        mock_import.assert_called_once_with("backend.agent.summary")
        mock_review_ltm.assert_awaited_once_with(agent_id="test-agent-001")
        assert mock_task.status == "completed"
        assert mock_task.return_message == expected_result
        mock_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_method_handler_class_method(mock_agent, mock_session):
    """測試類方法調用：/agent/summary@SummaryHelper.review_ltm"""
    mock_task = MagicMock()
    mock_task.id = 1
    mock_task.content = "/agent/summary@SummaryHelper.review_ltm"
    mock_task.status = "pending"
    mock_task.return_message = None

    expected_result = {"status": "ok", "count": 10}

    with patch("task_processor.handlers.importlib.import_module") as mock_import:
        mock_module = MagicMock()
        mock_method = AsyncMock(return_value=expected_result)
        mock_class = MagicMock()
        mock_class.review_ltm = mock_method
        mock_module.SummaryHelper = mock_class
        mock_import.return_value = mock_module

        await method_handler(mock_task, mock_agent, mock_session)

        mock_import.assert_called_once_with("backend.agent.summary")
        mock_method.assert_awaited_once_with(agent_id="test-agent-001")
        assert mock_task.status == "completed"
        assert mock_task.return_message == expected_result


@pytest.mark.asyncio
async def test_method_handler_missing_at_separator(mock_agent, mock_session):
    """測試缺少 @ 分隔符"""
    mock_task = MagicMock()
    mock_task.id = 1
    mock_task.content = "/agent/summary/review_ltm"
    mock_task.status = "pending"

    with pytest.raises(ValueError, match="缺少 '@' 分隔符"):
        await method_handler(mock_task, mock_agent, mock_session)


@pytest.mark.asyncio
async def test_method_handler_module_not_found(mock_agent, mock_session):
    """測試 module 不存在"""
    mock_task = MagicMock()
    mock_task.id = 1
    mock_task.content = "/nonexistent/module@method"
    mock_task.status = "pending"

    with patch("task_processor.handlers.importlib.import_module") as mock_import:
        mock_import.side_effect = ImportError("No module named 'backend.nonexistent'")

        with pytest.raises(ValueError, match="無法導入 module"):
            await method_handler(mock_task, mock_agent, mock_session)


@pytest.mark.asyncio
async def test_method_handler_function_not_found(mock_agent, mock_session):
    """測試函數不存在"""
    mock_task = MagicMock()
    mock_task.id = 1
    mock_task.content = "/agent/summary@nonexistent_function"
    mock_task.status = "pending"

    with patch("task_processor.handlers.importlib.import_module") as mock_import:
        mock_module = MagicMock()
        del mock_module.nonexistent_function
        mock_import.return_value = mock_module

        with pytest.raises(ValueError, match="無法獲取函數"):
            await method_handler(mock_task, mock_agent, mock_session)


@pytest.mark.asyncio
async def test_method_handler_class_not_found(mock_agent, mock_session):
    """測試類不存在"""
    mock_task = MagicMock()
    mock_task.id = 1
    mock_task.content = "/agent/summary@NonExistentClass.method"
    mock_task.status = "pending"

    with patch("task_processor.handlers.importlib.import_module") as mock_import:
        # 使用 spec 限制 mock 只暴露特定屬性，這樣訪問不存在的屬性會拋 AttributeError
        mock_module = MagicMock(spec=['SomeOtherClass'])
        mock_import.return_value = mock_module

        with pytest.raises(ValueError, match="無法獲取方法"):
            await method_handler(mock_task, mock_agent, mock_session)


@pytest.mark.asyncio
async def test_method_handler_method_not_found(mock_agent, mock_session):
    """測試類方法不存在"""
    mock_task = MagicMock()
    mock_task.id = 1
    mock_task.content = "/agent/summary@SummaryHelper.nonexistent_method"
    mock_task.status = "pending"

    with patch("task_processor.handlers.importlib.import_module") as mock_import:
        mock_module = MagicMock()
        mock_class = MagicMock()
        del mock_class.nonexistent_method
        mock_module.SummaryHelper = mock_class
        mock_import.return_value = mock_module

        with pytest.raises(ValueError, match="無法獲取方法"):
            await method_handler(mock_task, mock_agent, mock_session)


@pytest.mark.asyncio
async def test_method_handler_invalid_return_type(mock_agent, mock_session):
    """測試返回值不是 dict"""
    mock_task = MagicMock()
    mock_task.id = 1
    mock_task.content = "/agent/summary@review_ltm"
    mock_task.status = "pending"

    with patch("task_processor.handlers.importlib.import_module") as mock_import:
        mock_module = MagicMock()
        mock_review_ltm = AsyncMock(return_value="not a dict")
        mock_module.review_ltm = mock_review_ltm
        mock_import.return_value = mock_module

        with pytest.raises(ValueError, match="返回值不是 dict"):
            await method_handler(mock_task, mock_agent, mock_session)


@pytest.mark.asyncio
async def test_method_handler_method_exception(mock_agent, mock_session):
    """測試方法執行異常"""
    mock_task = MagicMock()
    mock_task.id = 1
    mock_task.content = "/agent/summary@review_ltm"
    mock_task.status = "pending"

    with patch("task_processor.handlers.importlib.import_module") as mock_import:
        mock_module = MagicMock()
        mock_review_ltm = AsyncMock(side_effect=RuntimeError("Connection failed"))
        mock_module.review_ltm = mock_review_ltm
        mock_import.return_value = mock_module

        with pytest.raises(RuntimeError, match="Connection failed"):
            await method_handler(mock_task, mock_agent, mock_session)


@pytest.mark.asyncio
async def test_method_handler_with_complex_path(mock_agent, mock_session):
    """測試複雜路徑：/db/dao/task_dao@TaskDAO.get_by_id"""
    mock_task = MagicMock()
    mock_task.id = 1
    mock_task.content = "/db/dao/task_dao@TaskDAO.get_by_id"
    mock_task.status = "pending"

    expected_result = {"id": 1, "name": "test"}

    with patch("task_processor.handlers.importlib.import_module") as mock_import:
        mock_module = MagicMock()
        mock_method = AsyncMock(return_value=expected_result)
        mock_class = MagicMock()
        mock_class.get_by_id = mock_method
        mock_module.TaskDAO = mock_class
        mock_import.return_value = mock_module

        await method_handler(mock_task, mock_agent, mock_session)

        mock_import.assert_called_once_with("backend.db.dao.task_dao")
        mock_method.assert_awaited_once_with(agent_id="test-agent-001")
        assert mock_task.status == "completed"
        assert mock_task.return_message == expected_result
