"""Session DTOs."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from db.entity import SessionEntity


class SessionCreate(BaseModel):
    recv_agent_id: int
    session_id: str = Field(..., max_length=200)
    name: str = Field("預設對話", max_length=80)
    session_type: str = Field(..., max_length=20)
    sender_agent_id: Optional[int] = None
    is_confidential: bool = False


class SessionUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    is_confidential: Optional[bool] = None


class SessionResponse(BaseModel):
    id: int
    recv_agent_id: int
    session_id: str
    name: str
    session_type: str
    sender_agent_id: Optional[int]
    is_confidential: bool

    @classmethod
    def from_entity(cls, entity: SessionEntity) -> "SessionResponse":
        return cls(
            id=entity.id,
            recv_agent_id=entity.recv_agent_id,
            session_id=entity.session_id,
            name=entity.name,
            session_type=entity.session_type,
            sender_agent_id=entity.sender_agent_id,
            is_confidential=entity.is_confidential,
        )
