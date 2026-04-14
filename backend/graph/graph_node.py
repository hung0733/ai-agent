

from typing import Any, Dict, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig


class GraphNode:
    
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
        args: Optional[Dict[str, Any]] = None,
        sender_name: str = "",
        recv_name: str = "",
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
                "user_db_id": user_db_id,
                "sender_name": sender_name,
                "recv_name": recv_name,
            }
        }
