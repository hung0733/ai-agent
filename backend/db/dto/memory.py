"""Memory DTOs (short-term, long-term, memory block)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from db.entity import ShortTermMemEntity, LongTermMemEntity, MemoryBlockEntity


class ShortTermMemCreate(BaseModel):
    session_id: int
    content: str
    create_dt: datetime
    token: int = 0


class ShortTermMemResponse(BaseModel):
    id: int
    session_id: int
    content: str
    create_dt: datetime
    token: int

    @classmethod
    def from_entity(cls, entity: ShortTermMemEntity) -> "ShortTermMemResponse":
        return cls(
            id=entity.id,
            session_id=entity.session_id,
            content=entity.content,
            create_dt=entity.create_dt,
            token=entity.token,
        )


class LongTermMemCreate(BaseModel):
    agent_id: int
    content: str
    wing: str | None = None
    room: str | None = None
    create_dt: datetime
    token: int = 0


class LongTermMemResponse(BaseModel):
    id: int
    agent_id: int
    content: str
    wing: str | None = None
    room: str | None = None
    create_dt: datetime
    token: int

    @classmethod
    def from_entity(cls, entity: LongTermMemEntity) -> "LongTermMemResponse":
        return cls(
            id=entity.id,
            agent_id=entity.agent_id,
            content=entity.content,
            wing=entity.wing,
            room=entity.room,
            create_dt=entity.create_dt,
            token=entity.token,
        )


class MemoryBlockCreate(BaseModel):
    agent_id: int
    memory_type: str = Field(..., max_length=20)
    content: str
    last_upd_dt: datetime


class MemoryBlockUpdate(BaseModel):
    content: str
    last_upd_dt: datetime


class MemoryBlockResponse(BaseModel):
    id: int
    agent_id: int
    memory_type: str
    content: str
    last_upd_dt: datetime

    @classmethod
    def from_entity(cls, entity: MemoryBlockEntity) -> "MemoryBlockResponse":
        return cls(
            id=entity.id,
            agent_id=entity.agent_id,
            memory_type=entity.memory_type,
            content=entity.content,
            last_upd_dt=entity.last_upd_dt,
        )
