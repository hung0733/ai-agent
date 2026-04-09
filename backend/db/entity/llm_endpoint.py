"""LLM endpoint entity."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class LlmEndpointEntity(Base):
    """LLM 端點實體。"""
    __tablename__ = "llm_endpoint"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user_acc.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(400), nullable=False)
    enc_key: Mapped[Optional[str]] = mapped_column(String(200))
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    max_token: Mapped[int] = mapped_column(BigInteger, nullable=False, default=4096)

    # Relationships
    user: Mapped["UserEntity"] = relationship("UserEntity", back_populates="llm_endpoints")
    levels: Mapped[list["LlmLevelEntity"]] = relationship("LlmLevelEntity", back_populates="llm_endpoint")
