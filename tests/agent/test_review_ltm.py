"""Tests for LTM review functionality."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


@pytest.mark.asyncio
async def test_review_ltm_no_records(monkeypatch: pytest.MonkeyPatch):
    """測試無未總結記錄時直接返回。"""
    from backend.agent import summary

    class FakeSessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeHistDAO:
        def __init__(self, session: object) -> None:
            pass

        async def list_unsummarized_for_ltm(self) -> list:
            return []

    monkeypatch.setattr(summary, "async_session_factory", FakeSessionContext)
    monkeypatch.setattr(summary, "AgentMsgHistDAO", FakeHistDAO)

    result = await summary.review_ltm(agent_id=1, model=MagicMock())
    assert result == {"processed": 0, "errors": 0, "memories": []}


@pytest.mark.asyncio
async def test_split_records_by_token_limit():
    """測試按 token 限制分割記錄。"""
    from backend.agent.summary import _split_records_by_token_limit

    records = [
        SimpleNamespace(token=10000),
        SimpleNamespace(token=10000),
        SimpleNamespace(token=10000),
        SimpleNamespace(token=5000),
    ]

    batches = _split_records_by_token_limit(records, limit=25000)
    assert len(batches) == 2
    assert sum(r.token for r in batches[0]) <= 25000
    assert sum(r.token for r in batches[1]) <= 25000


@pytest.mark.asyncio
async def test_group_records_by_session_date():
    """測試按 session_id + date 分組。"""
    from backend.agent.summary import _group_records_by_session_date

    records = [
        SimpleNamespace(
            session_id=1,
            create_dt=datetime(2026, 4, 17, 10, 0, 0),
            token=100,
        ),
        SimpleNamespace(
            session_id=1,
            create_dt=datetime(2026, 4, 17, 11, 0, 0),
            token=200,
        ),
        SimpleNamespace(
            session_id=1,
            create_dt=datetime(2026, 4, 18, 10, 0, 0),
            token=300,
        ),
        SimpleNamespace(
            session_id=2,
            create_dt=datetime(2026, 4, 17, 10, 0, 0),
            token=400,
        ),
    ]

    groups = _group_records_by_session_date(records)
    assert len(groups) == 3  # (1, 2026-04-17), (1, 2026-04-18), (2, 2026-04-17)


@pytest.mark.asyncio
async def test_review_ltm_marks_correct_ids_on_success(monkeypatch: pytest.MonkeyPatch):
    """測試成功處理時，mark_records_as_ltm_summarized 被正確調用。"""
    from backend.agent import summary

    class FakeSessionContext:
        async def __aenter__(self) -> object:
            return SimpleNamespace(commit=AsyncMock())

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeHistDAO:
        def __init__(self, session: object) -> None:
            self.marked_ids = None

        async def list_unsummarized_for_ltm(self) -> list:
            return [
                SimpleNamespace(id=1, session_id=1, create_dt=datetime(2026, 4, 17, 10, 0, 0), token=100),
                SimpleNamespace(id=2, session_id=1, create_dt=datetime(2026, 4, 17, 11, 0, 0), token=200),
                SimpleNamespace(id=3, session_id=1, create_dt=datetime(2026, 4, 18, 10, 0, 0), token=300),
            ]

        async def mark_records_as_ltm_summarized(self, ids: list) -> None:
            self.marked_ids = ids

    class FakeLtmDAO:
        def __init__(self, session: object) -> None:
            pass

    class FakeQdrantClient:
        async def ensure_collection(self, vector_size: int) -> None:
            pass

    fake_hist_dao = FakeHistDAO(None)
    batch_call_count = 0

    async def fake_process_ltm_batch(**kwargs) -> list:
        nonlocal batch_call_count
        batch_call_count += 1
        # 每個 batch 返回 1 條 memory
        return [
            {"wing": "Project_JARVIS", "room": "Database", "content": f"Test memory {batch_call_count}"},
        ]

    monkeypatch.setattr(summary, "async_session_factory", FakeSessionContext)
    monkeypatch.setattr(summary, "AgentMsgHistDAO", lambda session: fake_hist_dao)
    monkeypatch.setattr(summary, "LongTermMemDAO", FakeLtmDAO)
    monkeypatch.setattr(summary, "QdrantClient", FakeQdrantClient)
    monkeypatch.setattr(summary, "_process_ltm_batch", fake_process_ltm_batch)

    result = await summary.review_ltm(agent_id=1, model=MagicMock())

    assert result["processed"] == 3
    assert result["errors"] == 0
    assert fake_hist_dao.marked_ids == [1, 2, 3]
    assert len(result["memories"]) == 2


@pytest.mark.asyncio
async def test_review_ltm_error_handling(monkeypatch: pytest.MonkeyPatch):
    """測試批次處理失敗時的錯誤處理。"""
    from backend.agent import summary

    class FakeSessionContext:
        async def __aenter__(self) -> object:
            return SimpleNamespace(commit=AsyncMock())

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeHistDAO:
        def __init__(self, session: object) -> None:
            self.marked_ids = None

        async def list_unsummarized_for_ltm(self) -> list:
            return [
                SimpleNamespace(id=1, session_id=1, create_dt=datetime(2026, 4, 17, 10, 0, 0), token=100),
                SimpleNamespace(id=2, session_id=1, create_dt=datetime(2026, 4, 17, 11, 0, 0), token=200),
            ]

        async def mark_records_as_ltm_summarized(self, ids: list) -> None:
            self.marked_ids = ids

    class FakeLtmDAO:
        def __init__(self, session: object) -> None:
            pass

    class FakeQdrantClient:
        async def ensure_collection(self, vector_size: int) -> None:
            pass

    fake_hist_dao = FakeHistDAO(None)

    async def fake_process_ltm_batch(**kwargs) -> list:
        return []

    monkeypatch.setattr(summary, "async_session_factory", FakeSessionContext)
    monkeypatch.setattr(summary, "AgentMsgHistDAO", lambda session: fake_hist_dao)
    monkeypatch.setattr(summary, "LongTermMemDAO", FakeLtmDAO)
    monkeypatch.setattr(summary, "QdrantClient", FakeQdrantClient)
    monkeypatch.setattr(summary, "_process_ltm_batch", fake_process_ltm_batch)

    result = await summary.review_ltm(agent_id=1, model=MagicMock())

    assert result["processed"] == 0
    assert result["errors"] == 2
    assert fake_hist_dao.marked_ids is None
    assert result["memories"] == []


@pytest.mark.asyncio
async def test_review_ltm_partial_success(monkeypatch: pytest.MonkeyPatch):
    """測試部分批次成功時的 ID 追蹤。"""
    from backend.agent import summary

    class FakeSessionContext:
        async def __aenter__(self) -> object:
            return SimpleNamespace(commit=AsyncMock())

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeHistDAO:
        def __init__(self, session: object) -> None:
            self.marked_ids = None

        async def list_unsummarized_for_ltm(self) -> list:
            return [
                SimpleNamespace(id=10, session_id=1, create_dt=datetime(2026, 4, 17, 10, 0, 0), token=100),
                SimpleNamespace(id=20, session_id=1, create_dt=datetime(2026, 4, 17, 11, 0, 0), token=200),
                SimpleNamespace(id=30, session_id=1, create_dt=datetime(2026, 4, 18, 10, 0, 0), token=300),
            ]

        async def mark_records_as_ltm_summarized(self, ids: list) -> None:
            self.marked_ids = ids

    class FakeLtmDAO:
        def __init__(self, session: object) -> None:
            pass

    class FakeQdrantClient:
        async def ensure_collection(self, vector_size: int) -> None:
            pass

    fake_hist_dao = FakeHistDAO(None)
    call_count = 0

    async def fake_process_ltm_batch(**kwargs) -> list:
        nonlocal call_count
        call_count += 1
        # 只有第一次調用（第一個 batch）成功返回 memories
        if call_count == 1:
            return [
                {"wing": "Project_JARVIS", "room": "Database", "content": "Memory batch 1"},
            ]
        return []

    monkeypatch.setattr(summary, "async_session_factory", FakeSessionContext)
    monkeypatch.setattr(summary, "AgentMsgHistDAO", lambda session: fake_hist_dao)
    monkeypatch.setattr(summary, "LongTermMemDAO", FakeLtmDAO)
    monkeypatch.setattr(summary, "QdrantClient", FakeQdrantClient)
    monkeypatch.setattr(summary, "_process_ltm_batch", fake_process_ltm_batch)

    result = await summary.review_ltm(agent_id=1, model=MagicMock())

    assert result["processed"] == 2
    assert result["errors"] == 1
    assert fake_hist_dao.marked_ids is not None
    assert len(fake_hist_dao.marked_ids) == 2
    assert len(result["memories"]) == 1
