"""SessionMemoryCache tests."""

from __future__ import annotations

import sys
from pathlib import Path

# Add backend to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from memory.models import SessionMemoryCache


def test_cache_initialization():
    """測試 cache 初始化。"""
    cache = SessionMemoryCache(session_db_id=123)
    assert cache.session_db_id == 123
    assert cache.stm_messages == []
    assert cache.old_messages == []
    assert cache.is_initialized == False


def test_cache_with_messages():
    """測試添加消息到 cache。"""
    cache = SessionMemoryCache(session_db_id=123)
    cache.stm_messages.append(SystemMessage(content="STM 1"))
    cache.old_messages.append(("step_1", HumanMessage(content="Hello")))
    
    assert len(cache.stm_messages) == 1
    assert len(cache.old_messages) == 1
    assert cache.old_messages[0][0] == "step_1"
