"""User DTOs."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from db.entity import UserEntity


class UserCreate(BaseModel):
    user_id: str = Field(..., max_length=200)
    name: str = Field(..., max_length=80)
    phoneno: Optional[str] = Field(None, max_length=20)


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    phoneno: Optional[str] = Field(None, max_length=20)


class UserResponse(BaseModel):
    id: int
    user_id: str
    name: str
    phoneno: Optional[str]

    @classmethod
    def from_entity(cls, entity: UserEntity) -> "UserResponse":
        return cls(
            id=entity.id,
            user_id=entity.user_id,
            name=entity.name,
            phoneno=entity.phoneno,
        )
