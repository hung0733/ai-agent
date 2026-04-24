"""LLM Level DAO."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.dao.base import BaseDAO
from db.dto.llm_level import LlmLevelCreate, LlmLevelUpdate
from db.entity import LlmLevelEntity


class LlmLevelDAO(BaseDAO[LlmLevelEntity]):
    """LlmLevel 數據訪問對象。"""

    entity_cls = LlmLevelEntity

    async def list_by_group(self, llm_group_id: int) -> list[LlmLevelEntity]:
        """根據 llm_group_id 獲取所有層級。"""
        stmt = (
            select(LlmLevelEntity)
            .where(LlmLevelEntity.llm_group_id == llm_group_id)
            .options(selectinload(LlmLevelEntity.llm_endpoint))
            .order_by(LlmLevelEntity.seq_no)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_from_dto(self, dto: LlmLevelCreate) -> LlmLevelEntity:
        """從 DTO 創建 LLM 層級。"""
        entity = LlmLevelEntity(**dto.model_dump())
        return await self.create(entity)

    async def update_from_dto(self, entity: LlmLevelEntity, dto: LlmLevelUpdate) -> LlmLevelEntity:
        """從 DTO 更新 LLM 層級。"""
        update_data = dto.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(entity, key, value)
        return await self.update(entity)
