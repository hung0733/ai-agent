"""Agent Message History DAO."""

from __future__ import annotations

from sqlalchemy import select

from db.dao.base import BaseDAO
from db.dto.agent_msg_hist import AgentMsgHistCreate
from db.entity import AgentMsgHistEntity


class AgentMsgHistDAO(BaseDAO[AgentMsgHistEntity]):
    """AgentMsgHist 數據訪問對象。"""

    entity_cls = AgentMsgHistEntity

    async def list_by_session(self, session_id: int, offset: int = 0, limit: int = 50) -> list[AgentMsgHistEntity]:
        """根據 session_id 獲取訊息歷史。"""
        stmt = (
            select(AgentMsgHistEntity)
            .where(AgentMsgHistEntity.session_id == session_id)
            .order_by(AgentMsgHistEntity.create_dt)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_from_dto(self, dto: AgentMsgHistCreate) -> AgentMsgHistEntity:
        """從 DTO 創建訊息記錄。"""
        entity = AgentMsgHistEntity(**dto.model_dump())
        return await self.create(entity)
