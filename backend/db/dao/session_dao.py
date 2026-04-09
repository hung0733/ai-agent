"""Session DAO."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from db.dao.base import BaseDAO
from db.dto.session import SessionCreate, SessionUpdate
from db.entity import SessionEntity


class SessionDAO(BaseDAO[SessionEntity]):
    """Session 數據訪問對象。"""

    entity_cls = SessionEntity

    async def get_by_session_id(self, session_id: str) -> Optional[SessionEntity]:
        """根據 session_id（varchar）獲取會話。"""
        stmt = select(SessionEntity).where(SessionEntity.session_id == session_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_agent(self, agent_id: int, offset: int = 0, limit: int = 50) -> list[SessionEntity]:
        """列出 agent 的所有會話。"""
        stmt = (
            select(SessionEntity)
            .where(SessionEntity.recv_agent_id == agent_id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_from_dto(self, dto: SessionCreate) -> SessionEntity:
        """從 DTO 創建會話。"""
        entity = SessionEntity(**dto.model_dump())
        return await self.create(entity)

    async def update_from_dto(self, entity: SessionEntity, dto: SessionUpdate) -> SessionEntity:
        """從 DTO 更新會話。"""
        update_data = dto.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(entity, key, value)
        return await self.update(entity)
