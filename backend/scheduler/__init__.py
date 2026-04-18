"""Task scheduler module."""

from __future__ import annotations

from .manager import ScheduleManager

__all__ = ["ScheduleManager", "TaskScheduler"]

# TaskScheduler will be added by scheduler.py in Task 3
def __getattr__(name: str):
    if name == "TaskScheduler":
        from .scheduler import TaskScheduler
        return TaskScheduler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
