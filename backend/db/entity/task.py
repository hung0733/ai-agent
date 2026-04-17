"""Task entity."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class TaskEntity(Base):
    """Task 實體。"""

    __tablename__ = "task"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    agent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("agent.id"), nullable=False)
    parent_task_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("task.id"))
    execution_order: Mapped[Optional[int]] = mapped_column(Integer)
    required_skill: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    parameters: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    return_message: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_process_dt: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    agent: Mapped["AgentEntity"] = relationship("AgentEntity", back_populates="tasks")
    schedule: Mapped[Optional["ScheduleEntity"]] = relationship("ScheduleEntity", back_populates="task", uselist=False)
    sub_tasks: Mapped[list["TaskEntity"]] = relationship("TaskEntity", back_populates="parent_task")
    parent_task: Mapped[Optional["TaskEntity"]] = relationship("TaskEntity", remote_side=[id], back_populates="sub_tasks")
