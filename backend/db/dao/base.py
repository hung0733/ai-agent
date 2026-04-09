"""Base DAO class."""

from __future__ import annotations

from typing import Generic, Optional, Type, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import Base

EntityT = TypeVar("EntityT", bound=Base)


class BaseDAO(Generic[EntityT]):
    """所有 DAO 的基礎類。"""

    entity_cls: Type[EntityT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, record_id: int) -> Optional[EntityT]:
        """根據 ID 獲取單筆記錄。"""
        return await self._session.get(self.entity_cls, record_id)

    async def get_all(self, offset: int = 0, limit: int = 50) -> list[EntityT]:
        """獲取所有記錄（分頁）。"""
        stmt = select(self.entity_cls).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """記錄總數。"""
        stmt = select(func.count()).select_from(self.entity_cls)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def create(self, entity: EntityT) -> EntityT:
        """創建新記錄。"""
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def update(self, entity: EntityT) -> EntityT:
        """更新記錄。"""
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def delete(self, entity: EntityT) -> None:
        """刪除記錄。"""
        await self._session.delete(entity)
        await self._session.flush()
