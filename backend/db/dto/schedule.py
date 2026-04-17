"""Schedule DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from db.entity import ScheduleEntity


class ScheduleCreate(BaseModel):
    task_id: int
    cron_expression: str
    enabled: bool = True
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None


class ScheduleUpdate(BaseModel):
    task_id: Optional[int] = None
    cron_expression: Optional[str] = None
    enabled: Optional[bool] = None
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None


class ScheduleResponse(BaseModel):
    id: int
    task_id: int
    cron_expression: str
    enabled: bool
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, entity: ScheduleEntity) -> "ScheduleResponse":
        return cls(
            id=entity.id,
            task_id=entity.task_id,
            cron_expression=entity.cron_expression,
            enabled=entity.enabled,
            last_run_at=entity.last_run_at,
            next_run_at=entity.next_run_at,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
