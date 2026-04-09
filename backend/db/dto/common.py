"""Common DTOs."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginationResponse(BaseModel, Generic[T]):
    """分頁響應 DTO。"""
    items: list[T]
    total: int
    offset: int
    limit: int
    has_next: bool

    @classmethod
    def create(cls, items: list[T], total: int, offset: int, limit: int) -> "PaginationResponse[T]":
        return cls(
            items=items,
            total=total,
            offset=offset,
            limit=limit,
            has_next=(offset + limit) < total,
        )
