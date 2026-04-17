"""STM (Short-Term Memory) review and summary workflow."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from langchain_core.language_models import BaseChatModel

from agent.prompt import apply_stm_prompt_template
from db.config import async_session_factory
from db.dao.agent_msg_hist_dao import AgentMsgHistDAO
from db.dao.short_term_mem_dao import ShortTermMemDAO
from db.dto.memory import ShortTermMemCreate
from utils.tools import Tools
from i18n import _

logger = logging.getLogger(__name__)


def group_records_by_human(records: list) -> list[list]:
    """按 Human 訊息分組記錄。

    規則：每條 human 訊息開始新組，包含其後所有訊息直到下一條 human。

    Args:
        records: 按 message_idx 排序的記錄列表。

    Returns:
        分組後的記錄列表，例如 [[r1, r2], [r3], [r4, r5, r6]]
    """
    if not records:
        return []

    groups: list[list] = []
    current_group: list = []

    for record in records:
        if record.msg_type == "human":
            # 新 human 訊息，開始新組
            if current_group:
                groups.append(current_group)
            current_group = [record]
        else:
            # 非 human 訊息，加入當前組
            current_group.append(record)

    # 加入最後一組
    if current_group:
        groups.append(current_group)

    return groups


def select_conversation_groups_for_summary(
    groups: list[list],
    stm_trigger_token: int,
    stm_summary_token: int,
) -> tuple[list[list], list[list]]:
    """按對話分組決定保留/summary 範圍。

    Args:
        groups: 分組後的記錄列表。
        stm_trigger_token: 觸發 summary 的 token 閾值。
        stm_summary_token: 保留給 summary 的 token 空間。

    Returns:
        (keep_groups, summary_groups) 兩個都是舊到新的順序。
    """
    # 計算每組 token
    group_tokens = [(group, sum(r.token for r in group)) for group in groups]

    total_token = sum(t for _, t in group_tokens)
    if total_token <= stm_trigger_token:
        return [], []

    keep_token = stm_trigger_token - stm_summary_token

    # 從新到舊分配
    keep_groups: list[list] = []
    summary_groups: list[list] = []
    current_keep_token = 0

    for group, token in reversed(group_tokens):
        if current_keep_token + token <= keep_token:
            keep_groups.append(group)
            current_keep_token += token
        else:
            summary_groups.append(group)

    summary_groups.reverse()  # 舊到新
    return keep_groups, summary_groups


def compute_truncate_count(summary_groups: list[list]) -> int:
    """計算需要截斷的訊息數量。

    Args:
        summary_groups: 被 summary 的記錄分組。

    Returns:
        最大 message_idx，用於截斷 LangGraph state。
    """
    if not summary_groups:
        return 0

    max_idx = -1
    for group in summary_groups:
        for record in group:
            if record.message_idx > max_idx:
                max_idx = record.message_idx

    return max(0, max_idx)


async def review_stm(
    session_db_id: int,
    model: BaseChatModel,
    stm_trigger_token: int,
    stm_summary_token: int,
    max_token: int = 30000,
) -> tuple[int, list, list] | None:
    """Review and summarize short-term memory when token threshold is exceeded.

    Returns:
        (truncate_count, summary_groups, records) or None if no summarization occurred.
    """
    async with async_session_factory() as session:
        hist_dao = AgentMsgHistDAO(session)
        mem_dao = ShortTermMemDAO(session)

        # Step 1: 查詢未 summary 的記錄
        records = await hist_dao.list_unsummarized_by_session(session_db_id)
        if not records:
            logger.debug(_("無未 summary 的記錄，session=%s"), session_db_id)
            return None

        # Step 2: 按 Human 分組
        groups = group_records_by_human(records)
        if not groups:
            logger.debug(_("無有效對話分組，session=%s"), session_db_id)
            return None

        # Step 3: 決定保留/summary 範圍
        keep_groups, summary_groups = select_conversation_groups_for_summary(
            groups, stm_trigger_token, stm_summary_token,
        )
        if not summary_groups:
            logger.debug(_("無需要 summary 的對話組，session=%s"), session_db_id)
            return None

        # Step 4: 分批 summary
        summarized_ids = await _process_summary_batches(
            session_db_id=session_db_id,
            model=model,
            summary_groups=summary_groups,
            hist_dao=hist_dao,
            mem_dao=mem_dao,
            max_token=max_token,
        )

        # Step 5: 標記已處理的記錄
        if summarized_ids:
            await hist_dao.mark_records_as_summarized(list(summarized_ids), session_db_id)

        await session.commit()

        # 計算截斷數量
        truncate_count = compute_truncate_count(summary_groups)

        return truncate_count, summary_groups, records


async def _process_summary_batches(
    session_db_id: int,
    model: BaseChatModel,
    summary_groups: list[list],
    hist_dao: AgentMsgHistDAO,
    mem_dao: ShortTermMemDAO,
    max_token: int,
) -> set[int]:
    """按對話分組處理 summary。

    Returns:
        成功處理的記錄 ID 集合。
    """
    successfully_summarized_ids: set[int] = set()
    batch_records: list = []
    batch_token = 0
    batch_failed = False

    for group in summary_groups:
        # 檢查加入此組是否超過 max_token
        group_token = sum(r.token for r in group)

        if batch_token + group_token > max_token and batch_records:
            # 處理當前批次
            success = await _process_single_batch(
                session_db_id=session_db_id,
                model=model,
                batch_records=batch_records,
                mem_dao=mem_dao,
            )
            if not success:
                batch_failed = True
                logger.warning(
                    _("批次處理失敗，跳過標記記錄為已 summary")
                )
                break
            # 記錄成功處理的 ID
            for r in batch_records:
                successfully_summarized_ids.add(r.id)
            batch_records = []
            batch_token = 0

        batch_records.extend(group)
        batch_token += group_token

    # 處理最後一批（如果之前沒有失敗）
    if not batch_failed and batch_records:
        success = await _process_single_batch(
            session_db_id=session_db_id,
            model=model,
            batch_records=batch_records,
            mem_dao=mem_dao,
        )
        if success:
            for r in batch_records:
                successfully_summarized_ids.add(r.id)
        else:
            logger.warning(
                _("最後一批處理失敗，跳過標記記錄為已 summary")
            )

    return successfully_summarized_ids


def _format_conversation(records: list) -> str:
    """Format records into JSON conversation string."""
    import json
    
    conversation_data = []
    for record in records:
        conversation_data.append({
            "timestamp": record.create_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "sender": record.sender,
            "msg_type": record.msg_type,
            "content": record.content,
        })
    
    return json.dumps(conversation_data, ensure_ascii=False, indent=2)


async def _process_single_batch(
    session_db_id: int,
    model: BaseChatModel,
    batch_records: list,
    mem_dao: ShortTermMemDAO,
) -> bool:
    """Process a single batch of records for summarization.

    Returns:
        True if batch was processed successfully, False otherwise.
    """
    try:
        # Log 批次基本信息
        total_token = sum(getattr(r, 'token', 0) for r in batch_records)
        logger.info(
            _("Summary 批次處理開始 - session=%s, 記錄數=%s, 總 token=%s"),
            session_db_id,
            len(batch_records),
            total_token,
        )

        # Log 每條記錄的詳細信息
        for i, record in enumerate(batch_records):
            content_preview = (record.content[:100] + "...") if record.content and len(record.content) > 100 else record.content
            logger.debug(
                _("記錄 [%s/%s] - id=%s, msg_type=%s, sender=%s, token=%s, content=%s"),
                i + 1,
                len(batch_records),
                getattr(record, 'id', 'N/A'),
                getattr(record, 'msg_type', 'N/A'),
                getattr(record, 'sender', 'N/A'),
                getattr(record, 'token', 0),
                content_preview,
            )

        conversation = _format_conversation(batch_records)

        # Log 格式化後的對話內容
        logger.info(_("格式化後嘅對話內容:\n%s"), conversation)

        prompt = await apply_stm_prompt_template(conversation)

        response = await model.ainvoke(prompt)
        content = response.content.strip() # type: ignore

        # 移除 markdown 代碼塊包裹（如 ```json ... ```）
        if content.startswith("```"):
            # 移除開頭的 ```json 或 ```
            content = content.split("\n", 1)[-1] if "\n" in content else content[3:]
            # 移除結尾的 ```
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        # Log LLM 返回的原始內容
        logger.debug(_("LLM 返回內容:\n%s"), content[:500])

        # 解析 JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(_("LLM 返回的 JSON 格式錯誤: %s — %s"), content[:200], e)
            return False

        memories = data.get("memories", [])
        if not memories:
            logger.debug(_("LLM 未返回任何 memories"))
            return False

        # 寫入 short_term_mem
        now = datetime.now(timezone.utc)
        for memory in memories:
            restatement = memory.get("lossless_restatement", "")
            if not restatement:
                continue

            record_dt_str = memory.get("record_dt")
            if record_dt_str:
                try:
                    record_dt = datetime.fromisoformat(record_dt_str)
                except (ValueError, TypeError):
                    record_dt = now
            else:
                record_dt = now

            token = Tools.get_token_count(restatement)
            dto = ShortTermMemCreate(
                session_id=session_db_id,
                content=restatement,
                create_dt=record_dt,
                token=token,
            )
            await mem_dao.create_from_dto(dto)

        logger.info(_("已寫入 %s 條 short-term memories"), len(memories))
        return True

    except Exception as exc:
        logger.error(_("Summary 批次處理失敗: %s"), exc)
        return False
