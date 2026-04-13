from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))


@pytest.mark.asyncio
async def test_load_agent_soul_returns_latest_soul_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent import prompt

    captured: dict[str, object] = {}

    class FakeSessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeMemoryBlockDAO:
        def __init__(self, session: object) -> None:
            captured["session"] = session

        async def list_by_agent(self, agent_id: int, memory_type: str | None = None):
            captured["agent_id"] = agent_id
            captured["memory_type"] = memory_type
            now = datetime.now(timezone.utc)
            return [
                SimpleNamespace(content="old soul", last_upd_dt=now - timedelta(hours=1)),
                SimpleNamespace(content="new soul", last_upd_dt=now),
            ]

    monkeypatch.setattr(prompt, "async_session_factory", FakeSessionContext)
    monkeypatch.setattr(prompt, "MemoryBlockDAO", FakeMemoryBlockDAO)

    assert await prompt.load_agent_soul(7) == "new soul"
    assert captured == {
        "session": captured["session"],
        "agent_id": 7,
        "memory_type": "SOUL",
    }


def test_apply_prompt_template_requires_agent_db_id() -> None:
    from agent.prompt import apply_prompt_template

    with pytest.raises(TypeError):
        apply_prompt_template()  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_apply_prompt_template_includes_generated_soul(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent import prompt

    async def fake_load_agent_soul(agent_db_id: int) -> str:
        return "agent soul"

    monkeypatch.setattr(prompt, "load_agent_soul", fake_load_agent_soul)

    rendered = await prompt.apply_prompt_template(agent_db_id=9, agent_name="小丸")

    assert "You are 小丸" in rendered
    assert "<soul>\nagent soul\n</soul>" in rendered
