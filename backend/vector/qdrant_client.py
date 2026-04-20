"""Qdrant vector database client."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from qdrant_client import AsyncQdrantClient, models

from i18n import _

logger = logging.getLogger(__name__)


class QdrantClient:
    """Qdrant 向量數據庫客戶端。"""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        api_key: Optional[str] = None,
        collection_name: Optional[str] = None,
    ):
        """初始化 Qdrant 客戶端。

        Args:
            host: Qdrant 主機地址
            port: Qdrant 端口
            api_key: API 密鑰（可選）
            collection_name: 集合名稱
        """
        self.host = host or os.getenv("QDRANT_HOST", "localhost")
        self.port = port or int(os.getenv("QDRANT_PORT", "6333"))
        self.api_key = api_key or os.getenv("QDRANT_API_KEY")
        self.collection_name = collection_name or os.getenv(
            "QDRANT_LTM_COLLECTION", "simplemem_memories",
        )

        self.client = AsyncQdrantClient(
            host=self.host,
            port=self.port,
            api_key=self.api_key if self.api_key else None,
        )

    async def ensure_collection(self, vector_size: int = 2560) -> None:
        """確保集合存在，不存在則創建。

        同時確保 keyword 索引存在。

        Args:
            vector_size: 向量維度
        """
        try:
            collections = await self.client.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self.collection_name not in collection_names:
                logger.info(_("創建 Qdrant 集合：%s"), self.collection_name)
                await self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE,
                    ),
                )

            # 創建 keyword 索引用於 BM25 搜索（獨立於集合創建）
            await self._ensure_keyword_index()

        except Exception as exc:
            logger.error(_("確保 Qdrant 集合失敗：%s"), exc)
            raise

    async def _ensure_keyword_index(self) -> None:
        """確保 keyword 文本索引存在。"""
        try:
            await self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="keywords",
                field_schema=models.TextIndexParams(
                    type="text",
                    tokenizer="word",
                    min_token_len=2,
                    max_token_len=20,
                    lowercase=True,
                ),
            )
        except Exception as exc:
            # 索引可能已存在，忽略錯誤
            logger.debug(_("創建 keyword 索引時出錯（可能已存在）：%s"), exc)

    async def upsert_points(self, points: List[Dict[str, Any]]) -> Dict[str, Any]:
        """寫入向量點。

        Args:
            points: 向量點列表，每個點包含 id, vector, payload

        Returns:
            操作結果

        Raises:
            RuntimeError: 當 upsert 操作失敗時
        """
        qdrant_points = []
        for point in points:
            qdrant_points.append(
                models.PointStruct(
                    id=point["id"],
                    vector=point["vector"],
                    payload=point["payload"],
                )
            )

        try:
            result = await self.client.upsert(
                collection_name=self.collection_name,
                points=qdrant_points,
            )
        except Exception as exc:
            logger.error(_("Qdrant upsert 失敗：%s"), exc)
            raise

        if result.status != models.UpdateStatus.COMPLETED:
            error_msg = _("Qdrant upsert 失敗：狀態=%s") % getattr(
                result, "status", "unknown",
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info(_("寫入 %s 個向量點到 Qdrant"), len(points))
        return {"status": "ok", "count": len(points)}

    async def search_semantic(
        self,
        query_vector: List[float],
        top_k: int = 25,
        agent_id: Optional[int] = None,
        wing: Optional[str] = None,
        room: Optional[str] = None,
    ) -> List[Any]:
        """語義搜索（向量相似度）。

        Args:
            query_vector: 查詢向量
            top_k: 返回結果數量
            agent_id: 過濾特定 agent（可選）
            wing: 領域過濾（可選）
            room: 主題過濾（可選）

        Returns:
            搜索結果列表
        """
        conditions = []
        if agent_id is not None:
            conditions.append(
                models.FieldCondition(
                    key="agent_id",
                    match=models.MatchValue(value=agent_id),
                )
            )
        if wing is not None:
            conditions.append(
                models.FieldCondition(
                    key="wing",
                    match=models.MatchValue(value=wing),
                )
            )
        if room is not None:
            conditions.append(
                models.FieldCondition(
                    key="room",
                    match=models.MatchValue(value=room),
                )
            )

        query_filter = models.Filter(must=conditions) if conditions else None

        try:
            results = await self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
            )
        except Exception as exc:
            logger.error(_("Qdrant 語義搜索失敗：%s"), exc)
            raise
        return results.points

    async def search_keyword(
        self,
        keyword: str,
        top_k: int = 5,
        agent_id: Optional[int] = None,
        wing: Optional[str] = None,
        room: Optional[str] = None,
    ) -> List[Any]:
        """關鍵字搜索（BM25）。

        Args:
            keyword: 搜索關鍵字
            top_k: 返回結果數量
            agent_id: 過濾特定 agent（可選）
            wing: 領域過濾（可選）
            room: 主題過濾（可選）

        Returns:
            搜索結果列表
        """
        conditions = [
            models.FieldCondition(
                key="keywords",
                match=models.MatchText(text=keyword),
            )
        ]
        if agent_id is not None:
            conditions.append(
                models.FieldCondition(
                    key="agent_id",
                    match=models.MatchValue(value=agent_id),
                )
            )
        if wing is not None:
            conditions.append(
                models.FieldCondition(
                    key="wing",
                    match=models.MatchValue(value=wing),
                )
            )
        if room is not None:
            conditions.append(
                models.FieldCondition(
                    key="room",
                    match=models.MatchValue(value=room),
                )
            )

        query_filter = models.Filter(must=conditions)

        try:
            results = await self.client.query_points(
                collection_name=self.collection_name,
                query_filter=query_filter,
                limit=top_k,
            )
        except Exception as exc:
            logger.error(_("Qdrant 關鍵字搜索失敗：%s"), exc)
            raise
        return results.points
