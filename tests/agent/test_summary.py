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
    """測試對話格式化為 JSON。"""
    import json
    from agent.summary import _format_conversation

    record1 = SimpleNamespace(
        create_dt=datetime(2025, 1, 12, 11, 11, 12),
        sender="User",
        msg_type="human",
        content="Hello",
    )
    record2 = SimpleNamespace(
        create_dt=datetime(2025, 1, 12, 11, 12, 0),
        sender="Agent",
        msg_type="ai",
        content="Hi there!",
    )

    result = _format_conversation([record1, record2])
    
    # 驗證係有效 JSON
    data = json.loads(result)
    assert len(data) == 2
    assert data[0]["sender"] == "User"
    assert data[0]["content"] == "Hello"
    assert data[0]["msg_type"] == "human"
    assert data[1]["sender"] == "Agent"
    assert data[1]["content"] == "Hi there!"
    assert data[1]["msg_type"] == "ai"


def test_group_records_by_human_basic() -> None:
    """測試基本 human 分組。"""
    from agent.summary import group_records_by_human

    records = [
        SimpleNamespace(msg_type="human", token=100),
        SimpleNamespace(msg_type="ai", token=200),
        SimpleNamespace(msg_type="human", token=50),
        SimpleNamespace(msg_type="ai", token=150),
    ]

    groups = group_records_by_human(records)
    assert len(groups) == 2
    assert len(groups[0]) == 2  # [human, ai]
    assert len(groups[1]) == 2  # [human, ai]


def test_group_records_by_human_consecutive() -> None:
    """測試連續 human 分組。"""
    from agent.summary import group_records_by_human

    records = [
        SimpleNamespace(msg_type="human", token=100),
        SimpleNamespace(msg_type="human", token=50),
        SimpleNamespace(msg_type="ai", token=200),
    ]

    groups = group_records_by_human(records)
    assert len(groups) == 2
    assert len(groups[0]) == 1  # [human_1]
    assert len(groups[1]) == 2  # [human_2, ai]


def test_group_records_by_human_with_tools() -> None:
    """測試包含 tool 訊息的分組。"""
    from agent.summary import group_records_by_human

    records = [
        SimpleNamespace(msg_type="human", token=100),
        SimpleNamespace(msg_type="tool", token=50),
        SimpleNamespace(msg_type="tool_result", token=30),
        SimpleNamespace(msg_type="ai", token=200),
    ]

    groups = group_records_by_human(records)
    assert len(groups) == 1
    assert len(groups[0]) == 4  # [human, tool, tool_result, ai]


def test_group_records_by_human_empty() -> None:
    """測試空記錄列表。"""
    from agent.summary import group_records_by_human

    groups = group_records_by_human([])
    assert groups == []


def test_select_conversation_groups_below_threshold() -> None:
    """測試總 token 未超過閾值時返回空列表。"""
    from agent.summary import select_conversation_groups_for_summary

    groups = [
        [SimpleNamespace(token=100)],
        [SimpleNamespace(token=200)],
    ]

    keep, summary = select_conversation_groups_for_summary(groups, 10000, 5000)
    assert keep == []
    assert summary == []


def test_select_conversation_groups_triggers_summary() -> None:
    """測試超過閾值時正確分組。"""
    from agent.summary import select_conversation_groups_for_summary

    groups = [
        [SimpleNamespace(token=6000)],
        [SimpleNamespace(token=6000)],
    ]

    keep, summary = select_conversation_groups_for_summary(groups, 10000, 5000)
    # keep_token = 10000 - 5000 = 5000, so neither group fits in keep
    assert len(summary) == 2
    assert len(summary[0]) == 1
    assert len(summary[1]) == 1


def test_compute_truncate_count_empty() -> None:
    """測試無 summary group 時返回 0。"""
    from agent.summary import compute_truncate_count

    result = compute_truncate_count([])
    assert result == 0


def test_compute_truncate_count_basic() -> None:
    """測試基本截斷計數計算。"""
    from agent.summary import compute_truncate_count

    groups = [
        [
            SimpleNamespace(message_idx=0),
            SimpleNamespace(message_idx=1),
        ],
    ]

    result = compute_truncate_count(groups)
    # max message_idx is 1, so truncate count = 1
    assert result == 1


def test_compute_truncate_count_multiple_groups() -> None:
    """測試多個 summary group 時取最大 message_idx。"""
    from agent.summary import compute_truncate_count

    groups = [
        [
            SimpleNamespace(message_idx=0),
            SimpleNamespace(message_idx=1),
        ],
        [
            SimpleNamespace(message_idx=3),
            SimpleNamespace(message_idx=4),
        ],
    ]

    result = compute_truncate_count(groups)
    # max message_idx across all groups is 4
    assert result == 4


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
            record = SimpleNamespace(token=100, msg_type="human")
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
                    id=1,
                    token=6000,
                    msg_type="human",
                    sender="User",
                    create_dt=datetime(2025, 1, 12, 10, 0, 0),
                    content="Hello world",
                    message_idx=0,
                ),
                SimpleNamespace(
                    id=2,
                    token=6000,
                    msg_type="ai",
                    sender="Agent",
                    create_dt=datetime(2025, 1, 12, 10, 1, 0),
                    content="Hi there",
                    message_idx=1,
                ),
            ]

        async def mark_records_as_summarized(self, record_ids: list[int], session_id: int) -> None:
            captured["marked_ids"] = record_ids

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

    result = await summary.review_stm(
        session_db_id=1,
        model=FakeModel(),
        stm_trigger_token=10000,
        stm_summary_token=5000,
    )

    assert result is not None
    truncate_count, summary_groups, records = result
    assert truncate_count == 1  # max message_idx is 1
    assert captured.get("memories_written") is True
    assert captured.get("marked_ids") == [1, 2]


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
            msg_type="human",
            content="Hello",
        )
    ]

    result = await summary._process_single_batch(
        session_db_id=1,
        model=FakeModel(),
        batch_records=records,
        mem_dao=FakeMemDAO(None),
    )

    assert result is False
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
            msg_type="human",
            content="Hello",
        )
    ]

    result = await summary._process_single_batch(
        session_db_id=1,
        model=FakeModel(),
        batch_records=records,
        mem_dao=FakeMemDAO(None),
    )

    assert result is True
    assert "dto" in captured
    assert captured["dto"].content == "Test memory"


@pytest.mark.asyncio
async def test_process_summary_batches_skip_marking_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試當批次處理失敗時，不標記記錄為已 summary。"""
    from agent import summary

    captured: dict[str, object] = {}

    class FakeMemDAO:
        def __init__(self, session: object) -> None:
            pass

        async def create_from_dto(self, dto: object) -> None:
            captured["memories_written"] = True

    class FakeHistDAO:
        def __init__(self, session: object) -> None:
            pass

        async def mark_records_as_summarized(self, record_ids: list[int], session_id: int) -> None:
            captured["marked_ids"] = record_ids

    class FakeModel:
        async def ainvoke(self, prompt: str) -> SimpleNamespace:
            return SimpleNamespace(content="invalid json")

    async def fake_apply_template(conversation: str) -> str:
        return conversation

    monkeypatch.setattr(summary, "apply_stm_prompt_template", fake_apply_template)

    groups = [
        [
            SimpleNamespace(
                id=1,
                token=6000,
                msg_type="human",
                sender="User",
                create_dt=datetime(2025, 1, 12, 10, 0, 0),
                content="Hello world",
            ),
        ]
    ]

    result = await summary._process_summary_batches(
        session_db_id=1,
        model=FakeModel(),
        summary_groups=groups,
        hist_dao=FakeHistDAO(None),
        mem_dao=FakeMemDAO(None),
        max_token=30000,
    )

    # 驗證沒有標記任何記錄
    assert "marked_ids" not in captured
    assert result == set()
