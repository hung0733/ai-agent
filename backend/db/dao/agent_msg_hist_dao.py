"""Agent Message History DAO."""

from __future__ import annotations

from sqlalchemy import select, update

from db.dao.base import BaseDAO
from db.dto.agent_msg_hist import AgentMsgHistCreate
from db.entity import AgentEntity, AgentMsgHistEntity, SessionEntity


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

    async def list_unsummarized_by_session(self, session_id: int) -> list[AgentMsgHistEntity]:
        """獲取 session 中所有 is_stm_summary=False 的記錄（按 create_dt 排序）。"""
        stmt = (
            select(AgentMsgHistEntity)
            .where(AgentMsgHistEntity.session_id == session_id)
            .where(AgentMsgHistEntity.is_stm_summary == False)  # noqa: E712
            .order_by(AgentMsgHistEntity.create_dt, AgentMsgHistEntity.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_records_as_summarized(
        self,
        record_ids: list[int],
        session_id: int,
    ) -> None:
        """按記錄 ID 列表標記為 is_stm_summary=True。

        Args:
            record_ids: 記錄 ID 列表。
            session_id: Session ID。
        """
        if not record_ids:
            return

        stmt = (
            update(AgentMsgHistEntity)
            .where(AgentMsgHistEntity.session_id == session_id)
            .where(AgentMsgHistEntity.id.in_(record_ids))
            .values(is_stm_summary=True)
        )
        await self._session.execute(stmt)

    async def list_unsummarized_for_ltm(self, agent_id: str) -> list[AgentMsgHistEntity]:
        """列出指定 agent 未 LTM 總結的記錄。

        Args:
            agent_id: Agent ID（業務 ID，如 "agent-xxx"）

        Returns:
            未總結的記錄列表
        """
        stmt = (
            select(AgentMsgHistEntity)
            .join(SessionEntity, AgentMsgHistEntity.session_id == SessionEntity.id)
            .join(AgentEntity, SessionEntity.recv_agent_id == AgentEntity.id)
            .where(
                AgentEntity.agent_id == agent_id,
                AgentMsgHistEntity.is_ltm_summary == False,  # noqa: E712
            )
            .order_by(AgentMsgHistEntity.session_id, AgentMsgHistEntity.create_dt)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_records_as_ltm_summarized(self, record_ids: list[int]) -> None:
        """標記記錄為已 LTM 總結。

        Args:
            record_ids: 記錄 ID 列表
        """
        if not record_ids:
            return

        stmt = (
            update(AgentMsgHistEntity)
            .where(AgentMsgHistEntity.id.in_(record_ids))
            .values(is_ltm_summary=True)
        )
        await self._session.execute(stmt)

    async def list_unanalyzed_for_review(self, agent_id: str) -> list[AgentMsgHistEntity]:
        """列出指定 agent 未分析（is_analyst=0）的記錄。

        Args:
            agent_id: Agent ID（業務 ID，如 "agent-xxx"）

        Returns:
            未分析的記錄列表
        """
        stmt = (
            select(AgentMsgHistEntity)
            .join(SessionEntity, AgentMsgHistEntity.session_id == SessionEntity.id)
            .join(AgentEntity, SessionEntity.recv_agent_id == AgentEntity.id)
            .where(
                AgentEntity.agent_id == agent_id,
                AgentMsgHistEntity.is_analyst == 0,
            )
            .order_by(AgentMsgHistEntity.session_id, AgentMsgHistEntity.create_dt)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_records_as_analyzed(self, record_ids: list[int]) -> None:
        """標記記錄為已分析（is_analyst=1）。

        Args:
            record_ids: 記錄 ID 列表
        """
        if not record_ids:
            return

        stmt = (
            update(AgentMsgHistEntity)
            .where(AgentMsgHistEntity.id.in_(record_ids))
            .values(is_analyst=1)
        )
        await self._session.execute(stmt)
