"""Memory block entity."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class MemoryBlockEntity(Base):
    """記憶區塊實體。"""
    __tablename__ = "memory_block"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("agent.id"), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    last_upd_dt: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    agent: Mapped["AgentEntity"] = relationship("AgentEntity", back_populates="memory_blocks")
