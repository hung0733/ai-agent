"""TaskScheduler — heap-based schedule processor."""

from __future__ import annotations

import asyncio
import heapq
import logging
import random
from datetime import datetime, timedelta
from typing import Optional

from croniter import croniter

from db.config import async_session_factory
from db.entity import ScheduleEntity
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
        self._heap: list[tuple[datetime, ScheduleEntity]] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def _add_to_heap(self, schedule: ScheduleEntity) -> None:
        """將 schedule 加入 heap。"""
        heapq.heappush(self._heap, (schedule.next_run_at, schedule))

    def _get_due_schedules(self) -> list[ScheduleEntity]:
        """取出所有到期嘅 schedule。"""
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

        for schedule, delay in scattered:
            if delay > 0:
                logger.debug(
                    _("Schedule %s 將延遲 %.1f 秒執行"),
                    schedule.id,
                    delay,
                )
                await asyncio.sleep(delay)

            async with async_session_factory() as session:
                manager = ScheduleManager(session)

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
