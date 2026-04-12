import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, MessagesState, StateGraph
from langchain_core.language_models.chat_models import BaseChatModel

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
    args: Dict[str, Any] = config["configurable"]["args"] 

    messages_to_send: list[BaseMessage] = []
    
    # 只有非 backend 任務先入 system prompt
    if sys_prompt:
        messages_to_send.append(SystemMessage(content=sys_prompt))
        logger.debug(f"📝 已加入 System Prompt (長度：{len(sys_prompt)})")

    summary = state.get("summary", "")
    if summary:
        messages_to_send.append(
            AIMessage(
                content=f"以下是過去對話的重點總結，請作為背景記憶參考：\n{summary}"
            )
        )

    messages_to_send += state["messages"]
    last_message : BaseMessage = state["messages"][-1]
    
    logger.info(f"💬 Send Message, Length: {len(last_message.content)}, {last_message.content}")
    
    for model in models:
        # 呼叫模型 (用 ainvoke 獲取完整回應)
        response = await model.ainvoke(messages_to_send)
        
        if hasattr(response, "tool_calls") and len(response.tool_calls) > 0:
            for tc in getattr(response, "tool_calls", []):
                logger.info(f"🔧 收到工具調用：{tc.get('name')}, 📥 傳入參數: {tc.get('args')}")
        else:
            logger.info(f"💬 收到內容，長度：{len(response.content)}, {response.content}")

        # 返回最新嘅 AIMessage，LangGraph 會自動 append 落 State 度
        return {"messages": [response]}
    
    
# 建立藍圖 (Workflow)
workflow = StateGraph(AgentState)

workflow.add_node("chat", chat_node)

workflow.add_edge(START, "chat")

workflow.add_edge("chat", END)

graph = workflow.compile()