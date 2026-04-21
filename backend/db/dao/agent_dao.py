"""Agent DAO."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from db.dao.base import BaseDAO
from db.dto.agent import AgentCreate, AgentUpdate
from db.entity import AgentEntity


class AgentDAO(BaseDAO[AgentEntity]):
    """Agent 數據訪問對象。"""

    entity_cls = AgentEntity

    async def get_by_agent_id(self, agent_id: str) -> Optional[AgentEntity]:
        """根據 agent_id（varchar）獲取 agent。"""
        stmt = select(AgentEntity).where(AgentEntity.agent_id == agent_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_status(self, agent_id: str) -> Optional[str]:
        """獲取 agent 狀態。"""
        entity = await self.get_by_agent_id(agent_id)
        return entity.status if entity else None

    async def update_status(self, agent_id: str, status: str) -> bool:
        """更新 agent 狀態。

        Returns:
            True 如果成功更新，False 如果 agent 不存在。
        """
        entity = await self.get_by_agent_id(agent_id)
        if not entity:
            return False
        entity.status = status
        await self.update(entity)
        return True

    async def list_by_user(self, user_id: int, offset: int = 0, limit: int = 50) -> list[AgentEntity]:
        """列出用戶的所有 agent。"""
        stmt = (
            select(AgentEntity)
            .where(AgentEntity.user_id == user_id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_from_dto(self, dto: AgentCreate) -> AgentEntity:
        """從 DTO 創建 agent。"""
        entity = AgentEntity(**dto.model_dump())
        return await self.create(entity)

    async def update_from_dto(self, entity: AgentEntity, dto: AgentUpdate) -> AgentEntity:
        """從 DTO 更新 agent。"""
        update_data = dto.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(entity, key, value)
        return await self.update(entity)

    async def get_agents_by_skill(self, skill: str) -> list[AgentEntity]:
        """獲取具備指定技能的 agents。"""
        stmt = select(AgentEntity).where(
            AgentEntity.capabilities["skills"].contains([skill]),
            AgentEntity.is_active == True,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_idle_agents_by_skill(self, skill: str) -> list[AgentEntity]:
        """獲取具備指定技能且 idle 的 agents。"""
        stmt = select(AgentEntity).where(
            AgentEntity.capabilities["skills"].contains([skill]),
            AgentEntity.status == "idle",
            AgentEntity.is_active == True,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_available_agent(self, skill: str) -> Optional[AgentEntity]:
        """獲取最佳可用 agent（idle + 最低負載）。"""
        candidates = await self.get_idle_agents_by_skill(skill)
        if not candidates:
            return None

        # 選擇 current_tasks 最少的 agent
        return min(candidates, key=lambda a: a.current_tasks)
