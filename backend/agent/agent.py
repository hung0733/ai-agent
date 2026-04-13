from __future__ import annotations

import time
import traceback
from datetime import datetime, timezone
import logging
from typing import Any, AsyncGenerator, Dict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.db.config import async_session_factory
from backend.db.entity import AgentEntity, SessionEntity
from backend.graph.agent import SUMMARY_TRIGGER_TOKEN, SUMMARY_USAGE_TOKEN, workflow
from backend.graph.checkpoint import ExtLanggraphCheckpointer
from backend.graph.graph_node import GraphNode
from backend.msg_queue.models import StreamChunk
from i18n import _


logger = logging.getLogger(__name__)


class Agent:
    _graph: Any = None

    agent_db_id: int
    session_db_id: int
    
    agent_id: str
    session_id: str
    
    recv_agent_name: str
    sender_agent_name:str

    stm_trigger_token: int
    stm_summary_token: int

    def __init__(
        self,
        agent_db_id: int,
        session_db_id: int,   
        agent_id: str,
        session_id: str,
        recv_agent_name: str,
        sender_agent_name: str,
    ):
        self.agent_db_id = agent_db_id
        self.agent_id = agent_id
        self.session_db_id = session_db_id
        self.session_id = session_id
        self.recv_agent_name = recv_agent_name
        self.sender_agent_name = sender_agent_name

        self.stm_trigger_token = SUMMARY_TRIGGER_TOKEN
        self.stm_summary_token = SUMMARY_USAGE_TOKEN
        
        if Agent._graph is None:
            Agent._graph = workflow.compile(checkpointer=ExtLanggraphCheckpointer())
            
    @classmethod
    async def get_db_agent(
        cls, agent_id: str, session_id: str
    ) -> tuple[int, int, str, str, str, str]:
        """從數據庫獲取 agent 和 session 的資料。

        Returns:
            (agent_db_id, session_db_id, agent_id, session_id, recv_agent_name, sender_agent_name)

        Raises:
            ValueError: 當找不到 agent 或 session 時。
        """
        async with async_session_factory() as session:
            agent_stmt = (
                select(AgentEntity)
                .where(AgentEntity.agent_id == agent_id)
                .options(
                    selectinload(AgentEntity.user),
                    selectinload(AgentEntity.llm_group),
                )
            )
            agent_result = await session.execute(agent_stmt)
            agent = agent_result.scalar_one_or_none()

            if agent is None:
                raise ValueError(_("找不到 agent: %s"), agent_id)

            session_stmt = (
                select(SessionEntity)
                .where(SessionEntity.session_id == session_id)
                .options(
                    selectinload(SessionEntity.recv_agent).selectinload(AgentEntity.user),
                    selectinload(SessionEntity.sender_agent),
                )
            )
            session_result = await session.execute(session_stmt)
            session_entity = session_result.scalar_one_or_none()

            if session_entity is None:
                raise ValueError(_("找不到 session: %s"), session_id)

            recv_agent = session_entity.recv_agent
            sender_agent = session_entity.sender_agent

            recv_agent_name = recv_agent.name if recv_agent else ""
            sender_agent_name = sender_agent.name if sender_agent else recv_agent.user.name

            return (
                agent.id,
                session_entity.id,
                agent_id,
                session_id,
                recv_agent_name,
                sender_agent_name,
            )

    @classmethod
    async def get_agent(cls, agent_id: str, session_id: str):
        agent_db_id, session_db_id, agent_id, session_id, recv_agent_name, sender_agent_name = await Agent.get_db_agent(agent_id, session_id)
        
        return cls(
            agent_db_id=agent_db_id,
            agent_id=agent_id,
            session_db_id=session_db_id,
            session_id=session_id,
            recv_agent_name=recv_agent_name,
            sender_agent_name=sender_agent_name,
        )
    
    async def send(
        self,
        models: list[BaseChatModel],
        sys_prompt: str,
        message: str,
        think_mode: bool,
        metadata: Dict[str, Any],
    ) -> AsyncGenerator[StreamChunk, None]:
        
        try:
            # 準備 config
            config = GraphNode.prepare_chat_node_config(
                thread_id=self.session_id,
                models=models,
                sys_prompt=sys_prompt,
                involves_secrets=False,
                think_mode=think_mode,
                agent_db_id=self.agent_db_id,
                args=metadata,
                sender_name=self.sender_agent_name,
                recv_name=self.recv_agent_name,
            )

            async for chunk in Agent._graph.astream(
                {"messages": [HumanMessage(content=message, additional_kwargs={"datetime": datetime.now(timezone.utc)})]},
                config=config,
                stream_mode="messages",
            ):
                # stream_mode="messages" 返回 (msg, metadata) tuple
                if isinstance(chunk, tuple):
                    msg, metadata = chunk
                else:
                    msg = chunk
                    metadata = {}

                # 我哋只處理 LLM 嘔出嚟嘅消息，忽略其他 LangGraph 嘅系統事件
                if isinstance(msg, (AIMessage, AIMessageChunk)):
                    # 處理 Thinking (思考)
                    reasoning_content = msg.additional_kwargs.get(
                        "reasoning_content"
                    )
                    if reasoning_content:
                        # logger.debug(
                        #     f"🧠 收到推理內容，長度：{len(reasoning_content)}"
                        # )
                        yield StreamChunk(
                            chunk_type="think",
                            content=str(reasoning_content),
                            timestamp=time.time(),
                        )

                    # 處理 Tool Calls (工具)
                    if hasattr(msg, "tool_call_chunks") and msg.tool_call_chunks: # type: ignore
                        for tool_chunk in msg.tool_call_chunks: # type: ignore
                            # logger.debug(
                            #     f"🔧 收到工具調用：{tool_chunk.get('name')}"
                            # )
                            yield StreamChunk(
                                chunk_type="tool",
                                content=tool_chunk.get("name"),
                                data={"tool_call": tool_chunk},
                                timestamp=time.time(),
                            )
                    elif hasattr(msg, "tool_call") and msg.tool_call: # type: ignore
                        for tc in getattr(msg, "tool_calls", []):
                            # logger.debug(
                            #     f"🔧 收到工具調用：{tool_chunk.get('name')}"
                            # )
                            yield StreamChunk(
                                chunk_type="tool",
                                content=tc.get("name"),
                                data={"tool_call": tc},
                                timestamp=time.time(),
                            )

                    # 處理 Content (普通對話文字)
                    if msg.content:
                        content = (
                            msg.content
                            if isinstance(msg.content, str)
                            else str(msg.content)
                        )
                        #logger.debug(f"💬 收到內容，長度：{len(content)}")
                        yield StreamChunk(
                            chunk_type="content",
                            content=content,
                            timestamp=time.time(),
                        )
                elif isinstance(msg, ToolMessage):
                    content = (
                        msg.content
                        if isinstance(msg.content, str)
                        else str(msg.content)
                    )
                    # logger.debug(f"💬 收到工具結果，長度：{len(content)}")
                    yield StreamChunk(
                        chunk_type="tool_result",
                        content=content,
                        timestamp=time.time(),
                    )
        except Exception as e:
            logger.error(
                _("LLM 處理失敗，agentId: %s, sessionId: %s (%s): %s\n%s"),
                self.agent_id,
                self.session_id,
                self.recv_agent_name,
                e,
                traceback.format_exc(),
            )
            raise