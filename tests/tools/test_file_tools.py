"""Tests for LangChain file tool wrappers.

Verifies that tools are correctly created with proper names,
delegate to SandboxFileSystem properly, and handle errors
with user-friendly strings.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.tools import SandboxFileSystem
from backend.tools.file_tools import get_file_tools


@pytest.fixture
def sandbox():
    """創建測試用 sandbox。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        agent_id = "test-agent-tools"
        base_dir = Path(tmpdir) / "agents"
        yield SandboxFileSystem(agent_id=agent_id, base_dir=str(base_dir))


@pytest.fixture
def tools(sandbox):
    """創建綁咗 sandbox 嘅 tools。"""
    return get_file_tools(sandbox)


@pytest.mark.asyncio
async def test_get_file_tools_returns_list(tools):
    """測試 get_file_tools 返回 tool 列表。"""
    assert isinstance(tools, list)
    assert len(tools) == 8


@pytest.mark.asyncio
async def test_tool_names(tools):
    """測試 tool 名稱正確。"""
    names = [t.name for t in tools]
    expected = [
        "read_file", "write_file", "list_dir", "delete",
        "copy_file", "move_file", "search_files", "run_script",
    ]
    assert names == expected


@pytest.mark.asyncio
async def test_read_file_tool(sandbox, tools):
    """測試 read_file tool。"""
    await sandbox.write_file("/mnt/user-data/workspace/test.txt", "hello")

    tool = next(t for t in tools if t.name == "read_file")
    result = await tool.ainvoke({"path": "/mnt/user-data/workspace/test.txt"})
    assert result == "hello"


@pytest.mark.asyncio
async def test_read_file_not_found_tool(sandbox, tools):
    """測試 read_file 檔案不存在。"""
    tool = next(t for t in tools if t.name == "read_file")
    result = await tool.ainvoke({"path": "/mnt/user-data/workspace/nope.txt"})
    assert "未搵到" in result


@pytest.mark.asyncio
async def test_write_file_tool(sandbox, tools):
    """測試 write_file tool。"""
    tool = next(t for t in tools if t.name == "write_file")
    result = await tool.ainvoke({
        "path": "/mnt/user-data/workspace/out.txt",
        "content": "written by tool",
    })
    assert "已寫入" in result

    content = await sandbox.read_file("/mnt/user-data/workspace/out.txt")
    assert content == "written by tool"


@pytest.mark.asyncio
async def test_write_file_uploads_forbidden(sandbox, tools):
    """測試 write_file 唔可以寫入 uploads。"""
    tool = next(t for t in tools if t.name == "write_file")
    result = await tool.ainvoke({
        "path": "/mnt/user-data/uploads/blocked.txt",
        "content": "should fail",
    })
    assert "權限錯誤" in result or "唯讀" in result


@pytest.mark.asyncio
async def test_list_dir_tool(sandbox, tools):
    """測試 list_dir tool。"""
    await sandbox.write_file("/mnt/user-data/workspace/a.txt", "a")
    await sandbox.write_file("/mnt/user-data/workspace/b.txt", "b")

    tool = next(t for t in tools if t.name == "list_dir")
    result = await tool.ainvoke({"path": "/mnt/user-data/workspace"})
    assert "a.txt" in result
    assert "b.txt" in result


@pytest.mark.asyncio
async def test_delete_tool(sandbox, tools):
    """測試 delete tool。"""
    await sandbox.write_file("/mnt/user-data/workspace/del.txt", "delete me")

    tool = next(t for t in tools if t.name == "delete")
    result = await tool.ainvoke({"path": "/mnt/user-data/workspace/del.txt"})
    assert "已刪除" in result


@pytest.mark.asyncio
async def test_search_files_tool(sandbox, tools):
    """測試 search_files tool。"""
    await sandbox.write_file("/mnt/user-data/workspace/code.py", "def hello(): pass")

    tool = next(t for t in tools if t.name == "search_files")
    result = await tool.ainvoke({
        "path": "/mnt/user-data/workspace",
        "name_pattern": "*.py",
    })
    assert "code.py" in result
