"""LLM Level DTOs."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from db.entity import LlmLevelEntity


class LlmLevelCreate(BaseModel):
    llm_group_id: int
    llm_endpoint_id: int
    level: int = 1
    is_confidential: bool = False
    seq_no: int = 1


class LlmLevelUpdate(BaseModel):
    level: Optional[int] = None
    is_confidential: Optional[bool] = None
    seq_no: Optional[int] = None


class LlmLevelResponse(BaseModel):
    id: int
    llm_group_id: int
    llm_endpoint_id: int
    level: int
    is_confidential: bool
    seq_no: int

    @classmethod
    def from_entity(cls, entity: LlmLevelEntity) -> "LlmLevelResponse":
        return cls(
            id=entity.id,
            llm_group_id=entity.llm_group_id,
            llm_endpoint_id=entity.llm_endpoint_id,
            level=entity.level,
            is_confidential=entity.is_confidential,
            seq_no=entity.seq_no,
        )
