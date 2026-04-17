"""Agent Message History DAO."""

from __future__ import annotations

from sqlalchemy import select, update
from typing import Optional

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

    async def list_by_thread_unsummarized(self, thread_id: str) -> list[AgentMsgHistEntity]:
        """根據 thread_id 讀取未 summary 的訊息歷史（排除 is_stm_summary=True）。"""
        stmt = (
            select(AgentMsgHistEntity)
            .where(AgentMsgHistEntity.thread_id == thread_id)
            .where(AgentMsgHistEntity.is_stm_summary == False)  # noqa: E712
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
        tool_call_id: Optional[str] = None,
    ) -> bool:
        """檢查訊息記錄是否已存在。

        對於 tool_result 類型，用 tool_call_id 去重（每個 tool_call 只對應一個 result）。
        其他類型用 checkpoint_id + content 去重。
        """
        stmt = (
            select(AgentMsgHistEntity.id)
            .where(AgentMsgHistEntity.session_id == session_id)
            .where(AgentMsgHistEntity.message_idx == message_idx)
            .where(AgentMsgHistEntity.msg_type == msg_type)
            .where(AgentMsgHistEntity.sender == sender)
        )

        if msg_type == "tool_result" and tool_call_id:
            stmt = stmt.where(AgentMsgHistEntity.tool_call_id == tool_call_id)
        else:
            stmt = stmt.where(AgentMsgHistEntity.checkpoint_id == checkpoint_id)
            stmt = stmt.where(AgentMsgHistEntity.content == content)

        stmt = stmt.limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

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
            .order_by(AgentMsgHistEntity.create_dt, AgentMsgHistEntity.message_idx, AgentMsgHistEntity.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_checkpoint_as_summarized(self, checkpoint_id: str, session_id: int) -> None:
        """將指定 checkpoint 的所有記錄標記為 is_stm_summary=True。"""
        stmt = (
            update(AgentMsgHistEntity)
            .where(AgentMsgHistEntity.session_id == session_id)
            .where(AgentMsgHistEntity.checkpoint_id == checkpoint_id)
            .values(is_stm_summary=True)
        )
        await self._session.execute(stmt)

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
