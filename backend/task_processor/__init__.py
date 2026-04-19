"""TaskProcessor — DB task background execution."""

from __future__ import annotations

from .handlers import get_handler, method_handler, register_handler, register_method_handlers
from .processor import TaskProcessor

__all__ = [
    "TaskProcessor",
    "register_handler",
    "get_handler",
    "method_handler",
    "register_method_handlers",
]
