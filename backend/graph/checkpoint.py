from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Iterator, Optional, Sequence

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
    message_to_dict,
    messages_from_dict,
)
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    empty_checkpoint,
)

from db.config import async_session_factory
from db.dao import AgentMsgHistDAO, SessionDAO
from db.dto.agent_msg_hist import AgentMsgHistCreate
from i18n import _
from utils.tools import Tools

logger = logging.getLogger(__name__)


class ExtLanggraphCheckpointer(BaseCheckpointSaver):
    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self._run_sync(self.aput(config, checkpoint, metadata, new_versions))

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        del metadata
        del new_versions

        thread_id = self._get_config_str(config, "thread_id")
        step_id = str(checkpoint["id"])
        logger.debug(
            _("ExtLanggraphCheckpointer 寫入 - thread_id: %s, step_id: %s"),
            thread_id,
            step_id,
        )

        messages = checkpoint.get("channel_values", {}).get("messages", [])
        if not messages:
            return config

        latest_message = messages[-1]
        session_id = self._get_config_optional_int(config, "session_db_id")
        if session_id is None:
            session_id = await self._resolve_session_db_id(thread_id)
        records = self._build_records_for_message(
            session_id=session_id,
            step_id=step_id,
            message=latest_message,
            sender_name=self._get_config_str(config, "sender_name"),
            recv_name=self._get_config_str(config, "recv_name"),
        )
        if records:
            await self._persist_records(records)
        return config

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = self._get_config_str(config, "thread_id")
        logger.debug(
            _(
                "ExtLanggraphCheckpointer put_writes - thread_id: %s, task_id: %s, task_path: %s, writes: %s"
            ),
            thread_id,
            task_id,
            task_path,
            len(writes),
        )

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.put_writes(config, writes, task_id, task_path)

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        return self._run_sync(self.aget_tuple(config))

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        thread_id = self._get_config_str(config, "thread_id")
        logger.debug(
            _("ExtLanggraphCheckpointer 讀取 - thread_id: %s"),
            thread_id,
        )

        loaded_step_id, step, payloads = await self._load_checkpoint_messages(config)
        if not loaded_step_id or not payloads:
            return None

        checkpoint = empty_checkpoint()
        checkpoint["id"] = loaded_step_id
        checkpoint["channel_values"]["messages"] = messages_from_dict(payloads)
        return CheckpointTuple(
            config=config,
            checkpoint=checkpoint,
            metadata={"source": "loop", "step": step, "parents": {}},
            parent_config=None,
            pending_writes=None,
        )

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        del filter
        del before
        del limit

        if config is None:
            return iter([])

        checkpoint_tuple = self.get_tuple(config)
        if checkpoint_tuple is None:
            return iter([])
        return iter([checkpoint_tuple])

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    @staticmethod
    def _run_sync(coro: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        raise RuntimeError(_("同步 checkpointer 方法不能在 event loop 內呼叫"))

    @staticmethod
    def _get_config_str(config: RunnableConfig, key: str) -> str:
        configurable = config.get("configurable", {})
        value = configurable.get(key, "")
        return str(value) if value is not None else ""

    @staticmethod
    def _get_config_optional_str(config: RunnableConfig, key: str) -> Optional[str]:
        configurable = config.get("configurable", {})
        value = configurable.get(key)
        return str(value) if value is not None else None

    @staticmethod
    def _get_config_optional_int(config: RunnableConfig, key: str) -> Optional[int]:
        configurable = config.get("configurable", {})
        value = configurable.get(key)
        if value is None:
            return None
        return int(value)

    async def _resolve_session_db_id(self, thread_id: str) -> int:
        async with async_session_factory() as session:
            session_dao = SessionDAO(session)
            session_entity = await session_dao.get_by_session_id(thread_id)
            if session_entity is None:
                raise ValueError(_("找不到 session: %s") % thread_id)
            return session_entity.id

    def _build_records_for_message(
        self,
        *,
        session_id: int,
        step_id: str,
        message: BaseMessage,
        sender_name: str,
        recv_name: str,
    ) -> list[AgentMsgHistCreate]:
        content_json = json.dumps(
            message_to_dict(message),
            ensure_ascii=False,
            default=str,
        )
        create_dt = self._resolve_message_datetime(message)
        records: list[AgentMsgHistCreate] = []

        if isinstance(message, HumanMessage):
            records.append(
                self._build_record(
                    session_id=session_id,
                    step_id=step_id,
                    sender=sender_name,
                    msg_type="human",
                    create_dt=create_dt,
                    content=content_json,
                )
            )
            return records

        if isinstance(message, (AIMessage, AIMessageChunk)):
            tool_calls = getattr(message, "tool_calls", []) or []
            for tool_call in tool_calls:
                tool_name = str(tool_call.get("name") or "tool")
                records.append(
                    self._build_record(
                        session_id=session_id,
                        step_id=step_id,
                        sender=tool_name,
                        msg_type="tool",
                        create_dt=create_dt,
                        content=content_json,
                    )
                )

            content = self._stringify_content(message.content)
            if content:
                records.append(
                    self._build_record(
                        session_id=session_id,
                        step_id=step_id,
                        sender=recv_name,
                        msg_type="ai",
                        create_dt=create_dt,
                        content=content_json,
                    )
                )
            return records

        if isinstance(message, ToolMessage):
            tool_name = message.name or "tool"
            records.append(
                self._build_record(
                    session_id=session_id,
                    step_id=step_id,
                    sender=tool_name,
                    msg_type="tool_result",
                    create_dt=create_dt,
                    content=content_json,
                )
            )
        return records

    @staticmethod
    def _build_record(
        *,
        session_id: int,
        step_id: str,
        sender: str,
        msg_type: str,
        create_dt: datetime,
        content: str,
        token: Optional[int] = None,
    ) -> AgentMsgHistCreate:
        return AgentMsgHistCreate(
            session_id=session_id,
            step_id=step_id,
            sender=sender,
            msg_type=msg_type,
            create_dt=create_dt,
            content=content,
            token=Tools.get_token_count(content) if token is None else token,
            is_stm_summary=False,
            is_ltm_summary=False,
            is_analyst=0,
        )

    async def _persist_records(self, records: list[AgentMsgHistCreate]) -> None:
        async with async_session_factory() as session:
            dao = AgentMsgHistDAO(session)
            for record in records:
                await dao.create_from_dto(record)
            await session.commit()

    async def _load_checkpoint_messages(
        self,
        config: RunnableConfig,
    ) -> tuple[Optional[str], int, list[dict[str, Any]]]:
        thread_id = self._get_config_str(config, "thread_id")
        async with async_session_factory() as session:
            session_dao = SessionDAO(session)
            session_entity = await session_dao.get_by_session_id(thread_id)
            if session_entity is None:
                return None, -2, []
            session_id = session_entity.id

            dao = AgentMsgHistDAO(session)
            entities = await dao.list_unsummarized_by_session(session_id)
            payloads = []
            for entity in entities:
                try:
                    payload = json.loads(entity.content)
                    payloads.append(payload)
                except (json.JSONDecodeError, TypeError):
                    continue

            unique_payloads: list[dict[str, Any]] = []
            seen_payloads: set[str] = set()
            for payload in payloads:
                key = json.dumps(payload, sort_keys=True, ensure_ascii=False)
                if key in seen_payloads:
                    continue
                seen_payloads.add(key)
                unique_payloads.append(payload)

            step = max(len(unique_payloads) - 2, -1)
            latest_step_id = entities[-1].step_id if entities else None
            return latest_step_id, step, unique_payloads

    @staticmethod
    def _stringify_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if content is None:
            return ""
        return str(content)

    @staticmethod
    def _extract_token(message: AIMessage | AIMessageChunk) -> int:
        usage_metadata = getattr(message, "usage_metadata", None) or {}
        total_tokens = usage_metadata.get("total_tokens")
        if isinstance(total_tokens, int):
            return total_tokens

        response_metadata = getattr(message, "response_metadata", {}) or {}
        token_usage = response_metadata.get("token_usage", {})
        total_tokens = token_usage.get("total_tokens")
        return total_tokens if isinstance(total_tokens, int) else 0

    @staticmethod
    def _resolve_message_datetime(message: BaseMessage) -> datetime:
        additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
        raw_value = additional_kwargs.get("datetime")
        if isinstance(raw_value, datetime):
            return raw_value
        if isinstance(raw_value, str):
            try:
                return datetime.fromisoformat(raw_value)
            except ValueError:
                pass
        return datetime.now(timezone.utc)
