"""TaskScheduler — heap-based schedule processor."""

from __future__ import annotations

import asyncio
import heapq
import logging
import random
from datetime import datetime, timedelta
from typing import Optional

from croniter import croniter, CroniterBadCronError

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from db.config import async_session_factory
from db.entity import ScheduleEntity, TaskEntity
from i18n import _
from .manager import ScheduleManager
from utils.timezone import now_server

logger = logging.getLogger(__name__)

# Maximum time to wait between heap reloads (seconds)
_MAX_SLEEP_TIME = 60

# Scatter window for conflicting schedules (seconds)
_SCATTER_WINDOW = 300


class TaskScheduler:
    """Heap-based scheduler，按 next_run_at 排序。"""

    def __init__(self) -> None:
        self._heap: list[tuple[datetime, int]] = []  # (next_run_at, schedule_id)
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def _add_to_heap(self, schedule_id: int, next_run_at: datetime) -> None:
        """將 schedule 加入 heap。"""
        heapq.heappush(self._heap, (next_run_at, schedule_id))

    async def _get_due_schedule_ids(self) -> list[int]:
        """取出所有到期 schedule 的 ID。"""
        now = now_server()
        due_ids = []
        while self._heap and self._heap[0][0] <= now:
            _, schedule_id = heapq.heappop(self._heap)
            due_ids.append(schedule_id)
        return due_ids

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
        except CroniterBadCronError as exc:
            logger.error(
                _("Schedule %s cron 表達式無效：%s"),
                schedule.id,
                exc,
            )
            return None
        except Exception as exc:
            logger.error(
                _("Schedule %s cron 解析失敗：%s"),
                schedule.id,
                exc,
            )
            return None

    async def _process_due_schedules(self) -> None:
        """處理所有到期 schedule，打散邏輯，創建 task record。"""
        due_ids = await self._get_due_schedule_ids()
        if not due_ids:
            return

        logger.info(_("發現 %d 個到期 schedule，正在處理"), len(due_ids))

        # 用獨立 session 載入所有 due schedules（包含 task relationship）
        async with async_session_factory() as session:
            from db.dao.schedule_dao import ScheduleDAO
            schedule_dao = ScheduleDAO(session)

            due_schedules = []
            for sid in due_ids:
                # 使用 joinedload 預先載入 task，避免 lazy load 觸發 greenlet 錯誤
                stmt = (
                    select(ScheduleEntity)
                    .where(ScheduleEntity.id == sid)
                    .options(joinedload(ScheduleEntity.task))
                )
                result = await session.execute(stmt)
                fresh = result.scalar_one_or_none()
                if fresh:
                    # 在 session 內讀取 next_run_at，避免 detached 後訪問
                    due_schedules.append((fresh.id, fresh.next_run_at, fresh))
                else:
                    logger.warning(_("Schedule %s 已不存在"), sid)

        if not due_schedules:
            return

        # 只傳遞 entity，next_run_at 已在 session 內讀取
        scattered = self._scatter_schedules([s[2] for s in due_schedules])
        start_time = now_server()

        for schedule, delay in scattered:
            # 計算相對等待時間（相對於 start_time）
            target_time = start_time + timedelta(seconds=delay)
            wait_seconds = (target_time - now_server()).total_seconds()
            if wait_seconds > 0:
                logger.debug(
                    _("Schedule %s 將延遲 %.1f 秒執行"),
                    schedule.id,
                    wait_seconds,
                )
                await asyncio.sleep(wait_seconds)

            # 每個 schedule 用獨立 session 處理
            async with async_session_factory() as session:
                manager = ScheduleManager(session)

                # 重新載入以確保 session 正確（包含 task relationship）
                stmt = (
                    select(ScheduleEntity)
                    .where(ScheduleEntity.id == schedule.id)
                    .options(joinedload(ScheduleEntity.task))
                )
                result = await session.execute(stmt)
                fresh_schedule = result.scalar_one_or_none()
                if fresh_schedule is None:
                    logger.warning(_("Schedule %s 已不存在"), schedule.id)
                    continue

                next_run = self._calculate_next_run(fresh_schedule)
                if next_run is None:
                    # cron 解析失敗，disable 該 schedule
                    fresh_schedule.enabled = False
                    await session.commit()
                    continue

                try:
                    await manager.create_task_record(fresh_schedule)
                    await manager.mark_schedule_executed(fresh_schedule, next_run)
                    await session.commit()
                    self._add_to_heap(fresh_schedule.id, next_run)
                except Exception as exc:
                    logger.error(
                        _("Schedule %s 處理失敗：%s"),
                        schedule.id,
                        exc,
                    )
                    await session.rollback()
                    # 保留原 next_run_at，下次重試
                    # 從 due_schedules 中找回原 next_run_at
                    orig_next_run = next((s[1] for s in due_schedules if s[0] == schedule.id), schedule.next_run_at)
                    self._add_to_heap(schedule.id, orig_next_run)

    async def _reload_schedules(self) -> None:
        """重新載入 heap（處理 DB 變更）。"""
        async with async_session_factory() as session:
            manager = ScheduleManager(session)
            try:
                schedules = await manager.load_enabled_schedules()
                # 只保存 ID 和 next_run_at，唔保持 session 關聯
                self._heap.clear()
                for schedule in schedules:
                    self._add_to_heap(schedule.id, schedule.next_run_at)
                logger.debug(_("已重新載入 %d 個 schedule"), len(self._heap))
            except Exception as exc:
                logger.error(_("重新載入 schedule 失敗：%s"), exc)

    async def _main_loop(self) -> None:
        """主循環：計算 sleep 時間 → wake up → 處理到期 schedule。"""
        logger.info(_("TaskScheduler 主循環已啟動"))

        last_reload = now_server()

        while self._running:
            try:
                sleep_time = self._get_sleep_time()

                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

                await self._process_due_schedules()

                # 定期重新載入（每 60 秒）
                elapsed = (now_server() - last_reload).total_seconds()
                if elapsed >= _MAX_SLEEP_TIME:
                    await self._reload_schedules()
                    last_reload = now_server()

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
