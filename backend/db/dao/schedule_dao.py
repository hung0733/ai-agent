"""Schedule DAO."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from db.dao.base import BaseDAO
from db.dto.schedule import ScheduleCreate, ScheduleUpdate
from db.entity import ScheduleEntity


class ScheduleDAO(BaseDAO[ScheduleEntity]):
    """Schedule 數據訪問對象。"""

    entity_cls = ScheduleEntity

    async def get_by_task_id(self, task_id: int) -> Optional[ScheduleEntity]:
        """根據 task_id 獲取 schedule。"""
        stmt = select(ScheduleEntity).where(ScheduleEntity.task_id == task_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_enabled_schedules(self, offset: int = 0, limit: int = 50) -> list[ScheduleEntity]:
        """獲取所有已啟用的 schedule。"""
        stmt = (
            select(ScheduleEntity)
            .where(ScheduleEntity.enabled == True)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_from_dto(self, dto: ScheduleCreate) -> ScheduleEntity:
        """從 DTO 創建 schedule。"""
        entity = ScheduleEntity(**dto.model_dump())
        return await self.create(entity)

    async def update_from_dto(self, entity: ScheduleEntity, dto: ScheduleUpdate) -> ScheduleEntity:
        """從 DTO 更新 schedule。"""
        update_data = dto.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(entity, key, value)
        return await self.update(entity)
