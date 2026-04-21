"""TaskProcessor — DB task background execution loop."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Optional

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
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrent)

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

        task_ref = asyncio.create_task(self._process_task_with_semaphore(task, agent))
        task_ref.add_done_callback(
            lambda t: t.exception()
            and logger.error(_("Background task 執行錯誤：%s"), t.exception())
        )

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

            # 設 agent 為 busy，防止其他 task 被分配
            fresh_agent = await agent_dao.get_by_id(fresh_task.agent_id)
            if fresh_agent:
                fresh_agent.status = "busy"
            else:
                logger.error(_("Task %s 對應嘅 agent 不存在"), fresh_task.id)
                return

            # 設 task 為 processing
            fresh_task.status = "processing"
            await session.commit()

            logger.info(
                _("開始處理 task %s (type=%s, agent=%s)"),
                fresh_task.id,
                fresh_task.task_type,
                fresh_agent.agent_id,
            )

            try:
                # 獲取 handler
                handler = get_handler(fresh_task.task_type)
                if not handler:
                    raise ValueError(_("未知 task_type: %s") % fresh_task.task_type)

                # 執行 handler
                await handler(fresh_task, fresh_agent, session)

                # 成功 → completed
                fresh_task.status = "completed"
                fresh_task.error_message = None

                # 🌟 新增：觸發依賴解鎖邏輯
                if fresh_task.parent_task_id:
                    await self._check_and_unlock_next_order(
                        fresh_task.parent_task_id, session
                    )

            except Exception as exc:
                logger.error(_("Task %s 失敗：%s"), fresh_task.id, exc)
                await self._handle_task_failure(fresh_task, exc)
            finally:
                # 重置 agent 狀態為 idle
                fresh_agent.status = "idle"
                await session.commit()
                logger.debug(
                    _("Agent %s 已重置為 idle"),
                    fresh_agent.agent_id,
                )

    async def _check_and_unlock_next_order(
        self, parent_task_id: int, session: Any
    ) -> None:
        """
        檢查同一個 parent_task_id 下，當前 execution_order 嘅任務係咪全部做完。
        係嘅話，解鎖下一個 execution_order (由 blocked 轉為 pending)。
        """
        from db.dao.task_dao import TaskDAO

        task_dao = TaskDAO(session)

        # 1. 攞出所有 Sub-tasks (DAO 入面已經寫咗按 execution_order 排序)
        sub_tasks = await task_dao.get_sub_tasks(parent_task_id)
        if not sub_tasks:
            return

        # 2. 檢查係咪所有 sub-tasks 都 completed 晒 (成個大任務搞掂)
        all_completed = all(t.status == "completed" for t in sub_tasks)
        if all_completed:
            parent_task = await task_dao.get_by_id(parent_task_id)
            if parent_task and parent_task.status != "completed":
                parent_task.status = "completed"
                await session.commit()
                logger.info(_(f"🎉 任務流 (ID: {parent_task_id}) 已經全部完成！"))
                # 💡 日後可以在這裡喚醒 Supervisor Agent 做最終結論
            return

        # 3. 搵出目前處理緊 / 未做完嘅最細 execution_order
        current_active_order = None
        for t in sub_tasks:
            if t.status in ("pending", "processing", "failed"):
                current_active_order = t.execution_order
                break

        # 如果仲有 active 嘅任務，代表呢個 Phase 仲未搞掂，唔可以解鎖下一關
        if current_active_order is not None:
            return

        # 4. 如果目前 Phase 搞掂晒，搵出第一個 blocked 嘅 order 進行解鎖
        next_order_to_unlock = None
        for t in sub_tasks:
            if t.status == "blocked":
                next_order_to_unlock = t.execution_order
                break

        # 5. 將下一關所有任務轉做 pending
        if next_order_to_unlock is not None:
            unlocked_count = 0
            for t in sub_tasks:
                if t.execution_order == next_order_to_unlock and t.status == "blocked":
                    t.status = "pending"
                    unlocked_count += 1

            await session.commit()
            logger.info(
                _(
                    f"🔓 解鎖任務流 (ID: {parent_task_id}) Phase {next_order_to_unlock}，{unlocked_count} 個任務進入 pending 狀態！"
                )
            )

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

    async def _reset_agent_status(self, agent_id: int) -> None:
        """重置 agent 狀態為 idle。"""
        try:
            async with async_session_factory() as session:
                agent_dao = AgentDAO(session)
                agent_entity = await agent_dao.get_by_id(agent_id)
                if agent_entity:
                    agent_entity.status = "idle"
                    await session.commit()
        except Exception as exc:
            logger.error(_("重置 agent 狀態失敗：%s"), exc)
