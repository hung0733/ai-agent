"""User account entity."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class UserEntity(Base):
    """用戶帳戶實體。"""
    __tablename__ = "user_acc"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    phoneno: Mapped[Optional[str]] = mapped_column(String(20))

    # Relationships
    agents: Mapped[list["AgentEntity"]] = relationship("AgentEntity", back_populates="user")
    llm_groups: Mapped[list["LlmGroupEntity"]] = relationship("LlmGroupEntity", back_populates="user")
    llm_endpoints: Mapped[list["LlmEndpointEntity"]] = relationship("LlmEndpointEntity", back_populates="user")
