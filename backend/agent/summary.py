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


async def review_stm(
    session_db_id: int,
    model: BaseChatModel,
    stm_trigger_token: int,
    stm_summary_token: int,
    max_token: int = 30000,
) -> None:
    """Review and summarize short-term memory when token threshold is exceeded.

    Args:
        session_db_id: Database ID of the session.
        model: LLM model to use for summarization.
        stm_trigger_token: Token threshold to trigger summarization.
        stm_summary_token: Number of tokens to keep (not summarize).
        max_token: Maximum tokens to summarize in a single batch.
    """
    async with async_session_factory() as session:
        hist_dao = AgentMsgHistDAO(session)
        mem_dao = ShortTermMemDAO(session)

        # Step 1: 查詢未 summary 的記錄
        records = await hist_dao.list_unsummarized_by_session(session_db_id)
        if not records:
            logger.debug(_("無未 summary 的記錄，session=%s"), session_db_id)
            return

        # Step 2: 按 checkpoint 分組
        checkpoints: dict[str, list] = {}
        for record in records:
            checkpoints.setdefault(record.checkpoint_id, []).append(record)

        # Step 3: 計算總 token
        total_token = sum(r.token for r in records)
        if total_token <= stm_trigger_token:
            logger.debug(
                _("總 token (%s) 未超過閾值 (%s)，session=%s"),
                total_token,
                stm_trigger_token,
                session_db_id,
            )
            return

        # Step 4: 確定保留範圍（最新 stm_trigger_token - stm_summary_token token）
        keep_token = stm_trigger_token - stm_summary_token
        checkpoint_ids = list(checkpoints.keys())  # 已按 create_dt 排序
        checkpoint_ids.reverse()  # 由新到舊

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

        # summary_checkpoints 是由新到舊，反轉回由舊到新
        summary_checkpoints.reverse()

        if not summary_checkpoints:
            logger.debug(_("無需要 summary 的 checkpoint，session=%s"), session_db_id)
            return

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
