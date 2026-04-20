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

    mock_session = MagicMock()
    mock_session.recv_agent_id = 1

    mock_routing_llm = AsyncMock()
    mock_routing_llm.ainvoke.return_value.content = '{"domain_wing": "Project", "topic_room": "Database", "keywords": ["LTM", "Database"]}'

    mock_qdrant_client = AsyncMock()
    mock_qdrant_client.ensure_collection = AsyncMock()

    mock_point = MagicMock()
    mock_point.payload = {
        "content": "LTM 是長期記憶系統",
        "create_dt": "2026-04-17T10:00:00",
    }

    mock_model = AsyncMock()
    mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="測試回覆"))

    mock_stm_dao = AsyncMock()
    mock_stm_dao.list_recent_by_token_limit = AsyncMock(return_value=[])

    with patch("db.config.async_session_factory") as mock_session_factory:
        mock_db_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_db_session

        with patch("db.dao.session_dao.SessionDAO") as mock_session_dao:
            mock_session_dao.return_value.get_by_id = AsyncMock(return_value=mock_session)

            with patch("db.dao.short_term_mem_dao.ShortTermMemDAO", return_value=mock_stm_dao):
                with patch("backend.graph.agent._get_routing_llm", return_value=mock_routing_llm):
                    with patch("backend.vector.qdrant_client.QdrantClient", return_value=mock_qdrant_client):
                        with patch("backend.graph.agent._get_existing_taxonomy_by_agent", return_value="{}"):
                            with patch("backend.agent.ltm_search.search_ltm", return_value=("result", [mock_point])):
                                with patch("backend.graph.agent._get_embedding_model") as mock_embedding:
                                    mock_embedding.return_value.aembed_query = AsyncMock(return_value=[0.1, 0.2])

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

                                    mock_routing_llm.ainvoke.assert_called_once()


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

        with patch("db.dao.session_dao.SessionDAO") as mock_session_dao:
            mock_session_dao.return_value.get_by_id = AsyncMock(return_value=MagicMock(recv_agent_id=1))

            with patch("db.dao.short_term_mem_dao.ShortTermMemDAO", return_value=mock_stm_dao):
                with patch("backend.graph.agent._get_routing_llm", side_effect=Exception("ROUTING_LLM 失敗")):
                    result = await chat_node(state, config)

                    mock_model.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_get_existing_taxonomy_by_agent():
    """測試從 PostgreSQL 獲取現有 taxonomy。"""
    from backend.graph.agent import _get_existing_taxonomy_by_agent

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
