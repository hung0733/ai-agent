"""Long-term Memory DAO."""

from __future__ import annotations

from sqlalchemy import select

from db.dao.base import BaseDAO
from db.dto.memory import LongTermMemCreate
from db.entity import LongTermMemEntity


class LongTermMemDAO(BaseDAO[LongTermMemEntity]):
    """LongTermMem 數據訪問對象。"""

    entity_cls = LongTermMemEntity

    async def list_by_agent(self, agent_id: int, offset: int = 0, limit: int = 50) -> list[LongTermMemEntity]:
        """根據 agent_id 獲取長期記憶。"""
        stmt = (
            select(LongTermMemEntity)
            .where(LongTermMemEntity.agent_id == agent_id)
            .order_by(LongTermMemEntity.create_dt.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent_by_session(self, session_id: int, limit: int = 3) -> list[LongTermMemEntity]:
        """根據 session_id 獲取最近 N 筆長期記憶。"""
        stmt = (
            select(LongTermMemEntity)
            .where(LongTermMemEntity.session_id == session_id)
            .order_by(LongTermMemEntity.create_dt.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_from_dto(self, dto: LongTermMemCreate) -> LongTermMemEntity:
        """從 DTO 創建長期記憶。"""
        entity = LongTermMemEntity(**dto.model_dump())
        return await self.create(entity)
