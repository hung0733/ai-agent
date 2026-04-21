"""Task DAO."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from db.dao.base import BaseDAO
from db.dto.task import TaskCreate, TaskUpdate
from db.entity import AgentEntity, TaskEntity
from utils.timezone import now_server


class TaskDAO(BaseDAO[TaskEntity]):
    """Task 數據訪問對象。"""

    entity_cls = TaskEntity

    async def get_by_agent_id(self, agent_id: int, offset: int = 0, limit: int = 50) -> list[TaskEntity]:
        """獲取指定 agent 的所有 task。"""
        stmt = (
            select(TaskEntity)
            .where(TaskEntity.agent_id == agent_id)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_sub_tasks(self, parent_task_id: int) -> list[TaskEntity]:
        """獲取指定父任務的所有子任務（按 execution_order 排序）。"""
        stmt = (
            select(TaskEntity)
            .where(TaskEntity.parent_task_id == parent_task_id)
            .order_by(TaskEntity.execution_order)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_tasks(self, limit: int = 50) -> list[TaskEntity]:
        """獲取所有 pending 狀態嘅 task。"""
        stmt = (
            select(TaskEntity)
            .where(TaskEntity.status == "pending")
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_next_pending_task(self) -> Optional[tuple[TaskEntity, AgentEntity]]:
        """獲取下一個可執行嘅 pending task 同對應 agent（必須 idle）。

        Returns:
            (TaskEntity, AgentEntity) tuple，或者 None。
            同時考慮 next_process_dt（重試 delay）。
        """
        stmt = (
            select(TaskEntity, AgentEntity)
            .join(AgentEntity, TaskEntity.agent_id == AgentEntity.id)
            .where(
                TaskEntity.status == "pending",
                AgentEntity.status == "idle",
                (TaskEntity.next_process_dt.is_(None))
                | (TaskEntity.next_process_dt <= now_server()),
            )
            .order_by(TaskEntity.created_at)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.first()
        if row:
            return row[0], row[1]  # (task, agent)
        return None

    async def create_from_dto(self, dto: TaskCreate) -> TaskEntity:
        """從 DTO 創建 task。"""
        entity = TaskEntity(**dto.model_dump())
        return await self.create(entity)

    async def update_from_dto(self, entity: TaskEntity, dto: TaskUpdate) -> TaskEntity:
        """從 DTO 更新 task。"""
        update_data = dto.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(entity, key, value)
        return await self.update(entity)

    async def get_sub_tasks_by_parent(self, parent_task_id: int) -> list[TaskEntity]:
        """獲取指定父任務的所有子任務（按 execution_order 排序）。"""
        stmt = (
            select(TaskEntity)
            .where(TaskEntity.parent_task_id == parent_task_id)
            .order_by(TaskEntity.execution_order, TaskEntity.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_completed_sub_tasks(self, parent_task_id: int) -> list[TaskEntity]:
        """獲取已完成嘅 sub-tasks。"""
        stmt = (
            select(TaskEntity)
            .where(
                TaskEntity.parent_task_id == parent_task_id,
                TaskEntity.status == "completed",
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_failed_sub_tasks(self, parent_task_id: int) -> list[TaskEntity]:
        """獲取失敗嘅 sub-tasks。"""
        stmt = (
            select(TaskEntity)
            .where(
                TaskEntity.parent_task_id == parent_task_id,
                TaskEntity.status == "failed",
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def are_all_sub_tasks_completed(self, parent_task_id: int) -> bool:
        """檢查所有 sub-tasks 是否已完成。"""
        sub_tasks = await self.get_sub_tasks_by_parent(parent_task_id)
        if not sub_tasks:
            return False
        return all(t.status == "completed" for t in sub_tasks)
