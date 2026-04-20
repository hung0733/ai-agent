"""LTM (Long-Term Memory) search functionality."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Tuple

from i18n import _

logger = logging.getLogger(__name__)


def _get_embedding_model():
    """獲取 embedding 模型。"""
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        openai_api_base=os.getenv("EMBEDDING_LLM_ENDPOINT"),
        openai_api_key=os.getenv("EMBEDDING_LLM_API_KEY", ""),
        model=os.getenv("EMBEDDING_LLM_MODEL", "text-embedding-3-small"),
        dimensions=int(os.getenv("EMBEDDING_DIMENSION", "2560")),
    )


def _get_routing_llm():
    """獲取 ROUTING_LLM 用於查詢重寫。"""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        openai_api_base=os.getenv("ROUTING_LLM_ENDPOINT"),
        openai_api_key=os.getenv("ROUTING_LLM_API_KEY", ""),
        model=os.getenv("ROUTING_LLM_MODEL", "qwen3.5-4b"),
        temperature=0,
    )


async def _get_existing_taxonomy_by_agent(agent_id: int) -> str:
    """從 PostgreSQL long_term_mem 表獲取指定 agent 的現有 wing/room 分類。

    Returns:
        JSON 字符串：{"Personal": ["Health", "Hobbies"], "Project": ["Database", ...]}
    """
    from db.config import async_session_factory
    from db.dao.long_term_mem_dao import LongTermMemDAO

    async with async_session_factory() as session:
        dao = LongTermMemDAO(session)
        memories = await dao.list_by_agent(agent_id, limit=1000)

    taxonomy: Dict[str, set] = {}
    for mem in memories:
        wing = mem.wing or "Unknown"
        room = mem.room or "Unknown"
        if wing not in taxonomy:
            taxonomy[wing] = set()
        taxonomy[wing].add(room)

    return json.dumps({k: sorted(list(v)) for k, v in taxonomy.items()})


async def search_ltm_for_chat(
    user_query: str,
    session_db_id: str,
) -> str:
    """為聊天界面執行完整的 LTM 搜索流程。

    包括：查詢重寫 → 生成 embedding → 混合搜索 → 格式化為 JSON。

    Args:
        user_query: 用戶原始查詢
        session_db_id: 會話數據庫 ID

    Returns:
        JSON 數組字符串（無結果時返回空字符串）：
        '[{"content": "...", "sendDatetime": "..."}, ...]'
    """
    from backend.agent.prompt import LTM_QUERY_REWRITE_PROMPT_TEMPLATE
    from backend.vector.qdrant_client import QdrantClient
    from db.config import async_session_factory
    from db.dao.session_dao import SessionDAO

    async with async_session_factory() as db_session:
        session_dao = SessionDAO(db_session)
        session = await session_dao.get_by_id(session_db_id)
        if not session:
            return ""

        agent_id = session.recv_agent_id

        # 1. 獲取 ROUTING_LLM 並重寫查詢
        routing_llm = _get_routing_llm()
        qdrant_client = QdrantClient()
        await qdrant_client.ensure_collection(
            vector_size=int(os.getenv("EMBEDDING_DIMENSION", "2560"))
        )

        existing_taxonomy = await _get_existing_taxonomy_by_agent(agent_id)
        rewrite_prompt = LTM_QUERY_REWRITE_PROMPT_TEMPLATE.format(
            existing_taxonomy_json=existing_taxonomy,
            user_query=user_query,
        )

        rewrite_response = await routing_llm.ainvoke(rewrite_prompt)
        rewrite_content = rewrite_response.content
        # 清理可能的 markdown 代碼塊
        if rewrite_content.startswith("```"):
            rewrite_content = rewrite_content.split("```")[1]
            if rewrite_content.startswith("json"):
                rewrite_content = rewrite_content[4:]
        rewrite_content = rewrite_content.strip()

        query_params = json.loads(rewrite_content)

        domain_wing = query_params.get("domain_wing")
        topic_room = query_params.get("topic_room")
        keywords = query_params.get("keywords", [])

        # 如果 room 是 "ANY"，設為 None（擴大搜索）
        if topic_room == "ANY":
            topic_room = None

        # 2. 用 keywords 生成 embedding
        embedding_model = _get_embedding_model()
        query_embedding = await embedding_model.aembed_query(" ".join(keywords))

        # 3. 搜索 LTM（傳入 wing/room/agent_id）
        ltm_results_text, ltm_points = await search_ltm(
            query=" ".join(keywords),
            agent_id=agent_id,
            qdrant_client=qdrant_client,
            query_vector=query_embedding,
            wing=domain_wing,
            room=topic_room,
            semantic_top_k=5,
            keyword_top_k=5,
            structured_top_k=5,
        )

        # 4. 格式化為 JSON 數組
        if not ltm_points:
            return ""

        ltm_json_list = format_ltm_results_as_json(ltm_points)[:5]
        return json.dumps(ltm_json_list, ensure_ascii=False, indent=2)


async def search_ltm(
    query: str,
    agent_id: int,
    qdrant_client: Any,
    query_vector: List[float] | None = None,
    wing: str | None = None,
    room: str | None = None,
    semantic_top_k: int = 25,
    keyword_top_k: int = 5,
) -> Tuple[str, List[Any]]:
    """搜索長期記憶。

    使用混合搜索策略：語義 + 關鍵字。

    Args:
        query: 搜索查詢
        agent_id: Agent ID
        qdrant_client: Qdrant 客戶端
        query_vector: 查詢向量（用於語義搜索）
        wing: 領域過濾（可選）
        room: 主題過濾（可選）
        semantic_top_k: 語義搜索返回數量
        keyword_top_k: 關鍵字搜索返回數量

    Returns:
        (格式化的 LTM 內容字符串, 原始結果列表)
    """
    try:
        semantic_results = await qdrant_client.search_semantic(
            query_vector=query_vector or [],
            top_k=semantic_top_k,
            agent_id=agent_id,
            wing=wing,
            room=room,
        )

        keyword_results = await qdrant_client.search_keyword(
            keyword=query,
            top_k=keyword_top_k,
            agent_id=agent_id,
            wing=wing,
            room=room,
        )

        all_results = _merge_and_deduplicate(
            semantic_results, keyword_results
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
) -> List[Any]:
    """合併並去重搜索結果。"""
    seen_ids = set()
    merged = []

    for results in [semantic_results, keyword_results]:
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
