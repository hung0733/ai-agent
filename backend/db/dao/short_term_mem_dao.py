"""Short-term Memory DAO."""

from __future__ import annotations

from sqlalchemy import select

from db.dao.base import BaseDAO
from db.dto.memory import ShortTermMemCreate
from db.entity import ShortTermMemEntity


class ShortTermMemDAO(BaseDAO[ShortTermMemEntity]):
    """ShortTermMem 數據訪問對象。"""

    entity_cls = ShortTermMemEntity

    async def list_by_session(self, session_id: int, offset: int = 0, limit: int = 50) -> list[ShortTermMemEntity]:
        """根據 session_id 獲取短期記憶。"""
        stmt = (
            select(ShortTermMemEntity)
            .where(ShortTermMemEntity.session_id == session_id)
            .order_by(ShortTermMemEntity.create_dt.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_from_dto(self, dto: ShortTermMemCreate) -> ShortTermMemEntity:
        """從 DTO 創建短期記憶。"""
        entity = ShortTermMemEntity(**dto.model_dump())
        return await self.create(entity)
