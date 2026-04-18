# Task Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 實現 heap-based task scheduler，每秒 check 一次，到時就創建 task record，衝突時打散喺 5 分鐘內執行。

**Architecture:** 使用 min-heap 按 `next_run_at` 排序所有 enabled schedule，主循環計算到最近 schedule 嘅時間並 sleep，到期時用 croniter 計算下次執行時間，創建 task record，更新 DB。

**Tech Stack:** Python asyncio, croniter, SQLAlchemy async, FastAPI lifespan

---

### Task 1: Add croniter dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add croniter to requirements.txt**

Add `croniter>=1.3.0` to the end of `requirements.txt`:

```
# Task Scheduler
croniter>=1.3.0
```

- [ ] **Step 2: Install dependency**

Run: `pip install croniter>=1.3.0`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: add croniter for cron expression parsing"
```

---

### Task 2: Create scheduler module and ScheduleManager

**Files:**
- Create: `backend/scheduler/__init__.py`
- Create: `backend/scheduler/manager.py`
- Test: `tests/scheduler/test_manager.py`

- [ ] **Step 1: Create scheduler __init__.py**

```python
"""Task scheduler module."""

from __future__ import annotations

from scheduler.scheduler import TaskScheduler

__all__ = ["TaskScheduler"]
```

- [ ] **Step 2: Write test for ScheduleManager**

```python
"""Tests for ScheduleManager."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from db.entity import ScheduleEntity, TaskEntity
from scheduler.manager import ScheduleManager


@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session


@pytest.fixture
def manager(mock_session):
    return ScheduleManager(mock_session)


@pytest.fixture
def sample_schedule():
    schedule = MagicMock(spec=ScheduleEntity)
    schedule.id = 1
    schedule.task_id = 100
    schedule.cron_expression = "0 * * * *"
    schedule.enabled = True
    schedule.last_run_at = None
    schedule.next_run_at = datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc)
    schedule.task = MagicMock(spec=TaskEntity)
    schedule.task.name = "Test Task"
    schedule.task.task_type = "scheduled"
    schedule.task.content = "Test content"
    schedule.task.agent_id = 1
    schedule.task.parameters = {"key": "value"}
    return schedule


async def test_load_enabled_schedules(manager, mock_session):
    mock_schedule = MagicMock(spec=ScheduleEntity)
    mock_schedule.id = 1
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_schedule]
    mock_session.execute.return_value = mock_result

    result = await manager.load_enabled_schedules()

    assert result == [mock_schedule]
    mock_session.execute.assert_called_once()


async def test_mark_schedule_executed(manager, mock_session):
    schedule = MagicMock(spec=ScheduleEntity)
    schedule.id = 1
    new_next_run = datetime(2026, 4, 18, 11, 0, tzinfo=timezone.utc)

    await manager.mark_schedule_executed(schedule, new_next_run)

    assert schedule.last_run_at is not None
    assert schedule.next_run_at == new_next_run
    mock_session.flush.assert_called()
    mock_session.refresh.assert_called()


async def test_create_task_record(manager, mock_session, sample_schedule):
    await manager.create_task_record(sample_schedule)

    mock_session.add.assert_called_once()
    mock_session.flush.assert_called()
    mock_session.refresh.assert_called()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/scheduler/test_manager.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'scheduler'"

- [ ] **Step 4: Write ScheduleManager implementation**

```python
"""ScheduleManager — DB operations for the scheduler."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from db.config import async_session_factory
from db.dao.base import BaseDAO
from db.dao.schedule_dao import ScheduleDAO
from db.dao.task_dao import TaskDAO
from db.dto.task import TaskCreate
from db.entity import ScheduleEntity, TaskEntity
from i18n import _
from utils.timezone import now_server

logger = logging.getLogger(__name__)


class ScheduleManager:
    """負責 DB 操作：載入、更新 schedule，創建 task record。"""

    def __init__(self, session) -> None:
        self._session = session
        self._schedule_dao = ScheduleDAO(session)
        self._task_dao = TaskDAO(session)

    async def load_enabled_schedules(self) -> list[ScheduleEntity]:
        """載入所有 enabled schedule（包含關聯嘅 task）。"""
        stmt = (
            select(ScheduleEntity)
            .where(ScheduleEntity.enabled == True)
            .options(__import__('sqlalchemy.orm', fromlist=['joinedload']).joinedload(ScheduleEntity.task))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_schedule_executed(
        self, schedule: ScheduleEntity, next_run_at: datetime
    ) -> None:
        """更新 last_run_at = now，next_run_at = 新時間。"""
        schedule.last_run_at = now_server()
        schedule.next_run_at = next_run_at
        await self._session.flush()
        await self._session.refresh(schedule)
        logger.debug(
            _("Schedule %s 已更新 (next_run_at=%s)"),
            schedule.id,
            next_run_at,
        )

    async def create_task_record(self, schedule: ScheduleEntity) -> Optional[TaskEntity]:
        """根據 schedule 創建 TaskEntity record。"""
        task = schedule.task
        if not task:
            logger.error(_("Schedule %s 沒有關聯的 task"), schedule.id)
            return None

        task_dto = TaskCreate(
            name=task.name,
            task_type=task.task_type,
            content=task.content,
            agent_id=task.agent_id,
            parameters=task.parameters,
            status="pending",
            next_process_dt=now_server(),
        )
        entity = TaskEntity(**task_dto.model_dump())
        await self._task_dao.create(entity)
        logger.info(_("已為 schedule %s 創建 task record (task_id=%s)"), schedule.id, entity.id)
        return entity
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/scheduler/test_manager.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/scheduler/__init__.py backend/scheduler/manager.py tests/scheduler/test_manager.py
git commit -m "feat: add ScheduleManager for DB operations"
```

---

### Task 3: Implement TaskScheduler core

**Files:**
- Create: `backend/scheduler/scheduler.py`
- Test: `tests/scheduler/test_scheduler.py`

- [ ] **Step 1: Write test for TaskScheduler**

```python
"""Tests for TaskScheduler."""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from db.entity import ScheduleEntity
from scheduler.scheduler import TaskScheduler


@pytest.fixture
def mock_schedule():
    schedule = MagicMock(spec=ScheduleEntity)
    schedule.id = 1
    schedule.cron_expression = "0 * * * *"
    schedule.enabled = True
    schedule.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=2)
    return schedule


@pytest.fixture
def scheduler():
    return TaskScheduler()


def test_add_schedule_to_heap(scheduler, mock_schedule):
    scheduler._add_to_heap(mock_schedule)
    assert len(scheduler._heap) == 1


def test_get_due_schedules(scheduler, mock_schedule):
    # 設置為已經到期
    mock_schedule.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    scheduler._add_to_heap(mock_schedule)

    due = scheduler._get_due_schedules()
    assert len(due) == 1
    assert due[0] == mock_schedule


def test_get_sleep_time_with_future_schedule(scheduler, mock_schedule):
    future_time = datetime.now(timezone.utc) + timedelta(seconds=30)
    mock_schedule.next_run_at = future_time
    scheduler._add_to_heap(mock_schedule)

    sleep_time = scheduler._get_sleep_time()
    assert 0 < sleep_time <= 30


def test_get_sleep_time_with_due_schedule(scheduler, mock_schedule):
    mock_schedule.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    scheduler._add_to_heap(mock_schedule)

    sleep_time = scheduler._get_sleep_time()
    assert sleep_time < 1


def test_get_sleep_time_empty_heap(scheduler):
    sleep_time = scheduler._get_sleep_time()
    assert sleep_time == 60  # Default max wait


def test_scatter_schedules_single(scheduler):
    schedules = [MagicMock()]
    result = scheduler._scatter_schedules(schedules)
    assert len(result) == 1
    assert result[0][1] == 0  # Immediate execution


def test_scatter_schedules_multiple(scheduler):
    schedules = [MagicMock() for _ in range(3)]
    result = scheduler._scatter_schedules(schedules)
    assert len(result) == 3
    # All delays should be within 5 minutes
    for _, delay in result:
        assert 0 <= delay <= 300
    # Delays should be sorted (ascending)
    delays = [d for _, d in result]
    assert delays == sorted(delays)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scheduler/test_scheduler.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'scheduler.scheduler'"

- [ ] **Step 3: Write TaskScheduler implementation**

```python
"""TaskScheduler — heap-based schedule processor."""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Optional

from croniter import croniter

from db.config import async_session_factory
from db.entity import ScheduleEntity
from i18n import _
from scheduler.manager import ScheduleManager
from utils.timezone import now_server

logger = logging.getLogger(__name__)

# Maximum time to wait between heap reloads (seconds)
_MAX_SLEEP_TIME = 60

# Scatter window for conflicting schedules (seconds)
_SCATTER_WINDOW = 300


class TaskScheduler:
    """Heap-based scheduler，按 next_run_at 排序。"""

    def __init__(self) -> None:
        self._heap: list[tuple[datetime, ScheduleEntity]] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def _add_to_heap(self, schedule: ScheduleEntity) -> None:
        """將 schedule 加入 heap。"""
        import heapq
        heapq.heappush(self._heap, (schedule.next_run_at, schedule))

    def _get_due_schedules(self) -> list[ScheduleEntity]:
        """取出所有到期嘅 schedule。"""
        import heapq
        now = now_server()
        due = []
        while self._heap and self._heap[0][0] <= now:
            _, schedule = heapq.heappop(self._heap)
            due.append(schedule)
        return due

    def _get_sleep_time(self) -> float:
        """計算到最近 schedule 嘅 sleep 時間。"""
        if not self._heap:
            return float(_MAX_SLEEP_TIME)

        now = now_server()
        next_time = self._heap[0][0]
        diff = (next_time - now).total_seconds()

        if diff <= 0:
            return 0.0

        return min(diff, float(_MAX_SLEEP_TIME))

    def _scatter_schedules(
        self, schedules: list[ScheduleEntity]
    ) -> list[tuple[ScheduleEntity, float]]:
        """打散多個同時到期嘅 schedule，隨機分佈喺 5 分鐘內。"""
        if len(schedules) <= 1:
            return [(s, 0.0) for s in schedules]

        # 生成 N 個隨機時間點（0~300 秒）
        delays = sorted([random.uniform(0, _SCATTER_WINDOW) for _ in schedules])
        return list(zip(schedules, delays))

    def _calculate_next_run(self, schedule: ScheduleEntity) -> Optional[datetime]:
        """用 croniter 計算下一個執行時間。"""
        try:
            cron = croniter(schedule.cron_expression, now_server())
            return cron.get_next(datetime)
        except Exception as exc:
            logger.error(
                _("Schedule %s cron 解析失敗：%s"),
                schedule.id,
                exc,
            )
            return None

    async def _process_due_schedules(self) -> None:
        """處理所有到期 schedule，打散邏輯，創建 task record。"""
        due = self._get_due_schedules()
        if not due:
            return

        logger.info(_("發現 %d 個到期 schedule，正在處理"), len(due))

        scattered = self._scatter_schedules(due)

        async with async_session_factory() as session:
            manager = ScheduleManager(session)

            for schedule, delay in scattered:
                if delay > 0:
                    logger.debug(
                        _("Schedule %s 將延遲 %.1f 秒執行"),
                        schedule.id,
                        delay,
                    )
                    await asyncio.sleep(delay)

                next_run = self._calculate_next_run(schedule)
                if next_run is None:
                    # cron 解析失敗，disable 該 schedule
                    schedule.enabled = False
                    await session.commit()
                    continue

                try:
                    await manager.create_task_record(schedule)
                    await manager.mark_schedule_executed(schedule, next_run)
                    await session.commit()
                    self._add_to_heap(schedule)
                except Exception as exc:
                    logger.error(
                        _("Schedule %s 處理失敗：%s"),
                        schedule.id,
                        exc,
                    )
                    await session.rollback()
                    # 保留原 next_run_at，下次重試
                    self._add_to_heap(schedule)

    async def _reload_schedules(self) -> None:
        """重新載入 heap（處理 DB 變更）。"""
        async with async_session_factory() as session:
            manager = ScheduleManager(session)
            try:
                schedules = await manager.load_enabled_schedules()
                self._heap.clear()
                for schedule in schedules:
                    self._add_to_heap(schedule)
                logger.debug(_("已重新載入 %d 個 schedule"), len(self._heap))
            except Exception as exc:
                logger.error(_("重新載入 schedule 失敗：%s"), exc)

    async def _main_loop(self) -> None:
        """主循環：計算 sleep 時間 → wake up → 處理到期 schedule。"""
        logger.info(_("TaskScheduler 主循環已啟動"))

        while self._running:
            try:
                sleep_time = self._get_sleep_time()

                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

                await self._process_due_schedules()

                # 定期重新載入（每 60 秒）
                if not self._heap:
                    await self._reload_schedules()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(_("TaskScheduler 循環錯誤：%s"), exc)
                await asyncio.sleep(5)

        logger.info(_("TaskScheduler 主循環已停止"))

    async def start(self) -> None:
        """載入 schedule 到 heap，啟動主循環。"""
        if self._running:
            logger.warning(_("TaskScheduler 已經在運行"))
            return

        self._running = True
        await self._reload_schedules()
        self._task = asyncio.create_task(self._main_loop(), name="task-scheduler")
        logger.info(_("TaskScheduler 已啟動 (%d 個 schedule)"), len(self._heap))

    async def stop(self) -> None:
        """優雅停止。"""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(_("TaskScheduler 已停止"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/scheduler/test_scheduler.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/scheduler/scheduler.py tests/scheduler/test_scheduler.py
git commit -m "feat: add TaskScheduler with heap-based scheduling"
```

---

### Task 4: Integrate scheduler into FastAPI lifespan

**Files:**
- Modify: `backend/api/app.py`

- [ ] **Step 1: Modify app.py to include scheduler**

Change the lifespan function in `backend/api/app.py` to:

```python
"""FastAPI application setup."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from db.config import close_db, init_db
from msg_queue.handler import register_all_handlers
from msg_queue.manager import get_queue_manager
from scheduler import TaskScheduler

from api.routes.openai_chat import router as openai_chat_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize shared services for the API process."""
    qm = get_queue_manager()
    register_all_handlers(qm)
    await init_db()
    qm.start()

    scheduler = TaskScheduler()
    await scheduler.start()

    try:
        yield
    finally:
        await scheduler.stop()
        qm.stop()
        await close_db()


app = FastAPI(lifespan=lifespan)
app.include_router(openai_chat_router)
```

- [ ] **Step 2: Run existing tests to verify no regression**

Run: `pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/api/app.py
git commit -m "feat: integrate TaskScheduler into FastAPI lifespan"
```

---

### Task 5: Add scheduler tests and final verification

**Files:**
- Create: `tests/scheduler/__init__.py`
- Modify: `requirements.txt` (verify croniter is installed)

- [ ] **Step 1: Create tests/scheduler/__init__.py**

```python
"""Scheduler tests."""
```

- [ ] **Step 2: Run all scheduler tests**

Run: `pytest tests/scheduler/ -v`
Expected: All tests PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Final commit**

```bash
git add tests/scheduler/__init__.py
git commit -m "test: add scheduler test module"
```
