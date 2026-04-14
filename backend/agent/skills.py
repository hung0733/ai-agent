import os
import logging
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from backend.utils.tools import Tools

logger = logging.getLogger(__name__)

# 假設工作空間基於 .env 嘅 AGENT_HOME_DIR 或預設路徑
WORKSPACE_DIR = Tools.require_env("AGENT_HOME_DIR")


@tool
def read_file(file_path: str, runtime: ToolRuntime) -> str:
    """讀取工作空間內的文件內容。"""
    try:
        user_db_id: int = runtime.config["configurable"]["user_db_id"] or 0  # type: ignore

        # 簡單安全檢查，防止 Directory Traversal
        full_path = os.path.abspath(
            os.path.join(WORKSPACE_DIR, str(user_db_id), file_path)
        )
        if not full_path.startswith(os.path.join(WORKSPACE_DIR, str(user_db_id))):
            return "Error: 拒絕存取工作空間以外的檔案。"

        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"


@tool
def write_file(file_path: str, content: str, runtime: ToolRuntime) -> str:
    """將內容寫入工作空間內的文件。如果文件不存在會自動創建。"""
    try:
        user_db_id: int = runtime.config["configurable"]["user_db_id"] or 0  # type: ignore
        
        full_path = os.path.abspath(
            os.path.join(WORKSPACE_DIR, str(user_db_id), file_path)
        )
        if not full_path.startswith(os.path.join(WORKSPACE_DIR, str(agent_db_id))):
            return "Error: 拒絕寫入工作空間以外的檔案。"

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {file_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


@tool
def execute_bash(command: str, runtime: ToolRuntime) -> str:
    """
    在 Docker 沙盒中執行 Bash 指令 (如 npm install, python script.py, curl 等)。
    """
    # TODO: 這裡需要串接你 .env 裡面定義嘅 SANDBOX_AGENT_BASE_URL
    # 目前先返回提示，下一步我哋再實作真實嘅 HTTP Client call Sandbox
    logger.info(f"準備於 Sandbox 執行指令: {command}")
    return f"Mock Execution: `{command}` 已發送至 Sandbox (待實作真實 API 串接)。"


# 匯出所有技能
AGENT_SKILLS = [read_file, write_file, execute_bash]
