"""Agent Message History DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from db.entity import AgentMsgHistEntity


class AgentMsgHistCreate(BaseModel):
    session_id: int
    thread_id: str
    checkpoint_id: str
    message_idx: int
    sender: str
    msg_type: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    create_dt: datetime
    content: str
    payload_json: str
    token: int = 0
    is_stm_summary: bool = False
    is_ltm_summary: bool = False
    is_analyst: int


class AgentMsgHistResponse(BaseModel):
    id: int
    session_id: int
    thread_id: str
    checkpoint_id: str
    message_idx: int
    sender: str
    msg_type: str
    tool_call_id: str | None
    tool_name: str | None
    create_dt: datetime
    content: str
    payload_json: str
    token: int
    is_stm_summary: bool
    is_ltm_summary: bool
    is_analyst: int

    @classmethod
    def from_entity(cls, entity: AgentMsgHistEntity) -> "AgentMsgHistResponse":
        return cls(
            id=entity.id,
            session_id=entity.session_id,
            thread_id=entity.thread_id,
            checkpoint_id=entity.checkpoint_id,
            message_idx=entity.message_idx,
            sender=entity.sender,
            msg_type=entity.msg_type,
            tool_call_id=entity.tool_call_id,
            tool_name=entity.tool_name,
            create_dt=entity.create_dt,
            content=entity.content,
            payload_json=entity.payload_json,
            token=entity.token,
            is_stm_summary=entity.is_stm_summary,
            is_ltm_summary=entity.is_ltm_summary,
            is_analyst=entity.is_analyst,
        )
