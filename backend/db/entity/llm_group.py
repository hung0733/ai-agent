"""LLM group entity."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class LlmGroupEntity(Base):
    """LLM 模型組實體。"""
    __tablename__ = "llm_group"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user_acc.id"), nullable=False)
    name: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Relationships
    user: Mapped["UserEntity"] = relationship("UserEntity", back_populates="llm_groups")
    agents: Mapped[list["AgentEntity"]] = relationship("AgentEntity", back_populates="llm_group")
    levels: Mapped[list["LlmLevelEntity"]] = relationship("LlmLevelEntity", back_populates="llm_group")
