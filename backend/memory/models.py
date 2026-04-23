"""Memory Store data models."""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.messages import BaseMessage


@dataclass
class SessionMemoryCache:
    """每個 session 嘅 RAM cache。"""
    
    session_db_id: int
    stm_messages: list[BaseMessage] = field(default_factory=list)
    old_messages: list[tuple[str, BaseMessage]] = field(default_factory=list)
    is_initialized: bool = False
