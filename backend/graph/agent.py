import logging
from typing import Any, Dict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, MessagesState, StateGraph
from langchain_core.language_models.chat_models import BaseChatModel
from i18n import _
from backend.utils.tools import Tools
from backend.agent.summary import review_stm

logger = logging.getLogger(__name__)

SUMMARY_TRIGGER_TOKEN: int = 10000
SUMMARY_USAGE_TOKEN: int = 5000


class AgentState(MessagesState):
    summary: str


async def chat_node(state: AgentState, config: RunnableConfig):
    # 由 config 攞返 LLM 同 System Prompt 出嚟
    models: list[BaseChatModel] = config["configurable"]["models"]  # type: ignore
    sys_prompt: str = config["configurable"]["sys_prompt"] or ""  # type: ignore
    think_mode: bool = config["configurable"]["think_mode"]  # type: ignore
    args: Dict[str, Any] = config["configurable"]["args"]  # type: ignore

    messages_to_send: list[BaseMessage] = []

    # 只有非 backend 任務先入 system prompt
    if sys_prompt:
        messages_to_send.append(SystemMessage(content=sys_prompt))
        logger.debug(
            f"📝 已加入 System Prompt (長度：{len(sys_prompt)}, Token: {Tools.get_token_count(sys_prompt)})"
        )

    session_db_id = config["configurable"].get("session_db_id")  # type: ignore
    if session_db_id is not None:
        from db.config import async_session_factory
        from db.dao.short_term_mem_dao import ShortTermMemDAO

        async with async_session_factory() as db_session:
            mem_dao = ShortTermMemDAO(db_session)
            memories = await mem_dao.list_recent_by_token_limit(
                session_db_id, max_token=10000
            )
            if memories:
                summary_content = "\n".join(m.content for m in memories)
                messages_to_send.append(
                    AIMessage(
                        content=_(
                            "以下是過去對話的重點總結，請作為背景記憶參考：\n{}"
                        ).format(summary_content)
                    )
                )

    last_message: BaseMessage = state["messages"][-1]
    message: BaseMessage
    msg_count: int = 0
    msg_token: int = 0
    msg_len: int = 0

    for message in state["messages"]:
        messages_to_send.append(message)
        last_message = message
        msg_count += 1
        msg_token += Tools.get_token_count(message.content)
        msg_len += len(message.content)

    msg_count -= 1
    msg_token -= Tools.get_token_count(last_message.content)
    msg_len -= len(last_message.content)

    logger.info(
        f"💬 Message History, Count: {msg_count}, Length: {msg_len}, Token: {msg_token}"
    )
    logger.info(
        f"💬 Send Message, Length: {len(last_message.content)}, Token: {Tools.get_token_count(last_message.content)}"
    )
    logger.debug(f"💬 Send Message: {last_message.content}")

    # 綁定 file system tools 到 model
    sandbox = config["configurable"].get("sandbox")  # type: ignore
    model_to_use = models[0]
    if sandbox is not None:
        from backend.tools import get_file_tools

        file_tools = get_file_tools(sandbox)
        model_to_use = model_to_use.bind_tools(file_tools)

    # 呼叫模型 (用 ainvoke 獲取完整回應)
    response = await model_to_use.ainvoke(messages_to_send)

    if hasattr(response, "tool_calls") and len(response.tool_calls) > 0:
        for tc in getattr(response, "tool_calls", []):
            args = tc.get("args", {})
            truncated_args = {
                k: (v[:100] + "..." if isinstance(v, str) and len(v) > 100 else v)
                for k, v in args.items()
            }
            logger.info(
                _("🔧 收到工具調用：%s, 📥 傳入參數: %s")
                % (tc.get("name"), truncated_args)
            )
    else:
        logger.info(_("💬 收到內容，長度：%s") % len(response.content))
        logger.debug(_("💬 收到內容：%s") % response.content)

    # 返回最新嘅 AIMessage，LangGraph 會自動 append 落 State 度
    return {"messages": [response]}


# 路由判斷：模型有冇 Call Tool？
def should_continue(state: AgentState) -> str:
    messages = state["messages"]
    last_message = messages[-1]

    # 如果最後一個 Message 有 tool_calls，就去 "tools" node 執行
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:  # type: ignore
        return "tools"
    # 否則對話結束
    return END


# 建立藍圖 (Workflow)
workflow = StateGraph(AgentState)

workflow.add_node("chat", chat_node)


async def tool_executor_node(state: AgentState, config: RunnableConfig):
    """從 config 獲取 sandbox 並執行 tool calls。"""
    from backend.tools import get_file_tools

    messages = state["messages"]
    last_message = messages[-1]

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:  # type: ignore
        return {"messages": []}

    sandbox = config["configurable"].get("sandbox")  # type: ignore
    if sandbox is None:
        return {
            "messages": [
                ToolMessage(
                    content=_("錯誤: Sandbox 未初始化"),
                    tool_call_id=tc["id"],
                )
                for tc in last_message.tool_calls  # type: ignore
            ]
        }

    tools = get_file_tools(sandbox)
    tool_map = {tool.name: tool for tool in tools}

    results = []
    for tc in last_message.tool_calls:  # type: ignore
        tool_name = tc.get("name")
        tool_args = tc.get("args", {})
        tool_id = tc.get("id")

        if tool_name not in tool_map:
            results.append(
                ToolMessage(
                    content=_("未知工具: {}").format(tool_name),
                    tool_call_id=tool_id,
                )
            )
            continue

        try:
            tool = tool_map[tool_name]
            result = await tool.ainvoke(tool_args)
            results.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=tool_id,
                )
            )
        except Exception as e:
            logger.error(_("工具執行失敗 [%s]: %s") % (tool_name, e))
            results.append(
                ToolMessage(
                    content=_("工具執行失敗: {}").format(str(e)),
                    tool_call_id=tool_id,
                )
            )

    return {"messages": results}


async def review_stm_node(state: AgentState, config: RunnableConfig):
    """Review STM and truncate old messages after tool execution.

    This runs after tools node to prevent context window explosion
    during tool call loops.
    """
    session_db_id = config["configurable"].get("session_db_id")  # type: ignore
    models: list[BaseChatModel] = config["configurable"].get("models", [])  # type: ignore
    stm_trigger_token = config["configurable"].get("stm_trigger_token", SUMMARY_TRIGGER_TOKEN)  # type: ignore
    stm_summary_token = config["configurable"].get("stm_summary_token", SUMMARY_USAGE_TOKEN)  # type: ignore

    if session_db_id is None or not models:
        logger.warning(_("review_stm_node 缺少必要參數，跳過"))
        return {}

    result = await review_stm(
        session_db_id=session_db_id,
        model=models[0],
        stm_trigger_token=stm_trigger_token,
        stm_summary_token=stm_summary_token,
    )

    if result is None:
        return {}

    truncate_count, summary_groups, records = result

    if truncate_count <= 0:
        return {}

    messages = state["messages"]
    if len(messages) <= truncate_count:
        logger.warning(_("state 消息數量不足以截斷，跳過"))
        return {}

    kept_messages = messages[truncate_count:]
    logger.info(
        _("review_stm_node 截斷 %s 條舊消息，保留 %s 條"),
        truncate_count,
        len(kept_messages),
    )

    return {"messages": kept_messages}


workflow.add_node("tools", tool_executor_node)
workflow.add_node("review_stm", review_stm_node)
workflow.add_edge(START, "chat")
workflow.add_conditional_edges("chat", should_continue, {"tools": "tools", END: END})
workflow.add_edge("tools", "review_stm")
workflow.add_edge("review_stm", "chat")

graph = workflow.compile()
