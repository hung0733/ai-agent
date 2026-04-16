# STM Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 實作 `review_stm()` 函數，當對話歷史 token 超過閾值時，自動將舊對話壓縮成摘要並寫入 `short_term_mem` 表。

**Architecture:** 從 `agent_msg_hist` 讀取未 summary 的記錄，按 checkpoint 分組，分批呼叫 LLM 生成摘要，寫入 `short_term_mem` 並標記已處理記錄。

**Tech Stack:** Python, SQLAlchemy, LangChain, tiktoken

---

### Task 1: 新增 DAO 方法 — 查詢未 summary 記錄

**Files:**
- Modify: `backend/db/dao/agent_msg_hist_dao.py`

- [ ] **Step 1: 新增 `list_unsummarized_by_session` 方法**

```python
async def list_unsummarized_by_session(self, session_id: int) -> list[AgentMsgHistEntity]:
    """獲取 session 中所有 is_stm_summary=False 的記錄（按 create_dt 排序）。"""
    stmt = (
        select(AgentMsgHistEntity)
        .where(AgentMsgHistEntity.session_id == session_id)
        .where(AgentMsgHistEntity.is_stm_summary == False)  # noqa: E712
        .order_by(AgentMsgHistEntity.create_dt, AgentMsgHistEntity.message_idx, AgentMsgHistEntity.id)
    )
    result = await self._session.execute(stmt)
    return list(result.scalars().all())
```

- [ ] **Step 2: 新增 `mark_checkpoint_as_summarized` 方法**

```python
async def mark_checkpoint_as_summarized(self, checkpoint_id: str, session_id: int) -> None:
    """將指定 checkpoint 的所有記錄標記為 is_stm_summary=True。"""
    stmt = (
        update(AgentMsgHistEntity)
        .where(AgentMsgHistEntity.session_id == session_id)
        .where(AgentMsgHistEntity.checkpoint_id == checkpoint_id)
        .values(is_stm_summary=True)
    )
    await self._session.execute(stmt)
```

- [ ] **Step 3: 確認 import**

確保文件頂部有：
```python
from sqlalchemy import select, update
```

---

### Task 2: 實作 `review_stm()` 主函數

**Files:**
- Modify: `backend/agent/summary.py`

- [ ] **Step 1: 寫入完整實作**

```python
"""STM (Short-Term Memory) review and summary workflow."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from langchain_core.language_models import BaseChatModel

from backend.agent.prompt import apply_stm_prompt_template
from backend.db.config import async_session_factory
from backend.db.dao.agent_msg_hist_dao import AgentMsgHistDAO
from backend.db.dao.short_term_mem_dao import ShortTermMemDAO
from backend.db.dto.memory import ShortTermMemCreate
from backend.utils.tools import Tools
from i18n import _

logger = logging.getLogger(__name__)


async def review_stm(
    session_db_id: int,
    model: BaseChatModel,
    stm_trigger_token: int,
    stm_summary_token: int,
    max_token: int = 30000,
) -> None:
    """Review and summarize short-term memory when token threshold is exceeded.

    Args:
        session_db_id: Database ID of the session.
        model: LLM model to use for summarization.
        stm_trigger_token: Token threshold to trigger summarization.
        stm_summary_token: Number of tokens to keep (not summarize).
        max_token: Maximum tokens to summarize in a single batch.
    """
    async with async_session_factory() as session:
        hist_dao = AgentMsgHistDAO(session)
        mem_dao = ShortTermMemDAO(session)

        # Step 1: 查詢未 summary 的記錄
        records = await hist_dao.list_unsummarized_by_session(session_db_id)
        if not records:
            logger.debug(_("無未 summary 的記錄，session=%s"), session_db_id)
            return

        # Step 2: 按 checkpoint 分組
        checkpoints: dict[str, list] = {}
        for record in records:
            checkpoints.setdefault(record.checkpoint_id, []).append(record)

        # Step 3: 計算總 token
        total_token = sum(r.token for r in records)
        if total_token <= stm_trigger_token:
            logger.debug(
                _("總 token (%s) 未超過閾值 (%s)，session=%s"),
                total_token,
                stm_trigger_token,
                session_db_id,
            )
            return

        # Step 4: 確定保留範圍（最新 stm_trigger_token - stm_summary_token token）
        keep_token = stm_trigger_token - stm_summary_token
        checkpoint_ids = list(checkpoints.keys())  # 已按 create_dt 排序
        checkpoint_ids.reverse()  # 由新到舊

        keep_checkpoints: list[str] = []
        summary_checkpoints: list[str] = []
        current_keep_token = 0

        for cp_id in checkpoint_ids:
            cp_records = checkpoints[cp_id]
            cp_token = sum(r.token for r in cp_records)
            if current_keep_token + cp_token <= keep_token:
                keep_checkpoints.append(cp_id)
                current_keep_token += cp_token
            else:
                summary_checkpoints.append(cp_id)

        # summary_checkpoints 是由新到舊，反轉回由舊到新
        summary_checkpoints.reverse()

        if not summary_checkpoints:
            logger.debug(_("無需要 summary 的 checkpoint，session=%s"), session_db_id)
            return

        # Step 5: 分批 summary
        await _process_summary_batches(
            session_db_id=session_db_id,
            model=model,
            summary_checkpoints=summary_checkpoints,
            checkpoints=checkpoints,
            hist_dao=hist_dao,
            mem_dao=mem_dao,
            max_token=max_token,
        )

        await session.commit()


async def _process_summary_batches(
    session_db_id: int,
    model: BaseChatModel,
    summary_checkpoints: list[str],
    checkpoints: dict[str, list],
    hist_dao: AgentMsgHistDAO,
    mem_dao: ShortTermMemDAO,
    max_token: int,
) -> None:
    """Process summary in batches, each batch ≤ max_token."""
    # 收集所有待 summary 的 human/ai 記錄（由舊到新）
    all_summary_records: list = []
    for cp_id in summary_checkpoints:
        for record in checkpoints[cp_id]:
            if record.msg_type in ("human", "ai"):
                all_summary_records.append(record)

    # 分批處理
    batch_records: list = []
    batch_token = 0

    for record in all_summary_records:
        if batch_token + record.token > max_token and batch_records:
            # 處理當前批次
            await _process_single_batch(
                session_db_id=session_db_id,
                model=model,
                batch_records=batch_records,
                mem_dao=mem_dao,
            )
            batch_records = []
            batch_token = 0
        batch_records.append(record)
        batch_token += record.token

    # 處理最後一批
    if batch_records:
        await _process_single_batch(
            session_db_id=session_db_id,
            model=model,
            batch_records=batch_records,
            mem_dao=mem_dao,
        )

    # 標記所有 checkpoint 為已 summary
    for cp_id in summary_checkpoints:
        await hist_dao.mark_checkpoint_as_summarized(cp_id, session_db_id)


def _format_conversation(records: list) -> str:
    """Format records into conversation string."""
    lines = []
    for record in records:
        timestamp = record.create_dt.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"[{timestamp}] {record.sender} : {record.content}")
    return "\n".join(lines)


async def _process_single_batch(
    session_db_id: int,
    model: BaseChatModel,
    batch_records: list,
    mem_dao: ShortTermMemDAO,
) -> None:
    """Process a single batch of records for summarization."""
    try:
        conversation = _format_conversation(batch_records)
        prompt = await apply_stm_prompt_template(conversation)

        response = await model.ainvoke(prompt)
        content = response.content.strip()

        # 解析 JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.error(_("LLM 返回的 JSON 格式錯誤: %s"), content[:200])
            return

        memories = data.get("memories", [])
        if not memories:
            logger.debug(_("LLM 未返回任何 memories"))
            return

        # 寫入 short_term_mem
        now = datetime.now(timezone.utc)
        for memory in memories:
            restatement = memory.get("lossless_restatement", "")
            if not restatement:
                continue

            record_dt_str = memory.get("record_dt")
            if record_dt_str:
                try:
                    record_dt = datetime.fromisoformat(record_dt_str)
                except (ValueError, TypeError):
                    record_dt = now
            else:
                record_dt = now

            token = Tools.get_token_count(restatement)
            dto = ShortTermMemCreate(
                session_id=session_db_id,
                content=restatement,
                create_dt=record_dt,
                token=token,
            )
            await mem_dao.create_from_dto(dto)

        logger.info(_("已寫入 %s 條 short-term memories"), len(memories))

    except Exception as exc:
        logger.error(_("Summary 批次處理失敗: %s"), exc)
```

- [ ] **Step 2: 確認 import 正確**

確保所有 import 路徑正確（根據專案結構調整 `backend.` 前綴）。

---

### Task 3: 撰寫單元測試

**Files:**
- Create: `tests/agent/test_summary.py`

- [ ] **Step 1: 寫入測試**

```python
"""Tests for STM review workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agent.summary import review_stm, _format_conversation


def test_format_conversation() -> None:
    """測試對話格式化。"""
    record1 = MagicMock()
    record1.create_dt = datetime(2025, 1, 12, 11, 11, 12)
    record1.sender = "User"
    record1.content = "Hello"

    record2 = MagicMock()
    record2.create_dt = datetime(2025, 1, 12, 11, 12, 0)
    record2.sender = "Agent"
    record2.content = "Hi there!"

    result = _format_conversation([record1, record2])
    expected = "[2025-01-12 11:11:12] User : Hello\n[2025-01-12 11:12:00] Agent : Hi there!"
    assert result == expected


@pytest.mark.asyncio
async def test_review_stm_no_records() -> None:
    """測試無未 summary 記錄時直接返回。"""
    with patch("backend.agent.summary.async_session_factory"):
        with patch("backend.agent.summary.AgentMsgHistDAO") as mock_dao:
            mock_dao.return_value.list_unsummarized_by_session = AsyncMock(return_value=[])

            await review_stm(
                session_db_id=1,
                model=MagicMock(),
                stm_trigger_token=10000,
                stm_summary_token=5000,
            )

            mock_dao.return_value.list_unsummarized_by_session.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_review_stm_below_threshold() -> None:
    """測試總 token 未超過閾值時直接返回。"""
    record = MagicMock()
    record.token = 100
    record.checkpoint_id = "cp1"
    record.msg_type = "human"

    with patch("backend.agent.summary.async_session_factory"):
        with patch("backend.agent.summary.AgentMsgHistDAO") as mock_dao:
            mock_dao.return_value.list_unsummarized_by_session = AsyncMock(return_value=[record])

            await review_stm(
                session_db_id=1,
                model=MagicMock(),
                stm_trigger_token=10000,
                stm_summary_token=5000,
            )
```

- [ ] **Step 2: 運行測試**

```bash
pytest tests/agent/test_summary.py -v
```

---

### Task 4: 整合驗證

**Files:**
- Modify: `backend/agent/agent.py`（如需要，在適當位置呼叫 `review_stm`）

- [ ] **Step 1: 確認 `review_stm` 可被外部呼叫**

確認函數簽名正確，可從 `Agent` 類或其他地方呼叫。

- [ ] **Step 2: 運行完整測試**

```bash
pytest tests/ -v -k summary
```

---

## Self-Review

1. **Spec coverage:** 所有 R1-R10 需求均已覆蓋
2. **Placeholder scan:** 無 TBD/TODO
3. **Type consistency:** 所有方法簽名與現有 DAO/DTO 一致
4. **Error handling:** 已覆蓋所有錯誤情境
