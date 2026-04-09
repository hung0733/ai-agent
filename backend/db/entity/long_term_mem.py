"""Long-term memory entity."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class LongTermMemEntity(Base):
    """長期記憶實體。"""
    __tablename__ = "long_term_mem"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("agent.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    create_dt: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # Relationships
    agent: Mapped["AgentEntity"] = relationship("AgentEntity", back_populates="long_term_mems")
