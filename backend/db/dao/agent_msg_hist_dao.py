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

    async def get_latest_checkpoint_id(self, thread_id: str) -> str | None:
        """獲取 thread 最新 checkpoint_id。"""
        stmt = (
            select(AgentMsgHistEntity.checkpoint_id)
            .where(AgentMsgHistEntity.thread_id == thread_id)
            .order_by(AgentMsgHistEntity.create_dt.desc(), AgentMsgHistEntity.id.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_thread_checkpoint(
        self,
        thread_id: str,
        checkpoint_id: str,
    ) -> list[AgentMsgHistEntity]:
        """根據 thread_id + checkpoint_id 讀取訊息歷史。"""
        stmt = (
            select(AgentMsgHistEntity)
            .where(AgentMsgHistEntity.thread_id == thread_id)
            .where(AgentMsgHistEntity.checkpoint_id == checkpoint_id)
            .order_by(AgentMsgHistEntity.message_idx, AgentMsgHistEntity.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_thread(self, thread_id: str) -> list[AgentMsgHistEntity]:
        """根據 thread_id 讀取完整訊息歷史。"""
        stmt = (
            select(AgentMsgHistEntity)
            .where(AgentMsgHistEntity.thread_id == thread_id)
            .order_by(
                AgentMsgHistEntity.create_dt,
                AgentMsgHistEntity.message_idx,
                AgentMsgHistEntity.id,
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def exists_message(
        self,
        session_id: int,
        checkpoint_id: str,
        message_idx: int,
        msg_type: str,
        sender: str,
        content: str,
    ) -> bool:
        """檢查訊息記錄是否已存在。"""
        stmt = (
            select(AgentMsgHistEntity.id)
            .where(AgentMsgHistEntity.session_id == session_id)
            .where(AgentMsgHistEntity.checkpoint_id == checkpoint_id)
            .where(AgentMsgHistEntity.message_idx == message_idx)
            .where(AgentMsgHistEntity.msg_type == msg_type)
            .where(AgentMsgHistEntity.sender == sender)
            .where(AgentMsgHistEntity.content == content)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create_from_dto(self, dto: AgentMsgHistCreate) -> AgentMsgHistEntity:
        """從 DTO 創建訊息記錄。"""
        entity = AgentMsgHistEntity(**dto.model_dump())
        return await self.create(entity)
