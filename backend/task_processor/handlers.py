"""Handler registry for TaskProcessor."""

from __future__ import annotations

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

    從 task.parameters 提取 method 名稱同參數，
    執行對應邏輯，將結果寫入 task.return_message。

    Note:
        目前為框架實現，實際 method 執行邏輯待擴展。
    """
    parameters = task.parameters or {}
    logger.info(
        _("執行 method task %s (agent=%s, params=%s)"),
        task.id,
        agent.agent_id,
        parameters,
    )

    task.status = "completed"
    task.return_message = {"result": "method executed", "parameters": parameters}
    await session.flush()


def register_method_handlers() -> None:
    """註冊所有內置 handler。"""
    register_handler("method", method_handler)
    logger.info(_("已註冊 method handler"))
