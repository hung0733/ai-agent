"""Tests for Qdrant client."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client."""
    with patch("backend.vector.qdrant_client.QdrantClient") as mock:
        yield mock


def test_qdrant_client_initialization():
    """測試 QdrantClient 初始化。"""
    from backend.vector.qdrant_client import QdrantClient
    import os

    client = QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", "6333")),
        api_key=os.getenv("QDRANT_API_KEY"),
    )
    assert client.host == os.getenv("QDRANT_HOST", "localhost")
    assert client.port == int(os.getenv("QDRANT_PORT", "6333"))


@pytest.mark.asyncio
async def test_upsert_points_success():
    """測試成功寫入向量點。"""
    from backend.vector.qdrant_client import QdrantClient

    mock_client = AsyncMock()
    mock_client.upsert.return_value = {"status": "ok"}

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
