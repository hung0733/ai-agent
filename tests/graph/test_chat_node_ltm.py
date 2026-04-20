"""Tests for LTM retrieval in chat_node."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


@pytest.mark.asyncio
async def test_human_message_triggers_ltm_search():
    """測試 Human Message 觸發 LTM 檢索。"""
    from backend.graph.agent import chat_node

    state = {
        "messages": [HumanMessage(content="什麼是 LTM？")]
    }

    mock_model = AsyncMock()
    mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="測試回覆"))

    mock_stm_dao = AsyncMock()
    mock_stm_dao.list_recent_by_token_limit = AsyncMock(return_value=[])

    ltm_json_result = json.dumps([
        {"content": "LTM 是長期記憶系統", "sendDatetime": "2026-04-17T10:00:00"}
    ], ensure_ascii=False, indent=2)

    with patch("db.config.async_session_factory") as mock_session_factory:
        mock_db_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_db_session

        with patch("db.dao.short_term_mem_dao.ShortTermMemDAO", return_value=mock_stm_dao):
            with patch("backend.agent.ltm_search.search_ltm_for_chat", return_value=ltm_json_result):
                config = {
                    "configurable": {
                        "models": [mock_model],
                        "sys_prompt": "",
                        "think_mode": False,
                        "args": {},
                        "session_db_id": "test-session",
                    }
                }

                result = await chat_node(state, config)

                mock_model.ainvoke.assert_called_once()
                messages_sent = mock_model.ainvoke.call_args[0][0]
                ltm_messages = [m for m in messages_sent if "長期記憶檢索結果" in str(m.content)]
                assert len(ltm_messages) == 1
                assert "LTM 是長期記憶系統" in ltm_messages[0].content


@pytest.mark.asyncio
async def test_ai_message_does_not_trigger_ltm_search():
    """測試 AI Message 不觸發 LTM 檢索。"""
    from backend.graph.agent import chat_node

    state = {
        "messages": [AIMessage(content="這是 AI 的回覆")]
    }

    mock_model = AsyncMock()
    mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="測試回覆"))

    mock_stm_dao = AsyncMock()
    mock_stm_dao.list_recent_by_token_limit = AsyncMock(return_value=[])

    config = {
        "configurable": {
            "models": [mock_model],
            "sys_prompt": "",
            "think_mode": False,
            "args": {},
            "session_db_id": "test-session",
        }
    }

    with patch("db.config.async_session_factory") as mock_session_factory:
        mock_db_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_db_session

        with patch("db.dao.short_term_mem_dao.ShortTermMemDAO", return_value=mock_stm_dao):
            result = await chat_node(state, config)

            mock_model.ainvoke.assert_called_once()
            messages_sent = mock_model.ainvoke.call_args[0][0]
            ltm_messages = [m for m in messages_sent if "長期記憶檢索結果" in str(m.content)]
            assert len(ltm_messages) == 0


@pytest.mark.asyncio
async def test_ltm_search_failure_does_not_break_chat():
    """測試 LTM 搜索失敗不影響主流程。"""
    from backend.graph.agent import chat_node

    state = {
        "messages": [HumanMessage(content="什麼是 LTM？")]
    }

    mock_model = AsyncMock()
    mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="測試回覆"))

    mock_stm_dao = AsyncMock()
    mock_stm_dao.list_recent_by_token_limit = AsyncMock(return_value=[])

    config = {
        "configurable": {
            "models": [mock_model],
            "sys_prompt": "",
            "think_mode": False,
            "args": {},
            "session_db_id": "test-session",
        }
    }

    with patch("db.config.async_session_factory") as mock_session_factory:
        mock_db_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_db_session

        with patch("db.dao.short_term_mem_dao.ShortTermMemDAO", return_value=mock_stm_dao):
            with patch("backend.agent.ltm_search.search_ltm_for_chat", side_effect=Exception("LTM 失敗")):
                result = await chat_node(state, config)

                mock_model.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_ltm_message_order_is_before_last_message():
    """測試 LTM 結果放在日期時間之後、last_message 之前。"""
    from backend.graph.agent import chat_node

    state = {
        "messages": [
            HumanMessage(content="歷史消息1"),
            AIMessage(content="AI 回覆1"),
            HumanMessage(content="這是最後一條消息"),
        ]
    }

    mock_model = AsyncMock()
    mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="測試回覆"))

    mock_stm_dao = AsyncMock()
    mock_stm_dao.list_recent_by_token_limit = AsyncMock(return_value=[])

    ltm_json_result = json.dumps([
        {"content": "LTM 測試內容", "sendDatetime": "2026-04-17T10:00:00"}
    ], ensure_ascii=False, indent=2)

    with patch("db.config.async_session_factory") as mock_session_factory:
        mock_db_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_db_session

        with patch("db.dao.short_term_mem_dao.ShortTermMemDAO", return_value=mock_stm_dao):
            with patch("backend.agent.ltm_search.search_ltm_for_chat", return_value=ltm_json_result):
                config = {
                    "configurable": {
                        "models": [mock_model],
                        "sys_prompt": "",
                        "think_mode": False,
                        "args": {},
                        "session_db_id": "test-session",
                    }
                }

                result = await chat_node(state, config)

                messages_sent = mock_model.ainvoke.call_args[0][0]

                # 找到各類消息的索引
                ltm_indices = [i for i, m in enumerate(messages_sent) if "長期記憶檢索結果" in str(m.content)]
                datetime_indices = [i for i, m in enumerate(messages_sent) if "當前系統時間" in str(m.content)]
                last_message_indices = [i for i, m in enumerate(messages_sent) if m.content == "這是最後一條消息"]

                # 驗證 LTM 結果存在且只有一條
                assert len(ltm_indices) == 1, "應該有且只有一條 LTM 結果消息"

                # 驗證順序：日期時間 < LTM結果 < last_message
                last_datetime_idx = max(datetime_indices) if datetime_indices else -1
                ltm_idx = ltm_indices[0]
                last_message_idx = last_message_indices[0] if last_message_indices else -1

                assert last_datetime_idx < ltm_idx, "日期時間應該在 LTM 結果之前"
                assert ltm_idx < last_message_idx, "LTM 結果應該在 last_message 之前"


@pytest.mark.asyncio
async def test_ltm_search_returns_empty_json():
    """測試 LTM 無結果時不插入消息。"""
    from backend.graph.agent import chat_node

    state = {
        "messages": [HumanMessage(content="什麼是 LTM？")]
    }

    mock_model = AsyncMock()
    mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="測試回覆"))

    mock_stm_dao = AsyncMock()
    mock_stm_dao.list_recent_by_token_limit = AsyncMock(return_value=[])

    with patch("db.config.async_session_factory") as mock_session_factory:
        mock_db_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_db_session

        with patch("db.dao.short_term_mem_dao.ShortTermMemDAO", return_value=mock_stm_dao):
            with patch("backend.agent.ltm_search.search_ltm_for_chat", return_value=""):
                config = {
                    "configurable": {
                        "models": [mock_model],
                        "sys_prompt": "",
                        "think_mode": False,
                        "args": {},
                        "session_db_id": "test-session",
                    }
                }

                result = await chat_node(state, config)

                messages_sent = mock_model.ainvoke.call_args[0][0]
                ltm_messages = [m for m in messages_sent if "長期記憶檢索結果" in str(m.content)]
                assert len(ltm_messages) == 0


@pytest.mark.asyncio
async def test_get_existing_taxonomy_by_agent():
    """測試從 PostgreSQL 獲取現有 taxonomy。"""
    from backend.agent.ltm_search import _get_existing_taxonomy_by_agent

    mock_mem1 = MagicMock()
    mock_mem1.wing = "Project"
    mock_mem1.room = "Database"

    mock_mem2 = MagicMock()
    mock_mem2.wing = "Project"
    mock_mem2.room = "API"

    mock_mem3 = MagicMock()
    mock_mem3.wing = "Personal"
    mock_mem3.room = "Health"

    with patch("db.config.async_session_factory") as mock_session_factory:
        mock_db_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_db_session

        with patch("db.dao.long_term_mem_dao.LongTermMemDAO") as mock_dao:
            mock_dao.return_value.list_by_agent = AsyncMock(return_value=[mock_mem1, mock_mem2, mock_mem3])

            result = await _get_existing_taxonomy_by_agent(1)

            taxonomy = json.loads(result)
            assert "Project" in taxonomy
            assert "Database" in taxonomy["Project"]
            assert "API" in taxonomy["Project"]
            assert "Personal" in taxonomy
            assert "Health" in taxonomy["Personal"]
