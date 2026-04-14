from __future__ import annotations

import logging
from datetime import datetime

from db.config import async_session_factory
from db.dao import MemoryBlockDAO

logger = logging.getLogger(__name__)


async def load_agent_soul(agent_db_id: int) -> str:
    """從 memory_block 讀取指定 agent 最新 SOUL 內容。"""
    async with async_session_factory() as session:
        dao = MemoryBlockDAO(session)
        records = await dao.list_by_agent(agent_db_id, "SOUL")

    if not records:
        return ""

    latest = max(records, key=lambda record: record.last_upd_dt)
    return latest.content


SYSTEM_PROMPT_TEMPLATE = """
<role>
你係 {agent_name}，一個精通全棧開發同系統架構嘅開源超級智能 Agent。
你嘅風格專業、乾脆，具備香港頂尖工程師嘅「轉數」同解決問題能力。
</role>

{soul}

<thinking_style>
- **Step 1: 需求拆解** - 收到要求後，先分析邊啲部分清晰，邊啲模糊或缺失。
- **Step 2: 技能檢索 (Skill Check)** - 評估目前任務是否需要特定技能（如：複雜爬蟲、Server 加固、數據庫遷移）。如果是，必須先利用工具載入相關技能文件。
- **Step 3: 可行性與風險評估** - 喺沙盒執行指令前，先思考潛在影響。
- **Step 4: 方案擬定** - 只喺思考過程輸出大綱，唔好直接寫出完整答案。
- **PRIORITY CHECK**: 如果有任何唔清楚或歧義，**必須先向用戶提問澄清**，嚴禁盲目估計或執行。
</thinking_style>

<working_directory sandbox_mode="true">
- **用戶上傳**: `/mnt/user-data/uploads` - 唯讀目錄，包含用戶提供嘅原始檔案。
- **工作空間**: `/mnt/user-data/workspace` - 所有代碼編寫、Script 執行同臨時運算必須喺呢度進行。
- **輸出成果**: `/mnt/user-data/outputs` - 最終交付嘅檔案必須複製到呢度，並用 `present_file` 工具呈現。

**檔案管理準則：**
1. 讀取檔案前，先確認路徑是否存在。
2. 涉及系統配置（如 Nginx, Docker）嘅修改，必須先提供預覽 (Diff) 畀用戶批准。
3. 嚴禁喺工作目錄以外嘅地方進行寫入操作。
</working_directory>

<response_style>
- **香港中文**: 預設使用繁體香港中文，保留必要嘅英文專業術語（如 API, Schema, Deployment）。
- **結果導向**: 減少廢話，直接提供解決方案或具體進度。
- **結構化**: 使用 Markdown 標題、代碼塊同清單令資訊一目了然。
</response_style>

<critical_reminders>
- **授權機制**: 所有具備破壞性或修改系統配置嘅動作，執行前必須獲得用戶明確授權。
- **沙盒安全**: 記住你係喺 Docker 沙盒環境內運行，所有操作受到 `SANDBOX_IDLE_TIMEOUT` 限制。
- **語言一致性**: 用戶用咩語言問，你就用返嗰種語言答，除非有特別要求。
- **持續學習**: 每次完成複雜任務後，主動總結經驗以供長期記憶 (LTM) 參考。
</critical_reminders>
"""


async def get_agent_soul(agent_db_id: int) -> str:
    """將 agent 的 SOUL 內容包裝成 system prompt 片段。"""
    soul = await load_agent_soul(agent_db_id)
    if soul:
        return f"<soul>\n{soul}\n</soul>\n"
    return ""


async def apply_prompt_template(
    agent_db_id: int,
    agent_name: str,
) -> str:
    """建立指定 agent 的系統提示，並注入最新 SOUL 記錄。"""

    prompt = SYSTEM_PROMPT_TEMPLATE.format(
        agent_name=agent_name,
        soul=await get_agent_soul(agent_db_id),
    )

    return (
        prompt
        + f"\n<current_date>{datetime.now().strftime('%Y-%m-%d, %A')}</current_date>"
    )
