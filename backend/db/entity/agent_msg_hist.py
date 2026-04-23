"""Agent message history entity."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class AgentMsgHistEntity(Base):
    """Agent 訊息歷史實體。"""
    __tablename__ = "agent_msg_hist"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("session.id"), nullable=False)
    step_id: Mapped[str | None] = mapped_column(String(200))
    sender: Mapped[str] = mapped_column(String(80), nullable=False)
    msg_type: Mapped[str] = mapped_column(String(20), nullable=False)
    create_dt: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    is_stm_summary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_ltm_summary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_analyst: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Relationships
    session: Mapped["SessionEntity"] = relationship("SessionEntity", back_populates="msg_histories")
