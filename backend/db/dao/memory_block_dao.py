"""Memory Block DAO."""

from __future__ import annotations

from sqlalchemy import select

from db.dao.base import BaseDAO
from db.dto.memory import MemoryBlockCreate, MemoryBlockUpdate
from db.entity import MemoryBlockEntity


class MemoryBlockDAO(BaseDAO[MemoryBlockEntity]):
    """MemoryBlock 數據訪問對象。"""

    entity_cls = MemoryBlockEntity

    async def list_by_agent(self, agent_id: int, memory_type: str | None = None) -> list[MemoryBlockEntity]:
        """根據 agent_id 獲取記憶區塊，可選過濾 memory_type。"""
        stmt = select(MemoryBlockEntity).where(MemoryBlockEntity.agent_id == agent_id)
        if memory_type is not None:
            stmt = stmt.where(MemoryBlockEntity.memory_type == memory_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_from_dto(self, dto: MemoryBlockCreate) -> MemoryBlockEntity:
        """從 DTO 創建記憶區塊。"""
        entity = MemoryBlockEntity(**dto.model_dump())
        return await self.create(entity)

    async def update_from_dto(self, entity: MemoryBlockEntity, dto: MemoryBlockUpdate) -> MemoryBlockEntity:
        """從 DTO 更新記憶區塊。"""
        update_data = dto.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(entity, key, value)
        return await self.update(entity)
