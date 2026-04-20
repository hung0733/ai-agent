"""LTM (Long-Term Memory) search functionality."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

from i18n import _

logger = logging.getLogger(__name__)


async def search_ltm(
    query: str,
    agent_id: int,
    qdrant_client: Any,
    query_vector: List[float] | None = None,
    wing: str | None = None,
    room: str | None = None,
    semantic_top_k: int = 25,
    keyword_top_k: int = 5,
    structured_top_k: int = 5,
) -> Tuple[str, List[Any]]:
    """搜索長期記憶。

    使用混合搜索策略：語義 + 關鍵字 + 結構化。

    Args:
        query: 搜索查詢
        agent_id: Agent ID
        qdrant_client: Qdrant 客戶端
        query_vector: 查詢向量（用於語義搜索）
        wing: 領域過濾（可選）
        room: 主題過濾（可選）
        semantic_top_k: 語義搜索返回數量
        keyword_top_k: 關鍵字搜索返回數量
        structured_top_k: 結構化搜索返回數量

    Returns:
        (格式化的 LTM 內容字符串, 原始結果列表)
    """
    try:
        semantic_results = await qdrant_client.search_semantic(
            query_vector=query_vector or [],
            top_k=semantic_top_k,
            agent_id=agent_id,
        )

        keyword_results = await qdrant_client.search_keyword(
            keyword=query,
            top_k=keyword_top_k,
            agent_id=agent_id,
        )

        structured_results = await qdrant_client.search_structured(
            wing=wing,
            room=room,
            agent_id=agent_id,
            top_k=structured_top_k,
        )

        all_results = _merge_and_deduplicate(
            semantic_results, keyword_results, structured_results
        )

        if not all_results:
            logger.debug(_("無 LTM 搜索結果，agent_id=%s"), agent_id)
            return "", []

        logger.info(_("找到 %s 條 LTM 相關記憶，agent_id=%s"), len(all_results), agent_id)
        return format_ltm_results(all_results), all_results

    except Exception as exc:
        logger.error(_("LTM 搜索失敗：%s"), exc)
        return "", []


def _merge_and_deduplicate(
    semantic_results: List[Any],
    keyword_results: List[Any],
    structured_results: List[Any],
) -> List[Any]:
    """合併並去重搜索結果。"""
    seen_ids = set()
    merged = []

    for results in [semantic_results, keyword_results, structured_results]:
        for point in results:
            point_id = getattr(point, "id", None) or (getattr(point, "payload", None) or {}).get("id")
            if point_id not in seen_ids:
                seen_ids.add(point_id)
                merged.append(point)

    return merged


def format_ltm_results(points: List[Any]) -> str:
    """格式化 LTM 搜索結果。

    Args:
        points: 搜索結果列表

    Returns:
        格式化的字符串
    """
    if not points:
        return ""

    lines = [_("以下是相關的長期記憶：")]
    for i, point in enumerate(points, 1):
        payload = point.payload
        wing = payload.get("wing", "Unknown")
        room = payload.get("room", "Unknown")
        content = payload.get("content", "")
        keywords = payload.get("keywords", [])

        lines.append(
            f"{i}. [{wing}/{room}] {content}"
        )
        if keywords:
            lines.append(_("   Keywords: %s") % ', '.join(keywords))

    return "\n".join(lines)


def format_ltm_results_as_json(points: List[Any]) -> List[Dict[str, str]]:
    """格式化 LTM 搜索結果為 JSON 列表。

    Args:
        points: 搜索結果列表

    Returns:
        [{"content": "...", "sendDatetime": "2026-04-17T10:00:00"}, ...]
    """
    results = []
    for point in points:
        payload = point.payload
        content = payload.get("content", "")
        send_datetime = payload.get("create_dt") or payload.get("record_dt", "")
        if content:
            results.append({
                "content": content,
                "sendDatetime": str(send_datetime),
            })
    return results
