"""Minimal LangGraph bridge for SYS_ACT_LLM streaming."""

from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator, Sequence, TypedDict

import httpx
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from i18n import _
from msg_queue.models import StreamChunk


class AgentState(TypedDict):
    summary: str
    messages: Sequence[dict[str, str]]


def _get_sys_act_llm_config() -> tuple[str, str, str]:
    endpoint = os.getenv("SYS_ACT_LLM_ENDPOINT", "").strip()
    api_key = os.getenv("SYS_ACT_LLM_API_KEY", "").strip()
    model = os.getenv("SYS_ACT_LLM_MODEL", "").strip()

    if not endpoint:
        raise ValueError(_("缺少 SYS_ACT_LLM_ENDPOINT 設定"))
    if not model:
        raise ValueError(_("缺少 SYS_ACT_LLM_MODEL 設定"))

    return endpoint, api_key or "NO_KEY", model


def _build_request_payload(
    messages: Sequence[dict[str, str]],
    think_mode: bool | None,
) -> dict[str, Any]:
    _, _, model = _get_sys_act_llm_config()
    payload: dict[str, Any] = {
        "model": model,
        "messages": list(messages),
        "stream": True,
    }
    if think_mode is not None:
        payload["think_mode"] = think_mode
    return payload


def _iter_delta_chunks(delta: dict[str, Any]) -> list[StreamChunk]:
    chunks: list[StreamChunk] = []

    for key in ("reasoning_content", "reasoning", "thinking"):
        value = delta.get(key)
        if isinstance(value, str) and value:
            chunks.append(StreamChunk(chunk_type="think", content=value))

    content = delta.get("content")
    if isinstance(content, str) and content:
        chunks.append(StreamChunk(chunk_type="content", content=content))
    elif isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            text = item.get("text") or item.get("content")
            if not isinstance(text, str) or not text:
                continue
            if item_type in {"reasoning", "thinking"}:
                chunks.append(StreamChunk(chunk_type="think", content=text))
            else:
                chunks.append(StreamChunk(chunk_type="content", content=text))

    return chunks


async def _stream_llm_response(
    messages: Sequence[dict[str, str]],
    think_mode: bool | None,
) -> AsyncIterator[StreamChunk]:
    endpoint, api_key, _ = _get_sys_act_llm_config()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = _build_request_payload(messages, think_mode)
    url = f"{endpoint.rstrip('/')}/chat/completions"

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue

                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue

                chunk_data = json.loads(data)
                choices = chunk_data.get("choices") or []
                if not choices:
                    continue

                delta = choices[0].get("delta") or {}
                if not isinstance(delta, dict):
                    continue

                for chunk in _iter_delta_chunks(delta):
                    yield chunk


async def send_node(
    state: AgentState, config: RunnableConfig
) -> dict[str, list[dict[str, str]]]:
    sys_prompt = config.get("configurable", {}).get("sys_prompt", "")
    messages: list[dict[str, str]] = []
    if sys_prompt:
        messages.append({"role": "system", "content": sys_prompt})
    messages.extend(state["messages"])
    return {"messages": messages}


def build_agent_graph():
    graph = StateGraph(AgentState)
    graph.add_node("send", send_node)
    graph.set_entry_point("send")
    graph.add_edge("send", END)
    return graph.compile()


async def stream_agent_reply(
    message: str,
    system_prompt: str | None = None,
    think_mode: bool | None = None,
) -> AsyncIterator[StreamChunk]:
    _get_sys_act_llm_config()
    graph = build_agent_graph()
    config: RunnableConfig = {
        "configurable": {
            "sys_prompt": system_prompt or "",
        }
    }
    state: AgentState = {
        "summary": "",
        "messages": [{"role": "user", "content": message}],
    }
    graph_result = await graph.ainvoke(state, config=config)
    messages = graph_result["messages"]

    async for chunk in _stream_llm_response(messages, think_mode):
        yield chunk
