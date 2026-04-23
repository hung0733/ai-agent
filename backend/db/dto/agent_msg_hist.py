"""Agent Message History DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from db.entity import AgentMsgHistEntity


class AgentMsgHistCreate(BaseModel):
    session_id: int
    step_id: str | None = None
    sender: str
    msg_type: str
    create_dt: datetime
    content: str
    token: int = 0
    is_stm_summary: bool = False
    is_ltm_summary: bool = False
    is_analyst: int


class AgentMsgHistResponse(BaseModel):
    id: int
    session_id: int
    step_id: str | None
    sender: str
    msg_type: str
    create_dt: datetime
    content: str
    token: int
    is_stm_summary: bool
    is_ltm_summary: bool
    is_analyst: int

    @classmethod
    def from_entity(cls, entity: AgentMsgHistEntity) -> "AgentMsgHistResponse":
        return cls(
            id=entity.id,
            session_id=entity.session_id,
            step_id=entity.step_id,
            sender=entity.sender,
            msg_type=entity.msg_type,
            create_dt=entity.create_dt,
            content=entity.content,
            token=entity.token,
            is_stm_summary=entity.is_stm_summary,
            is_ltm_summary=entity.is_ltm_summary,
            is_analyst=entity.is_analyst,
        )
