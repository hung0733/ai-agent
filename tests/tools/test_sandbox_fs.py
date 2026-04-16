from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from backend.tools.sandbox_fs import (
    SandboxFileNotFoundError,
    SandboxFileSystem,
    SandboxPermissionError,
    SandboxSecurityError,
)


@pytest.fixture
def sandbox():
    """創建一個使用臨時目錄嘅 sandbox 實例。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        agent_id = "test-agent-001"
        base_dir = Path(tmpdir) / "agents"
        fs = SandboxFileSystem(agent_id=agent_id, base_dir=str(base_dir))
        yield fs


@pytest.mark.asyncio
async def test_resolve_path_valid(sandbox):
    """測試正常路徑解析。"""
    resolved = sandbox._resolve_path("/mnt/user-data/workspace/test.py")
    assert str(resolved).endswith("test-agent-001/workspace/test.py")


@pytest.mark.asyncio
async def test_resolve_path_uploads(sandbox):
    """測試 uploads 路徑解析。"""
    resolved = sandbox._resolve_path("/mnt/user-data/uploads/doc.txt")
    assert str(resolved).endswith("test-agent-001/uploads/doc.txt")


@pytest.mark.asyncio
async def test_resolve_path_outputs(sandbox):
    """測試 outputs 路徑解析。"""
    resolved = sandbox._resolve_path("/mnt/user-data/outputs/result.txt")
    assert str(resolved).endswith("test-agent-001/outputs/result.txt")


@pytest.mark.asyncio
async def test_resolve_path_invalid_prefix(sandbox):
    """測試非 /mnt/user-data/ 開頭嘅路徑。"""
    with pytest.raises(SandboxSecurityError):
        sandbox._resolve_path("/etc/passwd")


@pytest.mark.asyncio
async def test_resolve_path_traversal(sandbox):
    """測試 path traversal 攻擊。"""
    with pytest.raises(SandboxSecurityError):
        sandbox._resolve_path("/mnt/user-data/../../etc/passwd")


@pytest.mark.asyncio
async def test_is_safe_true(sandbox):
    """測試安全檢查通過。"""
    safe_path = sandbox.real_base / "workspace" / "test.py"
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.touch()
    assert sandbox._is_safe(safe_path.resolve()) is True


@pytest.mark.asyncio
async def test_is_safe_false(sandbox):
    """測試安全檢查失敗。"""
    outside_path = Path("/tmp/outside_sandbox.txt")
    assert sandbox._is_safe(outside_path.resolve()) is False


@pytest.mark.asyncio
async def test_check_writable_workspace(sandbox):
    """測試 workspace 可寫入。"""
    workspace_path = sandbox.real_base / "workspace" / "test.py"
    sandbox._check_writable(workspace_path)


@pytest.mark.asyncio
async def test_check_writable_uploads(sandbox):
    """測試 uploads 唔可寫入。"""
    uploads_path = sandbox.real_base / "uploads" / "test.py"
    with pytest.raises(SandboxPermissionError):
        sandbox._check_writable(uploads_path)


@pytest.mark.asyncio
async def test_read_file_not_found(sandbox):
    """測試讀取唔存在嘅檔案。"""
    with pytest.raises(SandboxFileNotFoundError):
        await sandbox.read_file("/mnt/user-data/workspace/nonexistent.txt")


@pytest.mark.asyncio
async def test_read_write_file(sandbox):
    """測試讀寫檔案。"""
    test_path = "/mnt/user-data/workspace/test.txt"
    test_content = "Hello, sandbox!"

    result = await sandbox.write_file(test_path, test_content)
    assert "已寫入" in result

    content = await sandbox.read_file(test_path)
    assert content == test_content


@pytest.mark.asyncio
async def test_write_to_uploads(sandbox):
    """測試寫入 uploads 應該失敗。"""
    with pytest.raises(SandboxPermissionError):
        await sandbox.write_file("/mnt/user-data/uploads/test.txt", "content")


@pytest.mark.asyncio
async def test_list_dir(sandbox):
    """測試列出目錄。"""
    await sandbox.write_file("/mnt/user-data/workspace/a.txt", "a")
    await sandbox.write_file("/mnt/user-data/workspace/b.txt", "bb")

    entries = await sandbox.list_dir("/mnt/user-data/workspace")
    assert len(entries) == 2
    names = [e["name"] for e in entries]
    assert "a.txt" in names
    assert "b.txt" in names


@pytest.mark.asyncio
async def test_list_dir_not_found(sandbox):
    """測試列出不存在嘅目錄。"""
    with pytest.raises(SandboxFileNotFoundError):
        await sandbox.list_dir("/mnt/user-data/workspace/nonexistent")


@pytest.mark.asyncio
async def test_delete_file(sandbox):
    """測試刪除檔案。"""
    test_path = "/mnt/user-data/workspace/to_delete.txt"
    await sandbox.write_file(test_path, "delete me")

    result = await sandbox.delete(test_path)
    assert "已刪除" in result

    with pytest.raises(SandboxFileNotFoundError):
        await sandbox.read_file(test_path)


@pytest.mark.asyncio
async def test_copy_file(sandbox):
    """測試複製檔案。"""
    src = "/mnt/user-data/workspace/src.txt"
    dst = "/mnt/user-data/outputs/dst.txt"

    await sandbox.write_file(src, "copy content")
    result = await sandbox.copy(src, dst)
    assert "已複製" in result

    content = await sandbox.read_file(dst)
    assert content == "copy content"


@pytest.mark.asyncio
async def test_move_file(sandbox):
    """測試移動檔案。"""
    src = "/mnt/user-data/workspace/move_src.txt"
    dst = "/mnt/user-data/outputs/move_dst.txt"

    await sandbox.write_file(src, "move content")
    result = await sandbox.move(src, dst)
    assert "已移動" in result

    content = await sandbox.read_file(dst)
    assert content == "move content"

    with pytest.raises(SandboxFileNotFoundError):
        await sandbox.read_file(src)


@pytest.mark.asyncio
async def test_search_files_by_name(sandbox):
    """測試按名稱搜尋檔案。"""
    await sandbox.write_file("/mnt/user-data/workspace/test.py", "python code")
    await sandbox.write_file("/mnt/user-data/workspace/readme.md", "documentation")

    results = await sandbox.search_files("/mnt/user-data/workspace", name_pattern="*.py")
    assert len(results) == 1
    assert results[0]["path"].endswith("test.py")
    assert results[0]["match_type"] == "name"


@pytest.mark.asyncio
async def test_search_files_by_content(sandbox):
    """測試按內容搜尋檔案。"""
    await sandbox.write_file("/mnt/user-data/workspace/secret.txt", "password=12345")
    await sandbox.write_file("/mnt/user-data/workspace/normal.txt", "hello world")

    results = await sandbox.search_files(
        "/mnt/user-data/workspace",
        content_query="password",
    )
    assert len(results) == 1
    assert results[0]["match_type"] == "content"
    assert "password" in results[0]["snippet"]


@pytest.mark.asyncio
async def test_run_script_workspace_only(sandbox):
    """測試腳本只可以喺 workspace 執行。"""
    with pytest.raises(SandboxPermissionError):
        await sandbox.run_script("/mnt/user-data/outputs/script.sh")


@pytest.mark.asyncio
async def test_run_script_not_found(sandbox):
    """測試執行唔存在嘅腳本。"""
    with pytest.raises(SandboxFileNotFoundError):
        await sandbox.run_script("/mnt/user-data/workspace/nonexistent.sh")


@pytest.mark.asyncio
async def test_run_script_success(sandbox):
    """測試成功執行腳本。"""
    script_path = sandbox.real_base / "workspace" / "echo.sh"
    script_path.write_text("#!/bin/bash\necho 'hello from script'")
    script_path.chmod(0o755)

    result = await sandbox.run_script("/mnt/user-data/workspace/echo.sh")
    assert "hello from script" in result


@pytest.mark.asyncio
async def test_auto_create_subdirs(sandbox):
    """測試自動創建 uploads, workspace, outputs 目錄。"""
    assert (sandbox.real_base / "uploads").is_dir()
    assert (sandbox.real_base / "workspace").is_dir()
    assert (sandbox.real_base / "outputs").is_dir()
