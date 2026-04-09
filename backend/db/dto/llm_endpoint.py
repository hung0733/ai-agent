"""LLM Endpoint DTOs."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from db.entity import LlmEndpointEntity


class LlmEndpointCreate(BaseModel):
    user_id: int
    name: str = Field(..., max_length=80)
    endpoint: str = Field(..., max_length=400)
    enc_key: Optional[str] = Field(None, max_length=200)
    model_name: str = Field(..., max_length=200)
    max_token: int = 4096


class LlmEndpointUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    endpoint: Optional[str] = Field(None, max_length=400)
    enc_key: Optional[str] = Field(None, max_length=200)
    model_name: Optional[str] = Field(None, max_length=200)
    max_token: Optional[int] = None


class LlmEndpointResponse(BaseModel):
    id: int
    user_id: int
    name: str
    endpoint: str
    enc_key: Optional[str]
    model_name: str
    max_token: int

    @classmethod
    def from_entity(cls, entity: LlmEndpointEntity) -> "LlmEndpointResponse":
        return cls(
            id=entity.id,
            user_id=entity.user_id,
            name=entity.name,
            endpoint=entity.endpoint,
            enc_key=entity.enc_key,
            model_name=entity.model_name,
            max_token=entity.max_token,
        )
