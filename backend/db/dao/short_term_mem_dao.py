"""Short-term Memory DAO."""

from __future__ import annotations

from sqlalchemy import select

from db.dao.base import BaseDAO
from db.dto.memory import ShortTermMemCreate
from db.entity import ShortTermMemEntity


class ShortTermMemDAO(BaseDAO[ShortTermMemEntity]):
    """ShortTermMem 數據訪問對象。"""

    entity_cls = ShortTermMemEntity

    async def list_by_session(self, session_id: int, offset: int = 0, limit: int = 50) -> list[ShortTermMemEntity]:
        """根據 session_id 獲取短期記憶。"""
        stmt = (
            select(ShortTermMemEntity)
            .where(ShortTermMemEntity.session_id == session_id)
            .order_by(ShortTermMemEntity.create_dt.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_from_dto(self, dto: ShortTermMemCreate) -> ShortTermMemEntity:
        """從 DTO 創建短期記憶。"""
        entity = ShortTermMemEntity(**dto.model_dump())
        return await self.create(entity)

    async def list_recent_by_token_limit(
        self, session_id: int, max_token: int = 10000
    ) -> list[ShortTermMemEntity]:
        """按 session_id 獲取最近的不超過 max_token 的短期記憶。

        返回按 create_dt 正序（舊到新）排列的記錄。
        """
        stmt = (
            select(ShortTermMemEntity)
            .where(ShortTermMemEntity.session_id == session_id)
            .order_by(ShortTermMemEntity.create_dt.desc())
        )
        result = await self._session.execute(stmt)
        all_records = list(result.scalars().all())

        selected: list[ShortTermMemEntity] = []
        current_token = 0
        for record in all_records:
            if current_token + record.token > max_token and selected:
                break
            selected.append(record)
            current_token += record.token

        selected.reverse()
        return selected
