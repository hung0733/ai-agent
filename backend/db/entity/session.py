"""Session entity."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class SessionEntity(Base):
    """對話會話實體。"""
    __tablename__ = "session"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recv_agent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("agent.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False, default="預設對話")
    session_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_agent_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("agent.id"))
    is_confidential: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    recv_agent: Mapped["AgentEntity"] = relationship("AgentEntity", foreign_keys=[recv_agent_id], back_populates="sessions_recv")
    sender_agent: Mapped[Optional["AgentEntity"]] = relationship("AgentEntity", foreign_keys=[sender_agent_id], back_populates="sessions_sent")
    msg_histories: Mapped[list["AgentMsgHistEntity"]] = relationship("AgentMsgHistEntity", back_populates="session")
    short_term_mems: Mapped[list["ShortTermMemEntity"]] = relationship("ShortTermMemEntity", back_populates="session")
    long_term_mems: Mapped[list["LongTermMemEntity"]] = relationship("LongTermMemEntity", back_populates="session")
