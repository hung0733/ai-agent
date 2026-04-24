"""OpenAI API client implementation.

Provides async invoke and stream methods for OpenAI-compatible APIs.
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from openai import APIConnectionError, APIError, AsyncOpenAI, RateLimitError

from i18n import _
from msg_queue.models import StreamChunk

logger = logging.getLogger(__name__)


def _convert_message(message: BaseMessage) -> dict[str, Any]:
    """Convert a langchain BaseMessage to OpenAI API format.

    Args:
        message: langchain BaseMessage instance

    Returns:
        Dict with 'role' and 'content' keys, optionally 'tool_calls' or 'tool_call_id'
    """
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": message.content}
    elif isinstance(message, HumanMessage):
        return {"role": "user", "content": message.content}
    elif isinstance(message, AIMessage):
        result: dict[str, Any] = {"role": "assistant", "content": message.content}
        if hasattr(message, "tool_calls") and message.tool_calls:
            result["tool_calls"] = message.tool_calls
        return result
    elif isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
    else:
        raise ValueError(_("不支持的消息類型: %s"), type(message).__name__)


class OpenAIClient:
    """Async OpenAI API client.

    Args:
        base_url: OpenAI API endpoint URL
        api_key: API authentication key
        model: Model name (e.g., "gpt-4", "gpt-3.5-turbo")
    """

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
        )
        self._model = model

    def _create_chunk(
        self,
        chunk_type: str,
        content: Optional[str] = None,
        data: Optional[dict[str, Any]] = None,
    ) -> StreamChunk:
        """Create a StreamChunk with timestamp.

        Args:
            chunk_type: Type of chunk ("content", "think", "tool", "tool_result", "done")
            content: Text content
            data: Extra structured data

        Returns:
            StreamChunk instance
        """
        return StreamChunk(
            chunk_type=chunk_type,
            content=content,
            data=data,
            timestamp=time.time(),
        )

    async def astream(self, messages: list[BaseMessage]) -> AsyncIterator[StreamChunk]:
        """Stream LLM response as AsyncIterator of StreamChunk.

        Args:
            messages: List of langchain BaseMessage

        Yields:
            StreamChunk for each piece of content (think, content, tool, done)

        Raises:
            ValueError: If messages are invalid
            APIError: If API request fails
            APIConnectionError: If connection fails
            RateLimitError: If rate limited
        """
        try:
            openai_messages = [_convert_message(msg) for msg in messages]

            logger.debug(
                _("OpenAI 請求: model=%s, messages=%d"),
                self._model,
                len(openai_messages),
            )

            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=openai_messages,  # type: ignore
                stream=True,
            )  # type: ignore

            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # Handle tool calls
                if delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        tool_data: dict[str, Any] = {
                            "id": tool_call.id,
                            "type": tool_call.type,
                        }
                        if tool_call.function:
                            tool_data["function"] = {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            }
                        yield self._create_chunk(
                            chunk_type="tool",
                            data=tool_data,
                        )

                # Handle thinking/reasoning content (some models support this)
                thinking_content = getattr(delta, "reasoning_content", None) or getattr(
                    delta, "thinking", None
                )
                if thinking_content:
                    yield self._create_chunk(
                        chunk_type="think",
                        content=thinking_content,
                    )

                # Handle content
                if delta.content is not None:
                    yield self._create_chunk(
                        chunk_type="content",
                        content=delta.content,
                    )

                # Handle finish reason
                if chunk.choices[0].finish_reason == "stop":
                    yield self._create_chunk(chunk_type="done")
                    return

        except RateLimitError as exc:
            logger.error(_("OpenAI 請求頻率限制: %s"), exc)
            raise
        except APIConnectionError as exc:
            logger.error(_("OpenAI 連線錯誤: %s"), exc)
            raise
        except APIError as exc:
            logger.error(_("OpenAI API 錯誤: %s"), exc)
            raise
        except ValueError as exc:
            logger.error(_("OpenAI 消息轉換錯誤: %s"), exc)
            raise
        except Exception as exc:
            logger.error(_("OpenAI 未知錯誤: %s"), exc)
            raise

    async def ainvoke(self, messages: list[BaseMessage]) -> list[StreamChunk]:
        """Invoke LLM and collect all stream chunks.

        Merges streaming chunks into complete content/think/tool chunks.

        Args:
            messages: List of langchain BaseMessage

        Returns:
            List of complete StreamChunk objects (think, content, tool)
        """
        content_parts: list[str] = []
        think_parts: list[str] = []
        tool_chunks: list[StreamChunk] = []

        async for chunk in self.astream(messages):
            if chunk.chunk_type == "content" and chunk.content:
                content_parts.append(chunk.content)
            elif chunk.chunk_type == "think" and chunk.content:
                think_parts.append(chunk.content)
            elif chunk.chunk_type == "tool":
                tool_chunks.append(chunk)
            # Skip "done" chunk

        result: list[StreamChunk] = []

        if think_parts:
            result.append(
                self._create_chunk(chunk_type="think", content="".join(think_parts))
            )

        if content_parts:
            result.append(
                self._create_chunk(chunk_type="content", content="".join(content_parts))
            )

        result.extend(tool_chunks)

        return result

    def get_resp_content(self, response: list[StreamChunk]) -> str:
        content: str = ""
        for chunk in response:
            if chunk.chunk_type == "content":
                content = chunk.content  # type: ignore
        return content
