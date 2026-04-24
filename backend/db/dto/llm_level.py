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
    name: str
    endpoint: str
    enc_key: Optional[str]
    model_name: str
    max_token: int
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
            name=entity.llm_endpoint.name,
            endpoint=entity.llm_endpoint.endpoint,
            enc_key=entity.llm_endpoint.enc_key,
            model_name=entity.llm_endpoint.model_name,
            max_token=entity.llm_endpoint.max_token,
        )
