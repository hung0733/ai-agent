from typing import Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig


class AgentState(TypedDict):
    summary: str
    messages: Sequence[BaseMessage]


async def send_node(
    state: AgentState, config: RunnableConfig
) -> dict[str, list[BaseMessage]]:
    agent_db_id: str = config["configurable"].get("agent_db_id", "")  # type: ignore
    sys_prompt: str = config["configurable"].get("sys_prompt", "")  # type: ignore
    summary = state.get("summary", "")
    messages = state["messages"]  # type: ignore
