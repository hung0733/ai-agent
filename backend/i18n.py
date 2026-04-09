"""Gettext i18n setup for agent-server.

Default locale: zh_HK (香港繁體中文).
Falls back to the original string if no translation is found.

Usage in any module:
    from i18n import _
    logger.info(_("任務 %s 已加入队列"), task.id)
    raise ValueError(_("Agent 未初始化"))
    system_prompt = _("你是一個 AI 助手，請用香港中文回覆。")
"""

from __future__ import annotations

import gettext
import os
from pathlib import Path

_LOCALE_DIR = Path(__file__).resolve().parent.parent / "locale"
_DOMAIN = "ai_agent"
_DEFAULT_LANG = os.getenv("LANG_LOCALE", "zh_HK")

_translation = gettext.translation(
    domain=_DOMAIN,
    localedir=str(_LOCALE_DIR),
    languages=[_DEFAULT_LANG],
    fallback=True,  # Return original string if .mo not found
)

_ = _translation.gettext
