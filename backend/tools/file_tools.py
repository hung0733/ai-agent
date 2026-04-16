"""LangChain tool definitions for sandboxed file system operations.

Wraps SandboxFileSystem methods with error handling and exposes them
as LangChain StructuredTool instances via closure-based sandbox binding.
"""

from __future__ import annotations

import logging
from typing import Optional

from langchain_core.tools import StructuredTool

from i18n import _
from .sandbox_fs import (
    SandboxFileSystem,
    SandboxFileNotFoundError,
    SandboxPermissionError,
    SandboxSecurityError,
)

logger = logging.getLogger(__name__)


def _handle_tool_error(func_name: str, e: Exception) -> str:
    """統一處理 tool 執行時嘅錯誤。"""
    if isinstance(e, SandboxSecurityError):
        logger.error(_("安全錯誤 [{0}]: {1}").format(func_name, e))
        return _("安全錯誤: {}").format(str(e))
    elif isinstance(e, SandboxPermissionError):
        logger.error(_("權限錯誤 [{0}]: {1}").format(func_name, e))
        return _("權限錯誤: {}").format(str(e))
    elif isinstance(e, SandboxFileNotFoundError):
        logger.warning(_("檔案未搵到 [{0}]: {1}").format(func_name, e))
        return _("檔案未搵到: {}").format(str(e))
    else:
        logger.error(_("工具執行錯誤 [{0}]: {1}").format(func_name, e), exc_info=True)
        return _("執行錯誤: {}").format(str(e))


def get_file_tools(sandbox: SandboxFileSystem) -> list:
    """創建綁咗 sandbox 實例嘅 file system tools。

    Args:
        sandbox: SandboxFileSystem 實例。

    Returns:
        LangChain StructuredTool 列表。
    """

    async def read_file(path: str) -> str:
        """讀取檔案內容。"""
        try:
            return await sandbox.read_file(path)
        except Exception as e:
            return _handle_tool_error("read_file", e)

    async def write_file(path: str, content: str) -> str:
        """寫入檔案內容。"""
        try:
            return await sandbox.write_file(path, content)
        except Exception as e:
            return _handle_tool_error("write_file", e)

    async def list_dir(path: str) -> str:
        """列出目錄內容。"""
        try:
            entries = await sandbox.list_dir(path)
            if not entries:
                return _("目錄為空: {}").format(path)
            lines = [_("目錄內容: {}").format(path)]
            for entry in entries:
                size_str = f"{entry['size']:,}" if entry["type"] == "file" else "-"
                lines.append(f"  {entry['type']:9s} {size_str:>12s} {entry['name']}")
            return "\n".join(lines)
        except Exception as e:
            return _handle_tool_error("list_dir", e)

    async def delete(path: str) -> str:
        """刪除檔案或目錄。"""
        try:
            return await sandbox.delete(path)
        except Exception as e:
            return _handle_tool_error("delete", e)

    async def copy_file(src: str, dst: str) -> str:
        """複製檔案或目錄。"""
        try:
            return await sandbox.copy(src, dst)
        except Exception as e:
            return _handle_tool_error("copy_file", e)

    async def move_file(src: str, dst: str) -> str:
        """移動檔案或目錄。"""
        try:
            return await sandbox.move(src, dst)
        except Exception as e:
            return _handle_tool_error("move_file", e)

    async def search_files(
        path: str,
        name_pattern: str = "",
        content_query: str = "",
    ) -> str:
        """搜尋檔案。"""
        try:
            results = await sandbox.search_files(path, name_pattern, content_query)
            if not results:
                return _("未搵到匹配嘅檔案")
            lines = [_("搜尋結果:")]
            for r in results:
                lines.append(f"  [{r['match_type']}] {r['path']}")
                if r["snippet"]:
                    lines.append(f"    ...{r['snippet']}...")
            return "\n".join(lines)
        except Exception as e:
            return _handle_tool_error("search_files", e)

    async def run_script(path: str, args: list[str] | None = None) -> str:
        """執行腳本。"""
        try:
            return await sandbox.run_script(path, args)
        except Exception as e:
            return _handle_tool_error("run_script", e)

    return [
        StructuredTool.from_function(
            coroutine=read_file,
            name="read_file",
            description=_("讀取檔案內容。路徑必須以 /mnt/user-data/ 開頭。"),
        ),
        StructuredTool.from_function(
            coroutine=write_file,
            name="write_file",
            description=_("寫入檔案內容。/mnt/user-data/uploads 係唯讀，唔可以寫入。"),
        ),
        StructuredTool.from_function(
            coroutine=list_dir,
            name="list_dir",
            description=_("列出目錄內容。路徑必須以 /mnt/user-data/ 開頭。"),
        ),
        StructuredTool.from_function(
            coroutine=delete,
            name="delete",
            description=_("刪除檔案或目錄。/mnt/user-data/uploads 內嘅檔案唔可以刪除。"),
        ),
        StructuredTool.from_function(
            coroutine=copy_file,
            name="copy_file",
            description=_("複製檔案或目錄。"),
        ),
        StructuredTool.from_function(
            coroutine=move_file,
            name="move_file",
            description=_("移動檔案或目錄。"),
        ),
        StructuredTool.from_function(
            coroutine=search_files,
            name="search_files",
            description=_("搜尋檔案。可以按名稱或內容關鍵字搜尋。"),
        ),
        StructuredTool.from_function(
            coroutine=run_script,
            name="run_script",
            description=_("執行腳本。只可以喺 /mnt/user-data/workspace 目錄執行。"),
        ),
    ]
