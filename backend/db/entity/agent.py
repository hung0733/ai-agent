"""Agent entity."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Any

if TYPE_CHECKING:
    from db.entity.task import TaskEntity

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class AgentEntity(Base):
    """Agent 實體。"""
    __tablename__ = "agent"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user_acc.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="idle")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    llm_group_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("llm_group.id"))
    capabilities: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, default=dict)
    current_tasks: Mapped[int] = mapped_column(Integer, default=0)
    agent_type: Mapped[str] = mapped_column(String(20), nullable=False, default="agent")

    # Relationships
    user: Mapped["UserEntity"] = relationship("UserEntity", back_populates="agents")
    llm_group: Mapped[Optional["LlmGroupEntity"]] = relationship("LlmGroupEntity", back_populates="agents")
    sessions_recv: Mapped[list["SessionEntity"]] = relationship(
        "SessionEntity", foreign_keys="SessionEntity.recv_agent_id", back_populates="recv_agent"
    )
    sessions_sent: Mapped[list["SessionEntity"]] = relationship(
        "SessionEntity", foreign_keys="SessionEntity.sender_agent_id", back_populates="sender_agent"
    )
    long_term_mems: Mapped[list["LongTermMemEntity"]] = relationship("LongTermMemEntity", back_populates="agent")
    memory_blocks: Mapped[list["MemoryBlockEntity"]] = relationship("MemoryBlockEntity", back_populates="agent")
    tasks: Mapped[list["TaskEntity"]] = relationship("TaskEntity", back_populates="agent")
