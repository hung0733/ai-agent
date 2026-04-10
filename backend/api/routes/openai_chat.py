"""OpenAI-compatible chat completions route."""

from __future__ import annotations

import inspect
import json
import re
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.adapters.openai_chat import (
    build_completion_response,
    build_final_stream_chunk,
    build_queue_payload,
    build_stream_chunk,
)
from api.schemas.openai_chat import OpenAIChatCompletionRequest
from db.config import get_async_session
from db.dao.agent_dao import AgentDAO
from i18n import _
from msg_queue.handler import MsgQueueHandler

router = APIRouter(prefix="/api/agents/{agent_id}/v1", tags=["openai-chat"])

_AGENT_ID_RE = re.compile(r"^agent-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


async def get_agent_or_404(agent_id: str, session: AsyncSession) -> object:
    """Validate the agent path parameter and ensure it exists."""
    if not _AGENT_ID_RE.match(agent_id):
        raise HTTPException(status_code=400, detail=_("agent_id 格式無效"))

    dao = AgentDAO(session)
    agent = await dao.get_by_agent_id(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=_("找不到 agent"))
    return agent


@router.get("/models")
async def list_models(
    agent_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, object]:
    """Return a minimal OpenAI-compatible models list for this agent."""
    await get_agent_or_404(agent_id, session)
    return {
        "object": "list",
        "data": [
            {
                "id": "gpt-4o",
                "object": "model",
                "created": 0,
                "owned_by": "openai",
            }
        ],
    }


@router.post("/chat/completions")
async def create_chat_completion(
    agent_id: str,
    request: OpenAIChatCompletionRequest,
    session: AsyncSession = Depends(get_async_session),
) -> object:
    """Bridge OpenAI chat completions requests into the message queue."""
    await get_agent_or_404(agent_id, session)

    try:
        payload = build_queue_payload(request)
        session_id = f"session_{uuid.uuid4()}"
        stream = MsgQueueHandler.create_msg_queue(
            agent_id=agent_id,
            session_id=session_id,
            message=payload["message"],
            think_mode=payload["think_mode"],
        )
        if inspect.isawaitable(stream):
            stream = await stream
    except HTTPException:
        raise
    except ValueError as exc:
        if "隊列已滿" in str(exc):
            raise HTTPException(status_code=429, detail=_("隊列已滿")) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_("內部伺服器錯誤")) from exc

    if request.stream:
        async def sse_gen() -> AsyncIterator[str]:
            async for chunk in stream:
                if chunk.chunk_type == "content" and chunk.content:
                    payload = json.dumps(
                        build_stream_chunk(chunk.content, request.model),
                        separators=(",", ":"),
                    )
                    yield f"data: {payload}\n\n"

            final_payload = json.dumps(
                build_final_stream_chunk(request.model),
                separators=(",", ":"),
            )
            yield f"data: {final_payload}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(sse_gen(), media_type="text/event-stream")

    parts: list[str] = []
    async for chunk in stream:
        if chunk.chunk_type == "content" and chunk.content:
            parts.append(chunk.content)

    return build_completion_response("".join(parts), request.model)
