"""Memory Store - Session-level memory management."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

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
    
    def __init__(self, session_db_id: int):
        self._session_db_id = session_db_id
        self._cache = SessionMemoryCache(session_db_id=session_db_id)
        self._pending_commits: dict[str, dict] = {}
    
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
        messages.extend(self._cache.stm_messages)
        
        # 3. Old Messages（≤ 20000 token，取最新）
        old_messages = self._get_old_messages_within_token_limit()
        messages.extend(old_messages)
        
        # 4. Current Date Time
        current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        messages.append(SystemMessage(content=_("當前時間：%s") % current_time))
        
        # 5. LTM（如果 message 係 HumanMessage）
        ltm_message: Optional[AIMessage] = None
        if isinstance(message, HumanMessage):
            ltm_message = await self._search_ltm(message)
            if ltm_message:
                messages.append(ltm_message)
        
        # 6. Last Message
        messages.append(message)
        
        # 7. 記住消息等 commit
        self._pending_commits[step_id] = {
            "ltm_message": ltm_message,
            "last_message": message,
        }
        
        return messages
    
    async def _load_from_db(self) -> None:
        """從 DB 加載 STM 同 Old Messages 到 RAM cache。"""
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
            
            # 加載 Old Messages（≤ 20000 token）
            all_histories = await hist_dao.list_unsummarized_by_session(self._session_db_id)
            self._cache.old_messages = []
            current_token = 0
            
            # 從最新開始取（按 id 倒序）
            for hist in reversed(all_histories):
                if current_token + hist.token > 20000 and self._cache.old_messages:
                    break
                self._cache.old_messages.append((hist.step_id or "", self._message_from_entity(hist)))
                current_token += hist.token
            
            # 反轉回舊到新嘅順序
            self._cache.old_messages.reverse()
    
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
                user_query=message.content,
                session_db_id=str(self._session_db_id),
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
        response: Optional[AIMessage] = None,
    ) -> None:
        """保存消息到 DB 同更新 Old Message List。
        
        流程：
        1. 檢查重複（比較同一 step_id 最後一條記錄嘅 msg_type 同 content）
        2. 保存 LTM（如果有且未保存）
        3. 保存 Last Message（如果未重複）
        4. 保存 Response（根據類型）
        5. 更新 Old Message List
        """
        if step_id not in self._pending_commits:
            logger.warning(_("Step %s 沒有待提交嘅消息"), step_id)
            return
        
        pending = self._pending_commits[step_id]
        ltm_message: Optional[AIMessage] = pending.get("ltm_message")
        last_message: BaseMessage = pending.get("last_message")
        
        async with async_session_factory() as session:
            hist_dao = AgentMsgHistDAO(session)
            
            # 獲取當前 msg_idx 起始值
            msg_idx_counter = await hist_dao.count_by_step(self._session_db_id, step_id) + 1
            
            messages_to_save: list[tuple[BaseMessage, str, str]] = []
            
            # 1. 保存 LTM（msg_type = "system", sender = "System"）
            if ltm_message:
                # 檢查重複
                last_record = await hist_dao.get_last_by_step(self._session_db_id, step_id)
                if not last_record or last_record.msg_type != "system" or last_record.content != ltm_message.content:
                    messages_to_save.append((ltm_message, "System", "system"))
            
            # 2. 保存 Last Message（檢查重複）
            last_record = await hist_dao.get_last_by_step(self._session_db_id, step_id)
            last_msg_type = self._get_msg_type(last_message)
            last_content = last_message.content
            last_sender = self._get_sender(last_message)
            
            if not last_record or last_record.msg_type != last_msg_type or last_record.content != last_content:
                messages_to_save.append((last_message, last_sender, last_msg_type))
            
            # 3. 保存 Response（根據類型）
            if response:
                response_type, response_sender = self._classify_response(response)
                messages_to_save.append((response, response_sender, response_type))
            
            # 4. 批量保存
            now = datetime.now(timezone.utc)
            saved_messages = []
            
            for message_obj, sender, msg_type in messages_to_save:
                content = message_obj.content
                if isinstance(content, list):
                    content = json.dumps(content, ensure_ascii=False)
                
                token = Tools.get_token_count(content)
                
                dto = AgentMsgHistCreate(
                    session_id=self._session_db_id,
                    step_id=step_id,
                    msg_idx=msg_idx_counter,
                    sender=sender,
                    msg_type=msg_type,
                    create_dt=now,
                    content=content,
                    token=token,
                    is_stm_summary=False,
                    is_ltm_summary=False,
                    is_analyst=0,
                )
                
                await hist_dao.create_from_dto(dto)
                saved_messages.append((step_id, message_obj))
                msg_idx_counter += 1
            
            await session.commit()
            
            # 5. 更新 Old Message List
            self._cache.old_messages.extend(saved_messages)
            
            # 6. 清理 pending
            del self._pending_commits[step_id]
    
    def _get_msg_type(self, message: BaseMessage) -> str:
        """獲取消息類型。"""
        if isinstance(message, HumanMessage):
            return "human"
        elif isinstance(message, AIMessage):
            return "ai"
        elif isinstance(message, SystemMessage):
            return "system"
        else:
            return "ai"
    
    def _get_sender(self, message: BaseMessage) -> str:
        """獲取消息發送者。"""
        if isinstance(message, HumanMessage):
            return "Human"
        elif isinstance(message, AIMessage):
            return "AI"
        elif isinstance(message, SystemMessage):
            return "System"
        else:
            return "AI"
    
    def _classify_response(self, response: AIMessage) -> tuple[str, str]:
        """分類 Response 消息類型。
        
        Returns:
            (msg_type, sender)
        """
        # 檢查有冇 reasoning content
        if hasattr(response, "response_metadata") and response.response_metadata:
            thinking = response.response_metadata.get("thinking")
            if thinking:
                return ("reasoning", "AI")
        
        # 檢查有冇 tool_calls
        if hasattr(response, "tool_calls") and response.tool_calls:
            return ("tool_call", "AI")
        
        # 正常 AI 回覆
        return ("ai", "AI")
    
    async def update_after_summary(self, step_ids: list[str]) -> None:
        """review_stm 完成後調用。
        
        流程：
        1. 從 old_messages 刪除 step_id 匹配嘅消息
        2. 重新加載 STM
        3. 更新 cache
        """
        # 1. 從 old_messages 刪除匹配嘅消息
        self._cache.old_messages = [
            (sid, msg) for sid, msg in self._cache.old_messages
            if sid not in step_ids
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
            _("MemoryStore 更新完成：session=%s, 刪除 %s 個 step, STM 消息數=%s"),
            self._session_db_id,
            len(step_ids),
            len(self._cache.stm_messages),
        )
