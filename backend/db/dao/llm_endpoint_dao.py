"""LLM Endpoint DAO."""

from __future__ import annotations

from sqlalchemy import select

from db.dao.base import BaseDAO
from db.dto.llm_endpoint import LlmEndpointCreate, LlmEndpointUpdate
from db.entity import LlmEndpointEntity


class LlmEndpointDAO(BaseDAO[LlmEndpointEntity]):
    """LlmEndpoint 數據訪問對象。"""

    entity_cls = LlmEndpointEntity

    async def list_by_user(self, user_id: int, offset: int = 0, limit: int = 50) -> list[LlmEndpointEntity]:
        """列出用戶的所有 LLM 端點。"""
        stmt = (
            select(LlmEndpointEntity)
            .where(LlmEndpointEntity.user_id == user_id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_from_dto(self, dto: LlmEndpointCreate) -> LlmEndpointEntity:
        """從 DTO 創建 LLM 端點。"""
        entity = LlmEndpointEntity(**dto.model_dump())
        return await self.create(entity)

    async def update_from_dto(self, entity: LlmEndpointEntity, dto: LlmEndpointUpdate) -> LlmEndpointEntity:
        """從 DTO 更新 LLM 端點。"""
        update_data = dto.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(entity, key, value)
        return await self.update(entity)
