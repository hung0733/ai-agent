"""Task DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from db.entity import TaskEntity


class TaskCreate(BaseModel):
    name: str
    task_type: str
    content: str
    agent_id: int
    parent_task_id: Optional[int] = None
    execution_order: Optional[int] = None
    required_skill: Optional[str] = None
    status: str = "pending"
    parameters: Optional[dict[str, Any]] = None
    return_message: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    next_process_dt: Optional[datetime] = None


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    task_type: Optional[str] = None
    content: Optional[str] = None
    agent_id: Optional[int] = None
    parent_task_id: Optional[int] = None
    execution_order: Optional[int] = None
    required_skill: Optional[str] = None
    status: Optional[str] = None
    parameters: Optional[dict[str, Any]] = None
    return_message: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    retry_count: Optional[int] = None
    next_process_dt: Optional[datetime] = None


class TaskResponse(BaseModel):
    id: int
    name: str
    task_type: str
    content: str
    agent_id: int
    parent_task_id: Optional[int]
    execution_order: Optional[int]
    required_skill: Optional[str]
    status: str
    parameters: Optional[dict[str, Any]]
    return_message: Optional[dict[str, Any]]
    error_message: Optional[str]
    retry_count: int
    next_process_dt: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, entity: TaskEntity) -> "TaskResponse":
        return cls(
            id=entity.id,
            name=entity.name,
            task_type=entity.task_type,
            content=entity.content,
            agent_id=entity.agent_id,
            parent_task_id=entity.parent_task_id,
            execution_order=entity.execution_order,
            required_skill=entity.required_skill,
            status=entity.status,
            parameters=entity.parameters,
            return_message=entity.return_message,
            error_message=entity.error_message,
            retry_count=entity.retry_count,
            next_process_dt=entity.next_process_dt,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
