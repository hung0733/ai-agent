"""Tests for Qdrant client."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


@pytest.fixture
def mock_async_qdrant_client():
    """Mock the underlying AsyncQdrantClient class."""
    with patch("backend.vector.qdrant_client.AsyncQdrantClient") as mock:
        mock_instance = AsyncMock()
        mock.return_value = mock_instance
        yield mock, mock_instance


def test_qdrant_client_initialization(mock_async_qdrant_client):
    """測試 QdrantClient 初始化。"""
    from backend.vector.qdrant_client import QdrantClient

    mock_cls, mock_instance = mock_async_qdrant_client

    client = QdrantClient(
        host="test-host",
        port=6334,
        api_key="test-key",
        collection_name="test_collection",
    )

    assert client.host == "test-host"
    assert client.port == 6334
    assert client.api_key == "test-key"
    assert client.collection_name == "test_collection"

    mock_cls.assert_called_once_with(host="test-host", port=6334, api_key="test-key")


@pytest.mark.asyncio
async def test_upsert_points_success():
    """測試成功寫入向量點。"""
    from backend.vector.qdrant_client import QdrantClient
    from qdrant_client import models

    mock_client = AsyncMock()
    mock_result = MagicMock()
    mock_result.status = models.UpdateStatus.COMPLETED
    mock_client.upsert.return_value = mock_result

    client = QdrantClient.__new__(QdrantClient)
    client.client = mock_client
    client.collection_name = "test_collection"

    points = [
        {
            "id": 1,
            "vector": [0.1, 0.2, 0.3],
            "payload": {
                "agent_id": 1,
                "wing": "Personal",
                "room": "Health",
                "content": "Test memory",
                "keywords": ["health", "fitness"],
                "create_dt": "2026-04-17T10:00:00",
                "session_id": 1,
            },
        }
    ]

    result = await client.upsert_points(points)
    assert result["status"] == "ok"
    assert result["count"] == 1
    mock_client.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_search_semantic():
    """測試語義搜索。"""
    from backend.vector.qdrant_client import QdrantClient

    mock_client = AsyncMock()
    mock_results = [
        MagicMock(
            id=1,
            score=0.95,
            payload={
                "agent_id": 1,
                "wing": "Personal",
                "room": "Health",
                "content": "Test memory",
                "keywords": ["health"],
                "create_dt": "2026-04-17T10:00:00",
                "session_id": 1,
            },
        )
    ]
    mock_client.query_points.return_value.points = mock_results

    client = QdrantClient.__new__(QdrantClient)
    client.client = mock_client
    client.collection_name = "test_collection"

    results = await client.search_semantic([0.1, 0.2, 0.3], top_k=5)
    assert len(results) == 1
    assert results[0].score == 0.95


@pytest.mark.asyncio
async def test_search_keyword():
    """測試關鍵字搜索。"""
    from backend.vector.qdrant_client import QdrantClient

    mock_client = AsyncMock()
    mock_results = [
        MagicMock(
            id=2,
            score=1.0,
            payload={
                "agent_id": 1,
                "wing": "Personal",
                "room": "Health",
                "content": "Test memory",
                "keywords": ["health"],
                "create_dt": "2026-04-17T10:00:00",
                "session_id": 1,
            },
        )
    ]
    mock_client.query_points.return_value.points = mock_results

    client = QdrantClient.__new__(QdrantClient)
    client.client = mock_client
    client.collection_name = "test_collection"

    results = await client.search_keyword("health", top_k=5)
    assert len(results) == 1
    assert results[0].id == 2
    mock_client.query_points.assert_called_once()


@pytest.mark.asyncio
async def test_search_keyword_with_agent_id():
    """測試帶 agent_id 過濾的關鍵字搜索。"""
    from backend.vector.qdrant_client import QdrantClient

    mock_client = AsyncMock()
    mock_client.query_points.return_value.points = []

    client = QdrantClient.__new__(QdrantClient)
    client.client = mock_client
    client.collection_name = "test_collection"

    results = await client.search_keyword("fitness", top_k=3, agent_id=1)
    assert len(results) == 0
    call_kwargs = mock_client.query_points.call_args[1]
    assert call_kwargs["query_filter"] is not None


@pytest.mark.asyncio
async def test_search_structured_with_wing():
    """測試帶 wing 過濾的结构化搜索。"""
    from backend.vector.qdrant_client import QdrantClient

    mock_client = AsyncMock()
    mock_results = [
        MagicMock(
            id=3,
            payload={"wing": "Personal", "content": "Test"},
        )
    ]
    mock_client.query_points.return_value.points = mock_results

    client = QdrantClient.__new__(QdrantClient)
    client.client = mock_client
    client.collection_name = "test_collection"

    results = await client.search_structured(wing="Personal", top_k=5)
    assert len(results) == 1
    assert results[0].payload["wing"] == "Personal"


@pytest.mark.asyncio
async def test_search_structured_with_multiple_filters():
    """測試帶多個過濾條件的结构化搜索。"""
    from backend.vector.qdrant_client import QdrantClient

    mock_client = AsyncMock()
    mock_client.query_points.return_value.points = []

    client = QdrantClient.__new__(QdrantClient)
    client.client = mock_client
    client.collection_name = "test_collection"

    results = await client.search_structured(
        wing="Personal", room="Health", agent_id=1, top_k=10,
    )
    assert len(results) == 0
    call_kwargs = mock_client.query_points.call_args[1]
    assert call_kwargs["limit"] == 10


@pytest.mark.asyncio
async def test_search_structured_no_conditions_returns_empty():
    """測試未提供任何過濾條件時返回空列表。"""
    from backend.vector.qdrant_client import QdrantClient

    mock_client = AsyncMock()

    client = QdrantClient.__new__(QdrantClient)
    client.client = mock_client
    client.collection_name = "test_collection"

    results = await client.search_structured()
    assert results == []
    mock_client.query_points.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_points_checks_status():
    """測試 upsert_points 檢查返回狀態。"""
    from backend.vector.qdrant_client import QdrantClient
    from qdrant_client import models

    mock_client = AsyncMock()
    mock_result = MagicMock()
    mock_result.status = models.UpdateStatus.ACKNOWLEDGED
    mock_client.upsert.return_value = mock_result

    client = QdrantClient.__new__(QdrantClient)
    client.client = mock_client
    client.collection_name = "test_collection"

    points = [{"id": 1, "vector": [0.1], "payload": {}}]

    with pytest.raises(RuntimeError, match="Qdrant upsert 失敗"):
        await client.upsert_points(points)


@pytest.mark.asyncio
async def test_upsert_points_propagates_exception():
    """測試 upsert_points 傳播網絡異常。"""
    from backend.vector.qdrant_client import QdrantClient

    mock_client = AsyncMock()
    mock_client.upsert.side_effect = ConnectionError("network error")

    client = QdrantClient.__new__(QdrantClient)
    client.client = mock_client
    client.collection_name = "test_collection"

    points = [{"id": 1, "vector": [0.1], "payload": {}}]

    with pytest.raises(ConnectionError, match="network error"):
        await client.upsert_points(points)
