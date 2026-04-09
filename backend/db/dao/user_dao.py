"""User DAO."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from db.dao.base import BaseDAO
from db.dto.user import UserCreate, UserUpdate
from db.entity import UserEntity


class UserDAO(BaseDAO[UserEntity]):
    """User 數據訪問對象。"""

    entity_cls = UserEntity

    async def get_by_user_id(self, user_id: str) -> Optional[UserEntity]:
        """根據 user_id（varchar）獲取用戶。"""
        stmt = select(UserEntity).where(UserEntity.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_from_dto(self, dto: UserCreate) -> UserEntity:
        """從 DTO 創建用戶。"""
        entity = UserEntity(**dto.model_dump())
        return await self.create(entity)

    async def update_from_dto(self, entity: UserEntity, dto: UserUpdate) -> UserEntity:
        """從 DTO 更新用戶。"""
        update_data = dto.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(entity, key, value)
        return await self.update(entity)
