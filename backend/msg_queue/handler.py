"""MsgQueueHandler — LLM pipeline stages for QueueTask processing.

Each static method handles one state in the pipeline.
Register them with QueueManager.register_state_handler() at startup.

Pipeline order:
  INIT
  → collect_db_data      (load agent from DB)
  → pack_sys_prompt      (assemble system prompt)
  → pack_memory          (attach long-term memory)
  → pack_message         (finalise user message)
  → analyse_msg_diff     (classify difficulty)
  → select_llm_model     (pick model based on difficulty)
  → send_llm_msg         (stream LLM → callback → WhatsApp)
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, AsyncGenerator, Dict, Optional

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from agent.agent import Agent
from backend.utils.tools import Tools
from i18n import _
from msg_queue.manager import QueueManager, get_queue_manager
from msg_queue.models import (
    QueueTaskPriority,
    QueueTaskState,
    StreamChunk,
)
from msg_queue.task import QueueTask

logger = logging.getLogger(__name__)


class MsgQueueHandler:

    @staticmethod
    async def create_msg_queue(
        agent_id: str,
        session_id: str,
        message: str,
        sender_agent_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        think_mode: Optional[bool] = None,
        priority: QueueTaskPriority = QueueTaskPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Enqueue a task and return an async generator of StreamChunks."""
        qm = get_queue_manager()
        logger.debug(_("正在建立任務 agent=%s session=%s"), agent_id, session_id)
        logger.debug(
            _("DEBUG: QueueManager 實例 (id=%s, running=%s, handlers=%s)"),
            id(qm),
            qm._running,
            list(qm._state_handlers.keys()),
        )
        task_id, gen = await qm.enqueue(
            agent_id=agent_id,
            session_id=session_id,
            message=message,
            sender_agent_id=sender_agent_id,
            system_prompt=system_prompt,
            priority=priority,
            metadata=metadata,
            think_mode=think_mode,
        )
        logger.debug(_("任務 %s 已加入队列"), task_id)
        async for chunk in gen:
            yield chunk

    # ------------------------------------------------------------------
    # Pipeline stages (register these with QueueManager at startup)
    # ------------------------------------------------------------------

    @staticmethod
    async def collect_db_data(task: QueueTask) -> None:
        """從數據庫載入 agent 資料並建立 Agent 實例。"""
        logger.debug(_("任務 %s：collect_db_data (agent=%s)"), task.id, task.agent_id)
        try:
            agent = await Agent.get_agent(
                agent_id=task.agent_id,
                session_id=task.session_id,
            )
            task.agent = agent
            task.update_state(QueueTaskState.COLLECTED_DB_DATA)
        except Exception as exc:
            logger.error(
                _("任務 %s：collect_db_data 失敗：%s\n%s"),
                task.id,
                exc,
                traceback.format_exc(),
            )
            task.update_state(QueueTaskState.ERROR)
            task.error = str(exc)
            raise

    @staticmethod
    async def pack_memory(task: QueueTask) -> None:
        """Attach long-term memory context to the message."""
        logger.debug(_("任務 %s：pack_memory"), task.id)
        try:

            task.update_state(QueueTaskState.PACKED_MEMORY)
        except Exception as exc:
            logger.error(
                _("任務 %s：pack_memory 失敗：%s\n%s"),
                task.id,
                exc,
                traceback.format_exc(),
            )
            task.update_state(QueueTaskState.ERROR)
            task.error = str(exc)
            raise

    @staticmethod
    async def pack_message(task: QueueTask) -> None:
        """Finalise the user message string."""
        logger.debug(_("任務 %s：pack_message"), task.id)
        try:
            if task.packed_message is None:
                task.packed_message = ""
            task.packed_message += task.message or ""
            task.update_state(QueueTaskState.MESSAGES_PACKED)
        except Exception as exc:
            logger.error(
                _("任務 %s：pack_message 失敗：%s\n%s"),
                task.id,
                exc,
                traceback.format_exc(),
            )
            task.update_state(QueueTaskState.ERROR)
            task.error = str(exc)
            raise

    @staticmethod
    async def select_llm_model(task: QueueTask) -> None:
        """Use SYS_ACT_LLM as the single system-level model selection."""
        logger.debug(_("任務 %s：select_llm_model"), task.id)
        try:
            task.model_set = [
                ChatOpenAI(
                    base_url=Tools.require_env("SYS_ACT_LLM_ENDPOINT"),
                    api_key=SecretStr(Tools.require_env("SYS_ACT_LLM_API_KEY")),
                    model=Tools.require_env("SYS_ACT_LLM_MODEL"),
                    streaming=True,
                    stream_usage=True,
                )
            ]
            task.update_state(QueueTaskState.SELECTED_LLM_MODEL)
        except Exception as exc:
            logger.error(
                _("任務 %s：select_llm_model 失敗：%s\n%s"),
                task.id,
                exc,
                traceback.format_exc(),
            )
            task.update_state(QueueTaskState.ERROR)
            task.error = str(exc)
            raise

    @staticmethod
    async def send_llm_msg(task: QueueTask) -> None:
        """使用 Agent 實例串流 LangGraph 回應並推送 chunk 到任務隊列。"""
        logger.debug(_("任務 %s：send_llm_msg"), task.id)
        try:
            if task.packed_message is None:
                raise ValueError(_("訊息未打包 — 先執行 pack_message"))
            if task.agent is None:
                raise ValueError(_("Agent 未初始化 — 先執行 collect_db_data"))

            task.update_state(QueueTaskState.SENDING_TO_LLM)

            models = task.model_set or []
            sys_prompt = task.system_prompt or ""
            think_mode = task.think_mode if task.think_mode is not None else False

            async for chunk in task.agent.send(
                models=models,
                sys_prompt=sys_prompt,
                message=task.packed_message,
                think_mode=think_mode,
                metadata=task.metadata,
            ):
                task.update_state(QueueTaskState.RECEIVING_STREAM)
                await task.stream_callback(chunk)

            task.update_state(QueueTaskState.STREAMING_TO_CLIENT)
            await task.complete_callback({})

        except Exception as exc:
            logger.error(
                _("任務 %s：send_llm_msg 失敗：%s\n%s"),
                task.id,
                exc,
                traceback.format_exc(),
            )
            task.update_state(QueueTaskState.ERROR)
            task.error = str(exc)
            raise


def register_all_handlers(qm: Optional[QueueManager] = None) -> QueueManager:
    """Register the full pipeline on *qm* (default: global singleton).

    Call this at application startup after QueueManager.start().
    """
    if qm is None:
        qm = get_queue_manager()

    qm.register_state_handler(QueueTaskState.INIT, MsgQueueHandler.collect_db_data)
    qm.register_state_handler(
        QueueTaskState.COLLECTED_DB_DATA, MsgQueueHandler.pack_memory
    )
    qm.register_state_handler(
        QueueTaskState.PACKED_MEMORY, MsgQueueHandler.pack_message
    )
    qm.register_state_handler(
        QueueTaskState.MESSAGES_PACKED, MsgQueueHandler.select_llm_model
    )
    qm.register_state_handler(
        QueueTaskState.SELECTED_LLM_MODEL, MsgQueueHandler.send_llm_msg
    )
    return qm
