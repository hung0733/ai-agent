from __future__ import annotations

import os
import logging
import re
import subprocess

from langchain_core.tools import tool
import yaml

from backend.i18n import _
from backend.utils.tools import Tools

logger = logging.getLogger(__name__)

SKILLS_DIR = Tools.require_env("SKILLS_DIR")


def _read_skill_description(skill_name: str) -> str:
    """從 SKILL.md 的 YAML frontmatter 中讀取 description。

    返回格式: "{skill_name}: {description}"
    如果找不到 SKILL.md 或沒有 description，返回 "{skill_name}: No description"
    """
    skill_md_path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")

    if not os.path.exists(skill_md_path):
        return _("{skill_name}: 無描述").format(skill_name=skill_name)

    try:
        with open(skill_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if not match:
            return _("{skill_name}: 無描述").format(skill_name=skill_name)

        frontmatter = yaml.safe_load(match.group(1))
        description = frontmatter.get("description") if frontmatter else None

        if description:
            return _("{skill_name}: {description}").format(
                skill_name=skill_name, description=description
            )
        return _("{skill_name}: 無描述").format(skill_name=skill_name)

    except Exception as e:
        logger.error(_("讀取技能 %s 的 SKILL.md 時發生錯誤: %s"), skill_name, str(e))
        return _("{skill_name}: 無描述").format(skill_name=skill_name)


@tool
def discover_skills() -> str:
    """
    掃描並列出所有可用的 Agent Skills。
    當你不知道該用什麼技能時，先呼叫此工具。
    """
    if not os.path.exists(SKILLS_DIR):
        return "找不到技能目錄。"

    available_skills = []
    for skill_name in os.listdir(SKILLS_DIR):
        skill_path = os.path.join(SKILLS_DIR, skill_name)
        if os.path.isdir(skill_path):
            # 讀取 YAML Metadata (Agent Skills 標準規範)
            meta_path = os.path.join(skill_path, "metadata.yaml")
            description = "No description"
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = yaml.safe_load(f)
                        description = meta.get("description", description)
                except Exception:
                    pass

            # 如果 metadata.yaml 沒有 description，fallback 到 SKILL.md
            if description == "No description":
                description = _read_skill_description(skill_name)

            available_skills.append(f"- {skill_name}: {description}")

    return "可用技能列表:\n" + "\n".join(available_skills)


@tool
def read_skill(skill_name: str) -> str:
    """
    Standard Read Step: 讀取指定技能的詳細說明與使用方法。
    在執行任何技能指令前，必須先呼叫此工具閱讀 SKILL.md。
    """
    skill_md_path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")

    if not os.path.exists(skill_md_path):
        return f"錯誤：找不到技能 {skill_name} 的 SKILL.md。"

    try:
        with open(skill_md_path, "r", encoding="utf-8") as f:
            content = f.read()
        logger.info(f"📖 Agent 正在讀取標準技能: {skill_name}")
        return f"=== {skill_name} 技能說明 (SKILL.md) ===\n{content}\n=== 閱讀完畢，請根據上述指示行動 ==="
    except Exception as e:
        return f"讀取 SKILL.md 時發生錯誤: {str(e)}"


@tool
def execute_cli(command: str) -> str:
    """
    安全地執行開放技能對應的 CLI 指令 (如 opencli)。
    注意：請確保你已經透過 read_skill 閱讀過該技能的用法。
    """
    logger.info(f"🚀 執行 CLI 指令: {command}")
    try:
        # 實戰中，呢度應該駁去你嘅 .env SANDBOX_AGENT_BASE_URL
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=120
        )
        return f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    except Exception as e:
        return f"執行失敗: {str(e)}"


# 將這三個核心 Process 工具打包
STANDARD_SKILL_TOOLS = [discover_skills, read_skill, execute_cli]
