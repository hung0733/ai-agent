"""Tests for STM review workflow."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


def test_format_conversation() -> None:
    """測試對話格式化。"""
    from agent.summary import _format_conversation

    record1 = SimpleNamespace(
        create_dt=datetime(2025, 1, 12, 11, 11, 12),
        sender="User",
        content="Hello",
    )
    record2 = SimpleNamespace(
        create_dt=datetime(2025, 1, 12, 11, 12, 0),
        sender="Agent",
        content="Hi there!",
    )

    result = _format_conversation([record1, record2])
    expected = "[2025-01-12 11:11:12] User : Hello\n[2025-01-12 11:12:00] Agent : Hi there!"
    assert result == expected


@pytest.mark.asyncio
async def test_review_stm_no_records(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試無未 summary 記錄時直接返回。"""
    from agent import summary

    class FakeSessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeHistDAO:
        def __init__(self, session: object) -> None:
            pass

        async def list_unsummarized_by_session(self, session_id: int) -> list:
            return []

    monkeypatch.setattr(summary, "async_session_factory", FakeSessionContext)
    monkeypatch.setattr(summary, "AgentMsgHistDAO", FakeHistDAO)

    await summary.review_stm(
        session_db_id=1,
        model=MagicMock(),
        stm_trigger_token=10000,
        stm_summary_token=5000,
    )


@pytest.mark.asyncio
async def test_review_stm_below_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試總 token 未超過閾值時直接返回。"""
    from agent import summary

    class FakeSessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeHistDAO:
        def __init__(self, session: object) -> None:
            pass

        async def list_unsummarized_by_session(self, session_id: int) -> list:
            record = SimpleNamespace(token=100, checkpoint_id="cp1", msg_type="human")
            return [record]

    monkeypatch.setattr(summary, "async_session_factory", FakeSessionContext)
    monkeypatch.setattr(summary, "AgentMsgHistDAO", FakeHistDAO)

    await summary.review_stm(
        session_db_id=1,
        model=MagicMock(),
        stm_trigger_token=10000,
        stm_summary_token=5000,
    )


@pytest.mark.asyncio
async def test_review_stm_triggers_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試超過閾值時觸發 summary。"""
    from agent import summary

    captured: dict[str, object] = {}

    class FakeSessionContext:
        committed = False

        async def __aenter__(self) -> object:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            pass

        async def commit(self) -> None:
            FakeSessionContext.committed = True

    class FakeHistDAO:
        def __init__(self, session: object) -> None:
            pass

        async def list_unsummarized_by_session(self, session_id: int) -> list:
            return [
                SimpleNamespace(
                    token=6000,
                    checkpoint_id="cp1",
                    msg_type="human",
                    sender="User",
                    create_dt=datetime(2025, 1, 12, 10, 0, 0),
                    content="Hello world",
                ),
                SimpleNamespace(
                    token=6000,
                    checkpoint_id="cp2",
                    msg_type="ai",
                    sender="Agent",
                    create_dt=datetime(2025, 1, 12, 10, 1, 0),
                    content="Hi there",
                ),
            ]

        async def mark_checkpoint_as_summarized(self, checkpoint_id: str, session_id: int) -> None:
            captured[f"marked_{checkpoint_id}"] = True

    class FakeMemDAO:
        def __init__(self, session: object) -> None:
            pass

        async def create_from_dto(self, dto: object) -> None:
            captured["memories_written"] = True

    class FakeModel:
        async def ainvoke(self, prompt: str) -> SimpleNamespace:
            return SimpleNamespace(
                content='{"memories": [{"lossless_restatement": "Test memory", "record_dt": "2025-01-12T10:00:00"}]}'
            )

    async def fake_apply_template(conversation: str) -> str:
        return conversation

    monkeypatch.setattr(summary, "async_session_factory", FakeSessionContext)
    monkeypatch.setattr(summary, "AgentMsgHistDAO", FakeHistDAO)
    monkeypatch.setattr(summary, "ShortTermMemDAO", FakeMemDAO)
    monkeypatch.setattr(summary, "apply_stm_prompt_template", fake_apply_template)

    await summary.review_stm(
        session_db_id=1,
        model=FakeModel(),
        stm_trigger_token=10000,
        stm_summary_token=5000,
    )

    assert captured.get("marked_cp1") is True
    assert captured.get("memories_written") is True


@pytest.mark.asyncio
async def test_process_single_batch_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試無效 JSON 時不寫入 memory。"""
    from agent import summary

    captured: dict[str, object] = {}

    class FakeMemDAO:
        def __init__(self, session: object) -> None:
            pass

        async def create_from_dto(self, dto: object) -> None:
            captured["memories_written"] = True

    class FakeModel:
        async def ainvoke(self, prompt: str) -> SimpleNamespace:
            return SimpleNamespace(content="invalid json")

    async def fake_apply_template(conversation: str) -> str:
        return conversation

    monkeypatch.setattr(summary, "apply_stm_prompt_template", fake_apply_template)

    records = [
        SimpleNamespace(
            create_dt=datetime(2025, 1, 12, 10, 0, 0),
            sender="User",
            content="Hello",
        )
    ]

    await summary._process_single_batch(
        session_db_id=1,
        model=FakeModel(),
        batch_records=records,
        mem_dao=FakeMemDAO(None),
    )

    assert "memories_written" not in captured


@pytest.mark.asyncio
async def test_process_single_batch_missing_record_dt(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試缺少 record_dt 時使用當前時間。"""
    from agent import summary

    captured: dict[str, object] = {}

    class FakeMemDAO:
        def __init__(self, session: object) -> None:
            pass

        async def create_from_dto(self, dto: object) -> None:
            captured["dto"] = dto

    class FakeModel:
        async def ainvoke(self, prompt: str) -> SimpleNamespace:
            return SimpleNamespace(
                content='{"memories": [{"lossless_restatement": "Test memory"}]}'
            )

    async def fake_apply_template(conversation: str) -> str:
        return conversation

    monkeypatch.setattr(summary, "apply_stm_prompt_template", fake_apply_template)

    records = [
        SimpleNamespace(
            create_dt=datetime(2025, 1, 12, 10, 0, 0),
            sender="User",
            content="Hello",
        )
    ]

    await summary._process_single_batch(
        session_db_id=1,
        model=FakeModel(),
        batch_records=records,
        mem_dao=FakeMemDAO(None),
    )

    assert "dto" in captured
    assert captured["dto"].content == "Test memory"
