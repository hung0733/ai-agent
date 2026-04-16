from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from i18n import _

logger = logging.getLogger(__name__)

VIRTUAL_BASE = "/mnt/user-data"
DEFAULT_BASE_DIR = "/mnt/data/misc/ai-agent/home"


class SandboxSecurityError(Exception):
    """Raised when a path operation would escape the sandbox."""
    pass


class SandboxFileNotFoundError(Exception):
    """Raised when a requested path does not exist."""
    pass


class SandboxPermissionError(Exception):
    """Raised when an operation is not allowed on the target path."""
    pass


class SandboxFileSystem:
    """沙盒化檔案系統，將 LLM 嘅 /mnt/user-data/ 路徑映射到實際 agent home 目錄。

    Args:
        agent_id: Agent 唯一識別碼。
        base_dir: 實際 agent home 目錄嘅 base path。
    """

    def __init__(self, agent_id: str, base_dir: str = DEFAULT_BASE_DIR):
        self.agent_id = agent_id
        self.real_base = Path(base_dir) / agent_id
        self.real_base.mkdir(parents=True, exist_ok=True)

        for subdir in ("uploads", "workspace", "outputs"):
            (self.real_base / subdir).mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, virtual_path: str) -> Path:
        """將 /mnt/user-data/xxx 映射到真實路徑。

        Args:
            virtual_path: LLM 使用嘅虛擬路徑。

        Returns:
            解析後嘅實際 Path 對象。

        Raises:
            SandboxSecurityError: 如果路徑嘗試 escape sandbox。
        """
        if not virtual_path.startswith(VIRTUAL_BASE):
            logger.warning(
                _("安全違規: 路徑必須以 %s 開頭，但收到: %s"),
                VIRTUAL_BASE,
                virtual_path,
            )
            raise SandboxSecurityError(
                _("路徑必須以 %s 開頭，但收到: %s") % (VIRTUAL_BASE, virtual_path)
            )

        relative = virtual_path[len(VIRTUAL_BASE):].lstrip("/")
        resolved = (self.real_base / relative).resolve()

        logger.debug(_("路徑解析: %s -> %s"), virtual_path, resolved)

        if not self._is_safe(resolved):
            logger.warning(
                _("安全違規: 路徑 %s 超出沙盒範圍 (解析為 %s)"),
                virtual_path,
                resolved,
            )
            raise SandboxSecurityError(
                _("路徑 %s 超出沙盒範圍") % virtual_path
            )

        return resolved

    def _is_safe(self, resolved: Path) -> bool:
        """檢查解析後嘅路徑是否喺 sandbox 範圍內。

        Args:
            resolved: 已解析嘅絕對路徑。

        Returns:
            True 如果路徑安全，False 如果超出範圍。
        """
        try:
            resolved.relative_to(self.real_base.resolve())
            return True
        except ValueError:
            return False

    def _check_writable(self, resolved: Path) -> None:
        """檢查路徑是否允許寫入。uploads 目錄係唯讀。

        Args:
            resolved: 已解析嘅實際路徑。

        Raises:
            SandboxPermissionError: 如果路徑唔允許寫入。
        """
        uploads_dir = self.real_base / "uploads"
        try:
            resolved.relative_to(uploads_dir)
            raise SandboxPermissionError(
                _("/mnt/user-data/uploads 係唯讀目錄，唔允許寫入")
            )
        except ValueError:
            pass

    async def read_file(self, path: str) -> str:
        """讀取檔案內容。"""
        resolved = self._resolve_path(path)
        if not resolved.exists():
            raise SandboxFileNotFoundError(
                _("檔案不存在: %s") % path
            )
        if not resolved.is_file():
            raise SandboxPermissionError(
                _("%s 係目錄，唔係檔案") % path
            )
        return await asyncio.to_thread(resolved.read_text, encoding="utf-8")

    async def write_file(self, path: str, content: str) -> str:
        """寫入檔案內容。"""
        resolved = self._resolve_path(path)
        self._check_writable(resolved)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(resolved.write_text, content, encoding="utf-8")
        return _("檔案已寫入: %s (%d 字元)") % (path, len(content))

    async def list_dir(self, path: str) -> List[Dict[str, Any]]:
        """列出目錄內容。"""
        resolved = self._resolve_path(path)
        if not resolved.exists():
            raise SandboxFileNotFoundError(
                _("目錄不存在: %s") % path
            )
        if not resolved.is_dir():
            raise SandboxPermissionError(
                _("%s 係檔案，唔係目錄") % path
            )

        def _list_entries() -> List[Dict[str, Any]]:
            results = []
            for entry in sorted(resolved.iterdir()):
                stat = entry.stat()
                results.append({
                    "name": entry.name,
                    "type": "directory" if entry.is_dir() else "file",
                    "size": stat.st_size if entry.is_file() else 0,
                    "modified": stat.st_mtime,
                })
            return results

        return await asyncio.to_thread(_list_entries)

    async def delete(self, path: str) -> str:
        """刪除檔案或目錄。"""
        resolved = self._resolve_path(path)
        if not resolved.exists():
            raise SandboxFileNotFoundError(
                _("路徑不存在: %s") % path
            )
        self._check_writable(resolved)

        if resolved.is_dir():
            await asyncio.to_thread(shutil.rmtree, resolved)
        else:
            await asyncio.to_thread(resolved.unlink)

        return _("已刪除: %s") % path

    async def copy(self, src: str, dst: str) -> str:
        """複製檔案或目錄。"""
        src_resolved = self._resolve_path(src)
        dst_resolved = self._resolve_path(dst)

        if not src_resolved.exists():
            raise SandboxFileNotFoundError(
                _("來源不存在: %s") % src
            )
        self._check_writable(dst_resolved)

        def _copy():
            if src_resolved.is_dir():
                shutil.copytree(src_resolved, dst_resolved, dirs_exist_ok=True)
            else:
                dst_resolved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_resolved, dst_resolved)

        await asyncio.to_thread(_copy)

        return _("已複製: %s -> %s") % (src, dst)

    async def move(self, src: str, dst: str) -> str:
        """移動檔案或目錄。"""
        src_resolved = self._resolve_path(src)
        dst_resolved = self._resolve_path(dst)

        if not src_resolved.exists():
            raise SandboxFileNotFoundError(
                _("來源不存在: %s") % src
            )
        self._check_writable(src_resolved)
        self._check_writable(dst_resolved)

        dst_resolved.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.move, str(src_resolved), str(dst_resolved))

        return _("已移動: %s -> %s") % (src, dst)

    async def search_files(
        self,
        path: str,
        name_pattern: str = "",
        content_query: str = "",
    ) -> List[Dict[str, Any]]:
        """搜尋檔案。"""
        import fnmatch

        resolved = self._resolve_path(path)
        if not resolved.exists():
            raise SandboxFileNotFoundError(
                _("路徑不存在: %s") % path
            )

        def _search() -> List[Dict[str, Any]]:
            results = []
            for root, dirs, files in os.walk(resolved):
                for filename in files:
                    file_path = Path(root) / filename
                    rel = file_path.relative_to(self.real_base)
                    virtual_file_path = f"{VIRTUAL_BASE}/{rel}"

                    name_match = (
                        not name_pattern or fnmatch.fnmatch(filename, name_pattern)
                    )
                    content_match = False
                    snippet = ""

                    if content_query and name_match:
                        try:
                            content = file_path.read_text(encoding="utf-8", errors="ignore")
                            if content_query.lower() in content.lower():
                                content_match = True
                                idx = content.lower().index(content_query.lower())
                                start = max(0, idx - 50)
                                end = min(len(content), idx + len(content_query) + 50)
                                snippet = content[start:end]
                        except (UnicodeDecodeError, PermissionError):
                            continue

                    if name_match and not content_query:
                        results.append({
                            "path": virtual_file_path,
                            "match_type": "name",
                            "snippet": "",
                        })
                    elif content_match:
                        results.append({
                            "path": virtual_file_path,
                            "match_type": "content",
                            "snippet": snippet,
                        })

            return results

        return await asyncio.to_thread(_search)

    async def run_script(
        self,
        path: str,
        args: Optional[List[str]] = None,
        timeout: int = 30,
    ) -> str:
        """執行腳本。只允許喺 workspace 目錄執行。"""
        resolved = self._resolve_path(path)
        workspace_dir = self.real_base / "workspace"

        try:
            resolved.relative_to(workspace_dir)
        except ValueError:
            raise SandboxPermissionError(
                _("腳本只可以喺 /mnt/user-data/workspace 目錄執行")
            )

        if not resolved.exists():
            raise SandboxFileNotFoundError(
                _("腳本不存在: %s") % path
            )

        cmd = [str(resolved)]
        if args:
            cmd.extend(args)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace_dir),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            output = stdout.decode("utf-8", errors="replace")
            if stderr:
                output += stderr.decode("utf-8", errors="replace")
            return output or _("腳本執行完成，無輸出")
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return _("腳本執行超時 (%d 秒)") % timeout
        except PermissionError as e:
            raise SandboxPermissionError(
                _("腳本執行權限被拒: %s") % str(e)
            ) from e
        except FileNotFoundError as e:
            raise SandboxFileNotFoundError(
                _("腳本執行失敗，解釋器不存在: %s") % str(e)
            ) from e
