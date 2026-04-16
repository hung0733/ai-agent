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


def select_checkpoints_for_summary(
    records: list,
    stm_trigger_token: int,
    stm_summary_token: int,
) -> tuple[list[str], list[str]]:
    """Determine which checkpoints to keep vs. summarize.

    Returns:
        (keep_checkpoint_ids, summary_checkpoint_ids) both ordered old-to-new.
    """
    checkpoints: dict[str, list] = {}
    for record in records:
        checkpoints.setdefault(record.checkpoint_id, []).append(record)

    total_token = sum(r.token for r in records)
    if total_token <= stm_trigger_token:
        return [], []

    keep_token = stm_trigger_token - stm_summary_token
    checkpoint_ids = list(checkpoints.keys())
    checkpoint_ids.reverse()  # new-to-old

    keep_checkpoints: list[str] = []
    summary_checkpoints: list[str] = []
    current_keep_token = 0

    for cp_id in checkpoint_ids:
        cp_records = checkpoints[cp_id]
        cp_token = sum(r.token for r in cp_records)
        if current_keep_token + cp_token <= keep_token:
            keep_checkpoints.append(cp_id)
            current_keep_token += cp_token
        else:
            summary_checkpoints.append(cp_id)

    summary_checkpoints.reverse()  # old-to-new
    return keep_checkpoints, summary_checkpoints


def compute_truncate_count(summary_checkpoint_ids: list[str], records: list) -> int:
    """Calculate how many messages to truncate from LangGraph state.

    Uses the max message_idx from summarized checkpoints to determine
    how many old messages can be safely removed.
    """
    if not summary_checkpoint_ids:
        return 0

    summary_ids = set(summary_checkpoint_ids)
    max_idx = -1
    for record in records:
        if record.checkpoint_id in summary_ids:
            if record.message_idx > max_idx:
                max_idx = record.message_idx

    # message_idx is 0-based, so truncate count = max_idx (keep messages from max_idx onward)
    return max(0, max_idx)


async def review_stm(
    session_db_id: int,
    model: BaseChatModel,
    stm_trigger_token: int,
    stm_summary_token: int,
    max_token: int = 30000,
) -> tuple[list[str], list[str], list] | None:
    """Review and summarize short-term memory when token threshold is exceeded.

    Returns:
        (keep_checkpoint_ids, summary_checkpoint_ids, records) or None if no summarization occurred.
    """
    async with async_session_factory() as session:
        hist_dao = AgentMsgHistDAO(session)
        mem_dao = ShortTermMemDAO(session)

        # Step 1: 查詢未 summary 的記錄
        records = await hist_dao.list_unsummarized_by_session(session_db_id)
        if not records:
            logger.debug(_("無未 summary 的記錄，session=%s"), session_db_id)
            return None

        # Step 2-4: 使用 helper 確定保留/summary 範圍
        keep_checkpoints, summary_checkpoints = select_checkpoints_for_summary(
            records, stm_trigger_token, stm_summary_token,
        )
        if not summary_checkpoints:
            logger.debug(_("無需要 summary 的 checkpoint，session=%s"), session_db_id)
            return None

        # 重建 checkpoints dict 供分批處理使用
        checkpoints: dict[str, list] = {}
        for record in records:
            checkpoints.setdefault(record.checkpoint_id, []).append(record)

        # Step 5: 分批 summary
        await _process_summary_batches(
            session_db_id=session_db_id,
            model=model,
            summary_checkpoints=summary_checkpoints,
            checkpoints=checkpoints,
            hist_dao=hist_dao,
            mem_dao=mem_dao,
            max_token=max_token,
        )

        await session.commit()

        return keep_checkpoints, summary_checkpoints, records


async def _process_summary_batches(
    session_db_id: int,
    model: BaseChatModel,
    summary_checkpoints: list[str],
    checkpoints: dict[str, list],
    hist_dao: AgentMsgHistDAO,
    mem_dao: ShortTermMemDAO,
    max_token: int,
) -> None:
    """Process summary in batches, each batch ≤ max_token."""
    # 收集所有待 summary 的 human/ai 記錄（由舊到新）
    all_summary_records: list = []
    for cp_id in summary_checkpoints:
        for record in checkpoints[cp_id]:
            if record.msg_type in ("human", "ai"):
                all_summary_records.append(record)

    # 分批處理
    batch_records: list = []
    batch_token = 0

    for record in all_summary_records:
        if batch_token + record.token > max_token and batch_records:
            # 處理當前批次
            await _process_single_batch(
                session_db_id=session_db_id,
                model=model,
                batch_records=batch_records,
                mem_dao=mem_dao,
            )
            batch_records = []
            batch_token = 0
        batch_records.append(record)
        batch_token += record.token

    # 處理最後一批
    if batch_records:
        await _process_single_batch(
            session_db_id=session_db_id,
            model=model,
            batch_records=batch_records,
            mem_dao=mem_dao,
        )

    # 標記所有 checkpoint 為已 summary
    for cp_id in summary_checkpoints:
        await hist_dao.mark_checkpoint_as_summarized(cp_id, session_db_id)


def _format_conversation(records: list) -> str:
    """Format records into conversation string."""
    lines = []
    for record in records:
        timestamp = record.create_dt.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"[{timestamp}] {record.sender} : {record.content}")
    return "\n".join(lines)


async def _process_single_batch(
    session_db_id: int,
    model: BaseChatModel,
    batch_records: list,
    mem_dao: ShortTermMemDAO,
) -> None:
    """Process a single batch of records for summarization."""
    try:
        conversation = _format_conversation(batch_records)
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

        # 解析 JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(_("LLM 返回的 JSON 格式錯誤: %s — %s"), content[:200], e)
            return

        memories = data.get("memories", [])
        if not memories:
            logger.debug(_("LLM 未返回任何 memories"))
            return

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

    except Exception as exc:
        logger.error(_("Summary 批次處理失敗: %s"), exc)
