"""ScheduleManager — DB operations for the scheduler."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import joinedload

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
            .options(joinedload(ScheduleEntity.task))
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
