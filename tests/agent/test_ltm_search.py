"""Tests for LTM search functionality."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


@pytest.mark.asyncio
async def test_search_ltm_no_results():
    """測試無搜索結果時返回空字符串和空列表。"""
    from backend.agent.ltm_search import search_ltm

    mock_client = AsyncMock()
    mock_client.search_semantic.return_value = []
    mock_client.search_keyword.return_value = []
    mock_client.search_structured.return_value = []

    result_text, result_points = await search_ltm("test query", agent_id=1, qdrant_client=mock_client)
    assert result_text == ""
    assert result_points == []


@pytest.mark.asyncio
async def test_search_ltm_with_results():
    """測試有搜索結果時返回格式化的記憶和原始結果。"""
    from backend.agent.ltm_search import search_ltm

    mock_point = MagicMock()
    mock_point.payload = {
        "wing": "Personal",
        "room": "Health",
        "content": "User likes running",
        "keywords": ["running", "fitness"],
        "create_dt": "2026-04-17T10:00:00",
    }

    mock_client = AsyncMock()
    mock_client.search_semantic.return_value = [mock_point]
    mock_client.search_keyword.return_value = []
    mock_client.search_structured.return_value = []

    result_text, result_points = await search_ltm("running", agent_id=1, qdrant_client=mock_client)
    assert "Personal" in result_text
    assert "Health" in result_text
    assert "User likes running" in result_text
    assert len(result_points) == 1
    assert result_points[0].payload["content"] == "User likes running"


@pytest.mark.asyncio
async def test_search_ltm_with_wing_room():
    """測試帶 wing/room 參數的搜索。"""
    from backend.agent.ltm_search import search_ltm

    mock_point = MagicMock()
    mock_point.payload = {
        "wing": "Project",
        "room": "Database",
        "content": "User uses PostgreSQL",
        "keywords": ["PostgreSQL"],
        "create_dt": "2026-04-17T11:00:00",
    }

    mock_client = AsyncMock()
    mock_client.search_semantic.return_value = []
    mock_client.search_keyword.return_value = []
    mock_client.search_structured.return_value = [mock_point]

    result_text, result_points = await search_ltm(
        "database",
        agent_id=1,
        qdrant_client=mock_client,
        wing="Project",
        room="Database",
    )
    assert "Project" in result_text
    assert "Database" in result_text
    assert len(result_points) == 1


@pytest.mark.asyncio
async def test_format_ltm_results():
    """測試格式化 LTM 搜索結果。"""
    from backend.agent.ltm_search import format_ltm_results

    points = [
        MagicMock(
            payload={
                "wing": "Personal",
                "room": "Health",
                "content": "User likes running",
                "keywords": ["running"],
                "create_dt": "2026-04-17T10:00:00",
            }
        ),
        MagicMock(
            payload={
                "wing": "Project_JARVIS",
                "room": "Database",
                "content": "User uses PostgreSQL",
                "keywords": ["PostgreSQL"],
                "create_dt": "2026-04-17T11:00:00",
            }
        ),
    ]

    result = format_ltm_results(points)
    assert "Personal" in result
    assert "Health" in result
    assert "User likes running" in result
    assert "Project_JARVIS" in result
    assert "Database" in result
    assert "User uses PostgreSQL" in result


@pytest.mark.asyncio
async def test_format_ltm_results_as_json():
    """測試格式化 LTM 結果為 JSON 格式。"""
    from backend.agent.ltm_search import format_ltm_results_as_json

    points = [
        MagicMock(
            payload={
                "content": "User likes running",
                "create_dt": "2026-04-17T10:00:00",
            }
        ),
        MagicMock(
            payload={
                "content": "User uses PostgreSQL",
                "record_dt": "2026-04-17T11:00:00",
            }
        ),
    ]

    result = format_ltm_results_as_json(points)
    assert len(result) == 2
    assert result[0]["content"] == "User likes running"
    assert result[0]["sendDatetime"] == "2026-04-17T10:00:00"
    assert result[1]["content"] == "User uses PostgreSQL"
    assert result[1]["sendDatetime"] == "2026-04-17T11:00:00"


@pytest.mark.asyncio
async def test_search_ltm_error_returns_empty():
    """測試搜索出錯時返回空字符串和空列表。"""
    from backend.agent.ltm_search import search_ltm

    mock_client = AsyncMock()
    mock_client.search_semantic.side_effect = Exception("Connection failed")

    result_text, result_points = await search_ltm("test", agent_id=1, qdrant_client=mock_client)
    assert result_text == ""
    assert result_points == []


@pytest.mark.asyncio
async def test_merge_and_deduplicate():
    """測試合併並去重搜索結果。"""
    from backend.agent.ltm_search import _merge_and_deduplicate

    point1 = MagicMock(id="uuid-1", payload={"content": "A"})
    point2 = MagicMock(id="uuid-2", payload={"content": "B"})
    point3 = MagicMock(id="uuid-1", payload={"content": "A duplicate"})

    merged = _merge_and_deduplicate([point1], [point2], [point3])
    assert len(merged) == 2
    assert merged[0].id == "uuid-1"
    assert merged[1].id == "uuid-2"


def test_format_ltm_results_empty():
    """測試空結果返回空字符串。"""
    from backend.agent.ltm_search import format_ltm_results

    assert format_ltm_results([]) == ""


def test_format_ltm_results_as_json_empty():
    """測試空結果返回空列表。"""
    from backend.agent.ltm_search import format_ltm_results_as_json

    assert format_ltm_results_as_json([]) == []
