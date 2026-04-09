"""LLM Group DAO."""

from __future__ import annotations

from sqlalchemy import select

from db.dao.base import BaseDAO
from db.dto.llm_group import LlmGroupCreate
from db.entity import LlmGroupEntity


class LlmGroupDAO(BaseDAO[LlmGroupEntity]):
    """LlmGroup 數據訪問對象。"""

    entity_cls = LlmGroupEntity

    async def list_by_user(self, user_id: int, offset: int = 0, limit: int = 50) -> list[LlmGroupEntity]:
        """列出用戶的所有 LLM 組。"""
        stmt = (
            select(LlmGroupEntity)
            .where(LlmGroupEntity.user_id == user_id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_from_dto(self, dto: LlmGroupCreate) -> LlmGroupEntity:
        """從 DTO 創建 LLM 組。"""
        entity = LlmGroupEntity(**dto.model_dump())
        return await self.create(entity)
