"""Agent DTOs."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from db.entity import AgentEntity


class AgentCreate(BaseModel):
    user_id: int
    agent_id: str = Field(..., max_length=200)
    name: str = Field(..., max_length=80)
    status: str = "idle"
    is_active: bool = True
    llm_group_id: Optional[int] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    status: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None
    llm_group_id: Optional[int] = None


class AgentResponse(BaseModel):
    id: int
    user_id: int
    agent_id: str
    name: str
    status: str
    is_active: bool
    llm_group_id: Optional[int]

    @classmethod
    def from_entity(cls, entity: AgentEntity) -> "AgentResponse":
        return cls(
            id=entity.id,
            user_id=entity.user_id,
            agent_id=entity.agent_id,
            name=entity.name,
            status=entity.status,
            is_active=entity.is_active,
            llm_group_id=entity.llm_group_id,
        )
