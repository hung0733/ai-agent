"""Helpers for mapping queue data to OpenAI-compatible payloads."""

from __future__ import annotations

import time
import uuid

from fastapi import HTTPException

from api.schemas.openai_chat import OpenAIChatCompletionRequest


def build_queue_payload(req: OpenAIChatCompletionRequest) -> dict[str, object]:
    """Extract the queue-facing payload from an OpenAI request."""
    last_user_message: str | None = None
    for msg in req.messages:
        if msg.role == "user":
            last_user_message = msg.content

    if not last_user_message:
        raise HTTPException(status_code=400, detail="Missing user message")

    return {
        "message": last_user_message,
        "think_mode": req.think_mode,
    }


def build_completion_response(
    content: str,
    model: str,
    reasoning: str | None = None,
) -> dict[str, object]:
    """Build a non-stream OpenAI chat completion payload."""
    now = int(time.time())
    message: dict[str, object] = {"role": "assistant", "content": content}
    if reasoning:
        message["reasoning"] = reasoning

    return {
        "object": "chat.completion",
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "created": now,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "stop",
            }
        ],
    }


def build_stream_chunk(
    content: str,
    model: str,
    chunk_type: str = "content",
) -> dict[str, object]:
    """Build a single OpenAI SSE chat chunk."""
    now = int(time.time())
    delta_key = "reasoning_content" if chunk_type == "think" else "content"
    return {
        "object": "chat.completion.chunk",
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "created": now,
        "model": model,
        "choices": [
            {"index": 0, "delta": {delta_key: content}, "finish_reason": None}
        ],
    }


def build_final_stream_chunk(model: str) -> dict[str, object]:
    """Build the final stop chunk for SSE chat completions."""
    now = int(time.time())
    return {
        "object": "chat.completion.chunk",
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "created": now,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
