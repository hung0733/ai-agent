"""Memory Store - Session-level memory management."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from db.config import async_session_factory
from db.dao.agent_msg_hist_dao import AgentMsgHistDAO
from db.dao.short_term_mem_dao import ShortTermMemDAO
from db.dto.agent_msg_hist import AgentMsgHistCreate
from i18n import _
from memory.models import SessionMemoryCache
from utils.tools import Tools

logger = logging.getLogger(__name__)


class MemoryStore:
    """每個 session 獨立嘅 memory store。

    職責：
    - RAM cache 管理（STM + Old Messages）
    - DB 數據加載同同步
    - LTM 搜索協調
    - 消息組裝同持久化
    """

    # 類變量：共享所有實例嘅 pending commits（因為每次調用都會創建新實例）
    _pending_commits: dict[str, list[AgentMsgHistCreate]] = {}

    def __init__(self, session_db_id: int):
        self._session_db_id = session_db_id
        self._cache = SessionMemoryCache(session_db_id=session_db_id)
        logger.debug(_("MemoryStore 已建立：session=%s"), session_db_id)

    async def prepare_messages(
        self,
        step_id: str,
        message: BaseMessage,
    ) -> list[BaseMessage]:
        """組裝消息列表並返回。

        輸出次序：
        1. STM Messages（≤ 10000 token）
        2. Old Messages（≤ 20000 token，取最新）
        3. Current Date Time
        4. LTM（如果 message 係 HumanMessage）
        5. Last Message（傳入嘅 message）
        """
        # 1. 檢查 RAM cache，如果未初始化就從 DB 加載
        if not self._cache.is_initialized:
            await self._load_from_db()
            self._cache.is_initialized = True

        messages: list[BaseMessage] = []

        # 2. STM Messages（≤ 10000 token）
        stm_token_count = 0
        for stm_msg in self._cache.stm_messages:
            messages.append(stm_msg)
            stm_token_count += Tools.get_token_count(stm_msg.content)

        if self._cache.stm_messages:
            logger.info(
                _("STM Messages, Count: %s, Token: %s"),
                len(self._cache.stm_messages),
                stm_token_count,
            )

        # 3. Old Messages（≤ 20000 token，取最新）
        old_messages = self._get_old_messages_within_token_limit()
        old_msg_count = 0
        old_token_count = 0
        old_len = 0
        for old_msg in old_messages:
            messages.append(old_msg)
            old_msg_count += 1
            old_token_count += Tools.get_token_count(old_msg.content)
            old_len += len(old_msg.content)

        logger.info(
            _("Old Messages, Count: %s, Length: %s, Token: %s"),
            old_msg_count,
            old_len,
            old_token_count,
        )
        messages.extend(old_messages)

        # 4. Current Date Time
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        current_time_msg = SystemMessage(content=_("當前時間：%s") % current_time)
        messages.append(current_time_msg)
        logger.debug(
            _("Current Date Time, Token: %s"),
            Tools.get_token_count(current_time_msg.content),
        )

        # 5. LTM（如果 message 係 HumanMessage）
        ltm_message: Optional[AIMessage] = None
        if isinstance(message, HumanMessage):
            ltm_message = await self._search_ltm(message)
            if ltm_message:
                messages.append(ltm_message)
                logger.info(
                    _("LTM Result, Token: %s"),
                    Tools.get_token_count(ltm_message.content),
                )

        # 6. Last Message
        messages.append(message)
        last_token = Tools.get_token_count(message.content)
        logger.info(
            _("Last Message, Length: %s, Token: %s"),
            len(message.content),
            last_token,
        )
        logger.debug(_("Last Message: %s"), message.content)

        # 7. 記住消息等 commit
        MemoryStore._pending_commits[step_id] = []
        if isinstance(message, (HumanMessage)):
            if ltm_message:
                MemoryStore._pending_commits[step_id].append(
                    AgentMsgHistCreate(
                        session_id=self._session_db_id,
                        step_id=step_id,
                        sender="System",
                        msg_type="system",
                        create_dt=message.additional_kwargs.get(
                            "datetime", datetime.now(timezone.utc)
                        ),
                        content=ltm_message.content if ltm_message.content else "",  # type: ignore
                        token=Tools.get_token_count(ltm_message.content),
                        is_stm_summary=False,
                        is_ltm_summary=False,
                        is_analyst=0,
                    )
                )

            MemoryStore._pending_commits[step_id].append(
                AgentMsgHistCreate(
                    session_id=self._session_db_id,
                    step_id=step_id,
                    sender="User",
                    msg_type="human",
                    create_dt=message.additional_kwargs.get(
                        "datetime", datetime.now(timezone.utc)
                    ),
                    content=message.content if message.content else "",  # type: ignore
                    token=Tools.get_token_count(message.content),
                    is_stm_summary=False,
                    is_ltm_summary=False,
                    is_analyst=0,
                )
            )

        if MemoryStore._pending_commits[step_id]:
            logger.info(
                _("已記住消息等待 commit：step=%s, 數量=%s"),
                step_id,
                len(MemoryStore._pending_commits[step_id]),
            )
        else:
            logger.debug(
                _("無消息需要記住：step=%s（非 HumanMessage）"),
                step_id,
            )

        # 總計 log
        total_token = (
            stm_token_count
            + old_token_count
            + Tools.get_token_count(current_time_msg.content)
        )
        if ltm_message:
            total_token += Tools.get_token_count(ltm_message.content)
        total_token += last_token

        logger.info(
            _("Total Messages, Count: %s, Token: %s"),
            len(messages),
            total_token,
        )

        return messages

    async def _load_from_db(self) -> None:
        """從 DB 加載 STM 同 Old Messages 到 RAM cache。"""
        logger.debug(_("開始從 DB 加載記憶：session=%s"), self._session_db_id)
        async with async_session_factory() as session:
            stm_dao = ShortTermMemDAO(session)
            hist_dao = AgentMsgHistDAO(session)

            # 加載 STM（≤ 10000 token）
            stm_entities = await stm_dao.list_recent_by_token_limit(
                self._session_db_id, max_token=10000
            )
            self._cache.stm_messages = [
                SystemMessage(content=_("短期記憶摘要：\n%s") % stm.content)
                for stm in stm_entities
            ]
            logger.debug(
                _("STM 加載完成：session=%s, 消息數=%s"),
                self._session_db_id,
                len(stm_entities),
            )

            # 加載 Old Messages（≤ 20000 token）
            all_histories = await hist_dao.list_unsummarized_by_session(
                self._session_db_id
            )
            self._cache.old_messages = []
            current_token = 0

            # 從最新開始取（按 id 倒序）
            for hist in reversed(all_histories):
                if current_token + hist.token > 20000 and self._cache.old_messages:
                    break
                self._cache.old_messages.append(
                    (hist.step_id or "", self._message_from_entity(hist))
                )
                current_token += hist.token

            # 反轉回舊到新嘅順序
            self._cache.old_messages.reverse()

            logger.debug(
                _("Old Messages 加載完成：session=%s, 消息數=%s, Token=%s"),
                self._session_db_id,
                len(self._cache.old_messages),
                current_token,
            )

    def _message_from_entity(self, entity) -> BaseMessage:
        """將 AgentMsgHistEntity 轉換為 BaseMessage。"""
        if entity.msg_type == "human":
            return HumanMessage(content=entity.content)
        elif entity.msg_type in ("ai", "AIMessage", "AIMessageChunk"):
            return AIMessage(content=entity.content)
        elif entity.msg_type in ("tool", "ToolMessage"):
            from langchain_core.messages import ToolMessage

            return ToolMessage(content=entity.content, tool_call_id="")
        elif entity.msg_type == "system":
            return SystemMessage(content=entity.content)
        else:
            return AIMessage(content=entity.content)

    def _get_old_messages_within_token_limit(self) -> list[BaseMessage]:
        """獲取 ≤ 20000 token 嘅 Old Messages（從最新開始取）。"""
        messages: list[BaseMessage] = []
        current_token = 0

        # 從最新開始取（倒序）
        for step_id, message in reversed(self._cache.old_messages):
            token = Tools.get_token_count(message.content)
            if current_token + token > 20000 and messages:
                break
            messages.append(message)
            current_token += token

        # 反轉回舊到新嘅順序
        messages.reverse()
        return messages

    async def _search_ltm(self, message: HumanMessage) -> Optional[AIMessage]:
        """搜索 LTM 並返回格式化嘅 AIMessage。"""
        try:
            from agent.ltm_search import search_ltm_for_chat

            ltm_json_content = await search_ltm_for_chat(
                user_query=message.content,  # type: ignore
                session_db_id=self._session_db_id,
            )

            if not ltm_json_content:
                return None

            return AIMessage(
                content=_("長期記憶檢索結果：\n{}").format(ltm_json_content)
            )
        except Exception as exc:
            logger.warning(_("LTM 搜索失敗，跳過：%s"), exc)
            return None

    async def commit_messages(
        self,
        step_id: str,
        sender_name: str,
        recv_name: str,
        responses: list[BaseMessage],
    ) -> None:
        """保存消息到 DB 同更新 Old Message List。

        流程：
        1. 保存 pending DTOs（LTM 等）
        2. 保存 Response（根據類型）
        3. 更新 Old Message List
        """
        if step_id not in MemoryStore._pending_commits:
            logger.warning(_("Step %s 沒有待提交嘅消息"), step_id)

        save_dtos: list[AgentMsgHistCreate] = []
        save_dtos.extend(MemoryStore._pending_commits[step_id])

        logger.debug(
            _("開始解包 responses：step=%s, 數量=%s"),
            step_id,
            len(responses),
        )

        for response in responses:
            unpacked = self._unpack_message(step_id, response, sender_name, recv_name)
            logger.debug(
                _("解包 %s 消息：step=%s, 生成 %s 條 DTO"),
                type(response).__name__,
                step_id,
                len(unpacked),
            )
            save_dtos.extend(unpacked)

        logger.info(
            _("準備提交消息：session=%s, step=%s, 數量=%s"),
            self._session_db_id,
            step_id,
            len(save_dtos),
        )

        saved_messages = []
        async with async_session_factory() as session:
            hist_dao = AgentMsgHistDAO(session)

            # 獲取當前 msg_idx 起始值
            msg_idx_counter = (
                await hist_dao.count_by_step(self._session_db_id, step_id) + 1
            )

            # 1. 保存 pending DTOs（LTM 等）
            for msg in save_dtos:
                msg.msg_idx = msg_idx_counter
                msg_idx_counter += 1

                await hist_dao.create_from_dto(msg)
                saved_messages.append((step_id, msg))
                msg_idx_counter += 1

            await session.commit()

        # 3. 更新 Old Message List
        self._cache.old_messages.extend(saved_messages)

        # 4. 清理 pending
        del MemoryStore._pending_commits[step_id]

        logger.info(
            _("MemoryStore 提交完成：session=%s, step=%s, 保存 %s 條消息"),
            self._session_db_id,
            step_id,
            len(saved_messages),
        )

    def _unpack_message(
        self, step_id: str, response: BaseMessage, sender_name: str, recv_name: str
    ) -> list[AgentMsgHistCreate]:
        msg: list[AgentMsgHistCreate] = []

        if isinstance(response, (AIMessage, HumanMessage)):
            reasoning_content = response.additional_kwargs.get("reasoning_content")
            if reasoning_content:
                logger.debug(
                    _("解包 Reasoning 消息：step=%s, token=%s"),
                    step_id,
                    Tools.get_token_count(reasoning_content),
                )
                msg.append(
                    AgentMsgHistCreate(
                        session_id=self._session_db_id,
                        step_id=step_id,
                        sender=self._get_sender("reasoning", sender_name, recv_name),
                        msg_type="reasoning",
                        create_dt=response.additional_kwargs.get(
                            "datetime", datetime.now(timezone.utc)
                        ),
                        content=reasoning_content,
                        token=Tools.get_token_count(reasoning_content),
                        is_stm_summary=False,
                        is_ltm_summary=False,
                        is_analyst=0,
                    )
                )

            if response.content:
                msg.append(
                    AgentMsgHistCreate(
                        session_id=self._session_db_id,
                        step_id=step_id,
                        sender=self._get_sender(
                            self._get_msg_type(response), sender_name, recv_name
                        ),
                        msg_type=self._get_msg_type(response),
                        create_dt=response.additional_kwargs.get(
                            "datetime", datetime.now(timezone.utc)
                        ),
                        content=response.content,  # type: ignore
                        token=Tools.get_token_count(response.content),
                        is_stm_summary=False,
                        is_ltm_summary=False,
                        is_analyst=0,
                    )
                )

        if isinstance(response, AIMessage):
            if hasattr(response, "tool_calls") and len(response.tool_calls) > 0:
                logger.debug(
                    _("解包 Tool Calls：step=%s, 數量=%s"),
                    step_id,
                    len(response.tool_calls),
                )
                for tc in getattr(response, "tool_calls", []):
                    name = tc.get("name", "")
                    if name:
                        msg.append(
                            AgentMsgHistCreate(
                                session_id=self._session_db_id,
                                step_id=step_id,
                                sender=self._get_sender(
                                    "use_tool", sender_name, recv_name
                                ),
                                msg_type="use_tool",
                                create_dt=response.additional_kwargs.get(
                                    "datetime", datetime.now(timezone.utc)
                                ),
                                content=name,  # type: ignore
                                token=Tools.get_token_count(name),
                                is_stm_summary=False,
                                is_ltm_summary=False,
                                is_analyst=0,
                                metadata=tc,
                            )
                        )

        if isinstance(response, ToolMessage):
            content = (
                response.content
                if isinstance(response.content, str)
                else str(response.content)
            )
            if content:
                msg.append(
                    AgentMsgHistCreate(
                        session_id=self._session_db_id,
                        step_id=step_id,
                        sender=self._get_sender(
                            self._get_msg_type(response), sender_name, recv_name
                        ),
                        msg_type=self._get_msg_type(response),
                        create_dt=response.additional_kwargs.get(
                            "datetime", datetime.now(timezone.utc)
                        ),
                        content=content,  # type: ignore
                        token=Tools.get_token_count(content),
                        is_stm_summary=False,
                        is_ltm_summary=False,
                        is_analyst=0,
                    )
                )

        return msg

    def _get_msg_type(self, message: BaseMessage) -> str:
        """獲取消息類型。"""
        if isinstance(message, HumanMessage):
            return "human"
        elif isinstance(message, AIMessage):
            return "ai"
        elif isinstance(message, SystemMessage):
            return "system"
        elif isinstance(message, ToolMessage):
            return "tool_result"
        else:
            return "ai"

    def _get_sender(self, msg_type: str, sender_name: str, recv_name: str) -> str:
        """獲取消息發送者。"""
        if msg_type == "human":
            return sender_name
        elif msg_type == "ai":
            return recv_name
        elif msg_type == "system":
            return "System"
        elif msg_type == "use_tool":
            return recv_name
        elif msg_type == "reasoning":
            return recv_name
        elif msg_type == "tool_result":
            return "System"
        return ""

    async def update_after_summary(self, step_ids: list[str]) -> None:
        """review_stm 完成後調用。

        流程：
        1. 從 old_messages 刪除 step_id 匹配嘅消息
        2. 重新加載 STM
        3. 更新 cache
        """
        logger.info(
            _("開始更新 MemoryStore：session=%s, 刪除 %s 個 step"),
            self._session_db_id,
            len(step_ids),
        )

        # 1. 從 old_messages 刪除匹配嘅消息
        old_count = len(self._cache.old_messages)
        self._cache.old_messages = [
            (sid, msg) for sid, msg in self._cache.old_messages if sid not in step_ids
        ]

        # 2. 重新加載 STM
        async with async_session_factory() as session:
            stm_dao = ShortTermMemDAO(session)
            stm_entities = await stm_dao.list_recent_by_token_limit(
                self._session_db_id, max_token=10000
            )
            self._cache.stm_messages = [
                SystemMessage(content=_("短期記憶摘要：\n%s") % stm.content)
                for stm in stm_entities
            ]

        logger.info(
            _(
                "MemoryStore 更新完成：session=%s, 刪除 %s 個 step, Old Messages %s→%s, STM 消息數=%s"
            ),
            self._session_db_id,
            len(step_ids),
            old_count,
            len(self._cache.old_messages),
            len(self._cache.stm_messages),
        )
