"""Handler registry for TaskProcessor."""

from __future__ import annotations

import importlib
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.entity import AgentEntity, TaskEntity
from i18n import _

logger = logging.getLogger(__name__)

HandlerFunc = Callable[[TaskEntity, AgentEntity, AsyncSession], Awaitable[None]]

_HANDLERS: Dict[str, HandlerFunc] = {}


def register_handler(task_type: str, handler: HandlerFunc) -> None:
    """註冊 task handler。

    Args:
        task_type: Task 類型（如 "method", "message", "workflow"）。
        handler: 異步處理函數。
    """
    _HANDLERS[task_type] = handler
    logger.debug(_("已註冊 handler task_type=%s"), task_type)


def get_handler(task_type: str) -> Optional[HandlerFunc]:
    """獲取 task handler。

    Args:
        task_type: Task 類型。

    Returns:
        Handler 函數，如果不存在則返回 None。
    """
    return _HANDLERS.get(task_type)


async def method_handler(
    task: TaskEntity, agent: AgentEntity, session: AsyncSession
) -> None:
    """執行 method 類型 task。

    解析 task.content 格式：/agent/summary@review_ltm 或 /agent/summary@ClassName.method_name。
    動態導入對應 module，調用方法並傳入 agent.agent_id（string），
    將返回的 json 結果寫入 task.return_message。
    """
    content = task.content
    if "@" not in content:
        raise ValueError(_("task.content 格式錯誤，缺少 '@' 分隔符: %s") % content)

    module_path, method_ref = content.split("@", 1)

    # 轉換 module path: /agent/summary → backend.agent.summary
    module_name = "backend." + module_path.strip("/").replace("/", ".")

    # 動態導入 module
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        raise ValueError(_("無法導入 module %s: %s") % (module_name, e))

    # 獲取方法
    if "." in method_ref:
        # ClassName.method_name 格式
        class_name, method_name = method_ref.split(".", 1)
        try:
            cls = getattr(module, class_name)
            method = getattr(cls, method_name)
        except AttributeError as e:
            raise ValueError(_("無法獲取方法 %s.%s: %s") % (module_name, method_ref, e))
    else:
        # 直接函數名
        try:
            method = getattr(module, method_ref)
        except AttributeError as e:
            raise ValueError(_("無法獲取函數 %s.%s: %s") % (module_name, method_ref, e))

    logger.info(
        _("執行 method %s.%s (agent=%s)"),
        module_name,
        method_ref,
        agent.agent_id,
    )

    # 調用方法（傳入 agent_id string）
    try:
        result = await method(agent_id=agent.agent_id)
    except Exception as e:
        logger.error(_("方法執行失敗 %s.%s: %s"), module_name, method_ref, e)
        raise

    # 驗證返回值是 dict
    if not isinstance(result, dict):
        raise ValueError(_("方法 %s.%s 返回值不是 dict: %s") % (module_name, method_ref, type(result).__name__))

    # 寫入結果
    task.status = "completed"
    task.return_message = result
    await session.flush()


def register_method_handlers() -> None:
    """註冊所有內置 handler。"""
    register_handler("method", method_handler)
    logger.info(_("已註冊 method handler"))
