"""TaskProcessor — DB task background execution loop."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Optional

from db.config import async_session_factory
from db.dao.agent_dao import AgentDAO
from db.dao.task_dao import TaskDAO
from db.entity import AgentEntity, TaskEntity
from i18n import _
from task_processor.handlers import get_handler
from task_processor.utils import calculate_retry_delay
from utils.timezone import now_server

logger = logging.getLogger(__name__)


class TaskProcessor:
    """DB task 背景執行器。

    每秒 poll DB 一次，搵 pending task + idle agent，
    按 task_type 分派 handler 執行。

    Args:
        max_concurrent: 最大同時處理 task 數。
    """

    def __init__(self, max_concurrent: int = 5) -> None:
        self.max_concurrent = max_concurrent
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def start(self) -> None:
        """啟動 background loop。"""
        if self._running:
            logger.warning(_("TaskProcessor 已經在運行"))
            return

        self._running = True
        self._task = asyncio.create_task(self._main_loop(), name="task-processor")
        logger.info(_("TaskProcessor 已啟動 (max_concurrent=%d)"), self.max_concurrent)

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
        logger.info(_("TaskProcessor 已停止"))

    async def _main_loop(self) -> None:
        """主循環：每秒 poll 一次。"""
        logger.info(_("TaskProcessor 主循環已啟動"))
        while self._running:
            try:
                await self._poll_and_process()
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(_("TaskProcessor 循環錯誤：%s"), exc)
                await asyncio.sleep(5)
        logger.info(_("TaskProcessor 主循環已停止"))

    async def _poll_and_process(self) -> None:
        """單次 poll + 處理邏輯。"""
        async with async_session_factory() as session:
            task_dao = TaskDAO(session)
            result = await task_dao.get_next_pending_task()

        if not result:
            return

        task, agent = result
        logger.debug(
            _("發現 pending task %s (agent=%s)"),
            task.id,
            agent.agent_id,
        )

        asyncio.create_task(self._process_task_with_semaphore(task, agent))

    async def _process_task_with_semaphore(
        self, task: TaskEntity, agent: AgentEntity
    ) -> None:
        """用 semaphore 控制併發執行 task。"""
        async with self._semaphore:
            await self._process_task(task, agent)

    async def _process_task(self, task: TaskEntity, agent: AgentEntity) -> None:
        """處理單個 task。"""
        async with async_session_factory() as session:
            task_dao = TaskDAO(session)
            agent_dao = AgentDAO(session)

            # 重新載入 task（確保 session 正確）
            fresh_task = await task_dao.get_by_id(task.id)
            if not fresh_task:
                logger.warning(_("Task %s 已不存在，跳過"), task.id)
                return

            # 設為 processing
            fresh_task.status = "processing"
            await session.commit()

            logger.info(
                _("開始處理 task %s (type=%s, agent=%s)"),
                fresh_task.id,
                fresh_task.task_type,
                agent.agent_id,
            )

            try:
                # 獲取 handler
                handler = get_handler(fresh_task.task_type)
                if not handler:
                    raise ValueError(_("未知 task_type: %s"), fresh_task.task_type)

                # 執行 handler
                await handler(fresh_task, agent, session)

                # 成功 → completed
                fresh_task.status = "completed"
                fresh_task.error_message = None
                await session.commit()

                logger.info(_("Task %s 已完成"), fresh_task.id)

            except Exception as exc:
                logger.error(_("Task %s 失敗：%s"), fresh_task.id, exc)
                await self._handle_task_failure(fresh_task, exc)
            finally:
                # 重置 agent 狀態
                await self._reset_agent_status(agent_dao, fresh_task.agent_id)

    async def _handle_task_failure(self, task: TaskEntity, exc: Exception) -> None:
        """處理 task 失敗，計算重試 delay。"""
        async with async_session_factory() as session:
            task_dao = TaskDAO(session)
            fresh_task = await task_dao.get_by_id(task.id)
            if not fresh_task:
                return

            delay = calculate_retry_delay(fresh_task.retry_count + 1)
            fresh_task.retry_count += 1
            fresh_task.status = "pending"
            fresh_task.error_message = str(exc)
            fresh_task.next_process_dt = now_server() + timedelta(seconds=delay)
            await session.commit()

            logger.warning(
                _("Task %s 失敗（第 %d 次），%d 秒後重試：%s"),
                fresh_task.id,
                fresh_task.retry_count,
                delay,
                exc,
            )

    async def _reset_agent_status(self, agent_dao: AgentDAO, agent_id: int) -> None:
        """重置 agent 狀態為 idle。"""
        try:
            agent_entity = await agent_dao.get_by_id(agent_id)
            if agent_entity:
                agent_entity.status = "idle"
                await agent_dao._session.commit()
        except Exception as exc:
            logger.error(_("重置 agent 狀態失敗：%s"), exc)
