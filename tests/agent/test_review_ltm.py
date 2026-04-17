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

    result = await summary.review_ltm(agent_id=1)
    assert result == {"processed": 0, "errors": 0}


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
