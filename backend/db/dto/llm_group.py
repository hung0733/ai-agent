"""LLM Group DTOs."""

from __future__ import annotations

from pydantic import BaseModel

from db.entity import LlmGroupEntity


class LlmGroupCreate(BaseModel):
    user_id: int
    name: int


class LlmGroupResponse(BaseModel):
    id: int
    user_id: int
    name: int

    @classmethod
    def from_entity(cls, entity: LlmGroupEntity) -> "LlmGroupResponse":
        return cls(
            id=entity.id,
            user_id=entity.user_id,
            name=entity.name,
        )
