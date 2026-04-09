"""LLM level entity."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class LlmLevelEntity(Base):
    """LLM 層級實體。"""
    __tablename__ = "llm_level"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    llm_group_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("llm_group.id"), nullable=False)
    llm_endpoint_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("llm_endpoint.id"), nullable=False)
    level: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    is_confidential: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seq_no: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    # Relationships
    llm_group: Mapped["LlmGroupEntity"] = relationship("LlmGroupEntity", back_populates="levels")
    llm_endpoint: Mapped["LlmEndpointEntity"] = relationship("LlmEndpointEntity", back_populates="levels")
