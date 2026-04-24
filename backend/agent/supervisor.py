from typing import Any, AsyncGenerator, Dict

from langchain_core.language_models import BaseChatModel

from agent.agent import Agent
from models.llm import LLMSet
from msg_queue.models import StreamChunk


class Supervisor(Agent):
    _graph: Any = None

    def __init__(self, *args, **kwargs):
        super(Agent, self).__init__(*args, **kwargs)

    @classmethod
    async def init_graph(cls) -> None:
        """初始化帶有 PostgreSQL checkpointer 的 graph。"""
        # if cls._graph is None:
        #     checkpointer = await get_checkpointer()
        #     cls._graph = workflow.compile(checkpointer=checkpointer)
        pass

    @classmethod
    async def get_agent(cls, agent_id: str, session_id: str):
        await cls.init_graph()

        (
            agent_db_id,
            session_db_id,
            user_db_id,
            agent_id,
            session_id,
            recv_agent_name,
            sender_agent_name,
        ) = await Agent.get_db_agent(agent_id, session_id)

        return cls(
            agent_db_id=agent_db_id,
            agent_id=agent_id,
            session_db_id=session_db_id,
            session_id=session_id,
            user_db_id=user_db_id,
            recv_agent_name=recv_agent_name,
            sender_agent_name=sender_agent_name,
        )

    async def send(
        self,
        models: LLMSet,
        sys_prompt: str,
        message: str,
        think_mode: bool,
        metadata: Dict[str, Any],
    ) -> AsyncGenerator[StreamChunk, None]:
        async for chunk in Agent.proc_send(
            agent=self,
            models=models,
            sys_prompt=sys_prompt,
            message=message,
            think_mode=think_mode,
            metadata=metadata,
            graph=Supervisor._graph,
        ):
            yield chunk
