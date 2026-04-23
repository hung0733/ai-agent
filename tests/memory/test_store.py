"""MemoryStore tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Add backend to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from memory.store import MemoryStore


@pytest.fixture
def mock_session_factory():
    """模擬數據庫 session factory。"""
    with patch("memory.store.async_session_factory") as mock:
        yield mock


@pytest.fixture
def memory_store():
    """創建 MemoryStore 實例。"""
    return MemoryStore(session_db_id=123)


def test_memory_store_initialization(memory_store):
    """測試 MemoryStore 初始化。"""
    assert memory_store._session_db_id == 123
    assert memory_store._cache.is_initialized == False
    assert memory_store._pending_commits == {}


@pytest.mark.asyncio
async def test_prepare_messages_without_ltm(memory_store, mock_session_factory):
    """測試 prepare_messages（非 HumanMessage，唔觸發 LTM）。"""
    # 模擬 DB 加載
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    
    with patch.object(memory_store, '_load_from_db', new_callable=AsyncMock):
        message = AIMessage(content="AI response")
        messages = await memory_store.prepare_messages(step_id="step_1", message=message)
        
        # 應該包含：STM + Old Messages + Current Time + Last Message（無 LTM）
        assert len(messages) >= 2  # 至少有时间消息同最后一条消息
        assert messages[-1] == message


@pytest.mark.asyncio
async def test_commit_messages(memory_store):
    """測試 commit_messages 基本功能。"""
    # 先準備 pending commits
    memory_store._pending_commits["step_1"] = {
        "ltm_message": None,
        "last_message": HumanMessage(content="Hello"),
    }
    
    # 模擬 DB 操作
    with patch("memory.store.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        
        mock_dao = AsyncMock()
        mock_dao.count_by_step = AsyncMock(return_value=0)
        mock_dao.get_last_by_step = AsyncMock(return_value=None)
        mock_dao.create_from_dto = AsyncMock()
        
        with patch("memory.store.AgentMsgHistDAO", return_value=mock_dao):
            await memory_store.commit_messages(step_id="step_1", response=AIMessage(content="Hi there"))
            
            # 驗證 DAO 被調用
            assert mock_dao.create_from_dto.called


@pytest.mark.asyncio
async def test_commit_messages_with_tool_result(memory_store):
    """測試 commit_messages 處理 ToolMessage（Tool Result）。"""
    memory_store._pending_commits["step_2"] = {
        "ltm_message": None,
        "last_message": HumanMessage(content="Run tool"),
    }
    
    with patch("memory.store.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        
        mock_dao = AsyncMock()
        mock_dao.count_by_step = AsyncMock(return_value=0)
        mock_dao.get_last_by_step = AsyncMock(return_value=None)
        mock_dao.create_from_dto = AsyncMock()
        
        with patch("memory.store.AgentMsgHistDAO", return_value=mock_dao):
            tool_response = ToolMessage(content="Tool output", tool_call_id="call_123")
            await memory_store.commit_messages(step_id="step_2", response=tool_response)
            
            # 驗證 DAO 被調用
            assert mock_dao.create_from_dto.called


def test_update_after_summary(memory_store):
    """測試 update_after_summary 清理邏輯。"""
    # 添加一些 old messages
    memory_store._cache.old_messages = [
        ("step_1", HumanMessage(content="Msg 1")),
        ("step_2", HumanMessage(content="Msg 2")),
        ("step_3", HumanMessage(content="Msg 3")),
    ]
    
    # 模擬 STM 加載
    with patch("memory.store.async_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        
        with patch("memory.store.ShortTermMemDAO") as mock_stm_dao:
            mock_stm_dao_instance = AsyncMock()
            mock_stm_dao_instance.list_recent_by_token_limit = AsyncMock(return_value=[])
            mock_stm_dao.return_value = mock_stm_dao_instance
            
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                memory_store.update_after_summary(["step_1", "step_2"])
            )
    
    # 驗證 step_1 同 step_2 被刪除，只保留 step_3
    assert len(memory_store._cache.old_messages) == 1
    assert memory_store._cache.old_messages[0][0] == "step_3"
