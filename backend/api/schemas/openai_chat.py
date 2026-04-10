"""Schemas for OpenAI-compatible chat completions."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class OpenAIChatMessage(BaseModel):
    """A minimal chat message shape compatible with OpenAI chat completions."""

    role: Literal["system", "user", "assistant"]
    content: str


class OpenAIChatCompletionRequest(BaseModel):
    """Subset of request fields used by the current queue bridge."""

    model: str
    messages: list[OpenAIChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    user: Optional[str] = None
    think_mode: Optional[bool] = None
