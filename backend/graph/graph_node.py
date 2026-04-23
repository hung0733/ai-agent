import logging
from typing import Any, Dict, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from backend.db.dao.short_term_mem_dao import ShortTermMemDAO
from backend.memory.store import MemoryStore
from backend.utils.tools import Tools
from i18n import _
from db.config import async_session_factory

logger = logging.getLogger(__name__)


class GraphNode:
    @staticmethod
    async def prepare_messages(
        config: RunnableConfig, sys_prompt: str, last_message: BaseMessage
    ) -> list[BaseMessage]:
        messages: list[BaseMessage] = []

        if sys_prompt:
            messages.append(SystemMessage(content=sys_prompt))
            logger.debug(
                _("已加入 System Prompt (長度：%s, Token: %s)"),
                len(sys_prompt),
                Tools.get_token_count(sys_prompt),
            )

            session_db_id = config["configurable"].get("session_db_id")  # type: ignore
            step_id = config["configurable"].get("step_id")  # type: ignore
            
            if session_db_id is not None and step_id is not None:
                memory_store = MemoryStore(session_db_id)
                messages = await memory_store.prepare_messages(step_id, last_message)

        return messages

    @staticmethod
    def replace_with_last(left: list, right: list):
        # 無論之前有幾多，只保留 right (新傳入) 嘅最後一條
        if not right:
            return left
        return [right[-1]]

    @staticmethod
    def prepare_chat_node_config(
        thread_id: str,
        models: list[BaseChatModel],
        sys_prompt: str,
        involves_secrets: bool,
        think_mode: Optional[bool],
        agent_db_id: int,
        session_db_id: int,
        user_db_id: int,
        step_id: str = "",
        args: Optional[Dict[str, Any]] = None,
        sender_name: str = "",
        recv_name: str = "",
        sandbox: Any = None,
        stm_trigger_token: int = 10000,
        stm_summary_token: int = 5000,
    ) -> RunnableConfig:
        return {
            "configurable": {
                "thread_id": thread_id,
                "models": models,
                "sys_prompt": sys_prompt,
                "involves_secrets": involves_secrets,
                "think_mode": think_mode,
                "args": args,
                "agent_db_id": agent_db_id,
                "session_db_id": session_db_id,
                "step_id": step_id,
                "user_db_id": user_db_id,
                "sender_name": sender_name,
                "recv_name": recv_name,
                "sandbox": sandbox,
                "stm_trigger_token": stm_trigger_token,
                "stm_summary_token": stm_summary_token,
            }
        }
