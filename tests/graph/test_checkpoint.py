from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, message_to_dict

from db.dto.agent_msg_hist import AgentMsgHistCreate
from graph.checkpoint import ExtLanggraphCheckpointer
from utils.tools import Tools


def test_agent_msg_hist_create_supports_audit_fields() -> None:
    dto = AgentMsgHistCreate(
        session_id=1,
        thread_id="thread-1",
        checkpoint_id="checkpoint-1",
        message_idx=0,
        sender="Tester",
        msg_type="human",
        tool_call_id=None,
        tool_name=None,
        create_dt="2026-04-13T00:00:00+00:00",
        content="hello",
        payload_json='{"type":"human"}',
        token=0,
        is_stm_summary=False,
        is_ltm_summary=False,
        is_analyst=0,
    )

    assert dto.thread_id == "thread-1"
    assert dto.checkpoint_id == "checkpoint-1"
    assert dto.message_idx == 0
    assert dto.is_stm_summary is False
    assert dto.is_ltm_summary is False


def test_checkpointer_aput_persists_latest_ai_message_and_tool_calls() -> None:
    async def run() -> None:
        checkpointer = ExtLanggraphCheckpointer()
        captured: list[AgentMsgHistCreate] = []

        async def fake_resolve_session_db_id(thread_id: str) -> int:
            assert thread_id == "thread-1"
            return 11

        async def fake_persist_records(records: list[AgentMsgHistCreate]) -> None:
            captured.extend(records)

        checkpointer._resolve_session_db_id = fake_resolve_session_db_id  # type: ignore[attr-defined]
        checkpointer._persist_records = fake_persist_records  # type: ignore[attr-defined]

        checkpoint = {
            "id": "checkpoint-1",
            "channel_values": {
                "messages": [
                    HumanMessage(content="hi"),
                    AIMessage(
                        content="Let me check",
                        tool_calls=[
                            {
                                "name": "web_search",
                                "args": {"query": "weather"},
                                "id": "call-1",
                                "type": "tool_call",
                            }
                        ],
                        response_metadata={"token_usage": {"total_tokens": 9}},
                    ),
                ]
            },
        }
        config = {
            "configurable": {
                "thread_id": "thread-1",
                "sender_name": "用戶",
                "recv_name": "小丸",
            }
        }

        await checkpointer.aput(config, checkpoint, {}, {})

        assert [record.msg_type for record in captured] == ["tool", "ai"]
        assert [record.sender for record in captured] == ["web_search", "小丸"]
        assert captured[0].session_id == 11
        assert captured[0].thread_id == "thread-1"
        assert captured[0].checkpoint_id == "checkpoint-1"
        assert captured[0].message_idx == 1
        assert json.loads(captured[0].content) == {
            "name": "web_search",
            "args": {"query": "weather"},
        }
        assert captured[0].token == Tools.get_token_count(captured[0].content)
        assert captured[1].content == "Let me check"
        assert captured[1].token == Tools.get_token_count("Let me check")

    asyncio.run(run())


def test_checkpointer_aput_persists_latest_tool_result_message() -> None:
    async def run() -> None:
        checkpointer = ExtLanggraphCheckpointer()
        captured: list[AgentMsgHistCreate] = []

        async def fake_resolve_session_db_id(thread_id: str) -> int:
            assert thread_id == "thread-2"
            return 12

        async def fake_persist_records(records: list[AgentMsgHistCreate]) -> None:
            captured.extend(records)

        checkpointer._resolve_session_db_id = fake_resolve_session_db_id  # type: ignore[attr-defined]
        checkpointer._persist_records = fake_persist_records  # type: ignore[attr-defined]

        checkpoint = {
            "id": "checkpoint-2",
            "channel_values": {
                "messages": [
                    HumanMessage(content="hi"),
                    ToolMessage(content="sunny", tool_call_id="call-1", name="web_search"),
                ]
            },
        }
        config = {
            "configurable": {
                "thread_id": "thread-2",
                "sender_name": "用戶",
                "recv_name": "小丸",
            }
        }

        await checkpointer.aput(config, checkpoint, {}, {})

        assert len(captured) == 1
        assert captured[0].msg_type == "tool_result"
        assert captured[0].sender == "web_search"
        assert captured[0].tool_call_id == "call-1"
        assert captured[0].tool_name == "web_search"
        assert captured[0].content == "sunny"
        assert captured[0].token == Tools.get_token_count("sunny")

    asyncio.run(run())


def test_checkpointer_aget_tuple_rebuilds_messages_from_history() -> None:
    async def run() -> None:
        checkpointer = ExtLanggraphCheckpointer()

        async def fake_load_checkpoint_messages(config: dict):
            return (
                "checkpoint-9",
                1,
                [
                    message_to_dict(HumanMessage(content="hi")),
                    message_to_dict(AIMessage(content="hello")),
                    message_to_dict(
                        ToolMessage(
                            content="sunny",
                            tool_call_id="call-1",
                            name="web_search",
                        )
                    ),
                ],
            )

        checkpointer._load_checkpoint_messages = fake_load_checkpoint_messages  # type: ignore[attr-defined]
        config = {"configurable": {"thread_id": "thread-9"}}

        result = await checkpointer.aget_tuple(config)

        assert result is not None
        assert result.config == config
        assert result.checkpoint["id"] == "checkpoint-9"
        assert result.metadata["step"] == 1
        assert result.metadata["source"] == "loop"
        messages = result.checkpoint["channel_values"]["messages"]
        assert [message.type for message in messages] == ["human", "ai", "tool"]
        assert messages[0].content == "hi"
        assert messages[1].content == "hello"
        assert messages[2].content == "sunny"

    asyncio.run(run())
