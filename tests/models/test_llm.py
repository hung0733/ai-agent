"""Tests for LLMSet model."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.client.openai import OpenAIClient


def _make_fake_openai_client(base_url: str = "", api_key: str = "", model: str = "") -> OpenAIClient:
    """創建假的 OpenAIClient（用 mock 繞過實際 API 連線）。"""
    with patch("backend.client.openai.AsyncOpenAI"):
        return OpenAIClient(
            base_url=base_url or "https://fake.example.com/v1",
            api_key=api_key or "fake-key",
            model=model or "fake-model",
        )


class FakeSessionContext:
    """模擬 async_session_factory 的上下文管理器。"""

    def __init__(self, session: object = None) -> None:
        self._session = session or object()

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        pass


def _make_agent_entity(
    agent_db_id: int = 1,
    llm_group_id: int = 42,
) -> SimpleNamespace:
    """創建模擬 AgentEntity。"""
    return SimpleNamespace(
        id=agent_db_id,
        llm_group_id=llm_group_id,
    )


def _make_llm_level_entity(
    level: int = 1,
    is_confidential: bool = False,
    endpoint_id: int = 1,
    endpoint_url: str = "https://api.example.com/v1",
    api_key: str = "test-key",
    model_name: str = "gpt-4",
    max_token: int = 4096,
    seq_no: int = 1,
) -> SimpleNamespace:
    """創建模擬 LlmLevelEntity（含 relationship）。"""
    endpoint = SimpleNamespace(
        id=endpoint_id,
        endpoint=endpoint_url,
        enc_key=api_key,
        model_name=model_name,
        max_token=max_token,
        name=f"endpoint-{endpoint_id}",
        user_id=1,
    )
    return SimpleNamespace(
        id=endpoint_id,
        llm_group_id=42,
        llm_endpoint_id=endpoint_id,
        level=level,
        is_confidential=is_confidential,
        seq_no=seq_no,
        llm_endpoint=endpoint,
    )


class FakeAgentDAO:
    """模擬 AgentDAO。"""

    entity_cls = None  # type: ignore

    def __init__(self, session: object) -> None:
        self._session = session
        self._agent = None

    def set_agent(self, agent: SimpleNamespace) -> None:
        self._agent = agent

    async def get_by_id(self, record_id: int) -> SimpleNamespace | None:
        return self._agent if self._agent and self._agent.id == record_id else None


class FakeLlmLevelDAO:
    """模擬 LlmLevelDAO。"""

    entity_cls = None  # type: ignore

    def __init__(self, session: object) -> None:
        self._session = session
        self._levels: list[SimpleNamespace] = []

    def set_levels(self, levels: list[SimpleNamespace]) -> None:
        self._levels = levels

    async def list_by_group(self, llm_group_id: int) -> list[SimpleNamespace]:
        return [
            lvl for lvl in self._levels
            if lvl.llm_group_id == llm_group_id
        ]


@pytest.mark.asyncio
async def test_from_model_returns_llm_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試基本返回 LLMSet 實例。"""
    from models.llm import LLMSet

    agent = _make_agent_entity(agent_db_id=1, llm_group_id=42)
    levels = [
        _make_llm_level_entity(level=1, is_confidential=False, seq_no=1),
    ]

    fake_session = object()
    agent_dao = FakeAgentDAO(fake_session)
    agent_dao.set_agent(agent)
    level_dao = FakeLlmLevelDAO(fake_session)
    level_dao.set_levels(levels)

    def fake_agent_dao_factory(session: object) -> FakeAgentDAO:
        return agent_dao

    def fake_level_dao_factory(session: object) -> FakeLlmLevelDAO:
        return level_dao

    monkeypatch.setattr("models.llm.async_session_factory", lambda: FakeSessionContext(fake_session))
    monkeypatch.setattr("models.llm.AgentDAO", fake_agent_dao_factory)
    monkeypatch.setattr("models.llm.LlmLevelDAO", fake_level_dao_factory)
    monkeypatch.setattr("models.llm.Tools", MagicMock())
    monkeypatch.setattr("models.llm.OpenAIClient", _make_fake_openai_client)

    result = await LLMSet.from_model(agent_db_id=1)

    assert isinstance(result, LLMSet)


@pytest.mark.asyncio
async def test_from_model_groups_levels(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試 level 和 sec_level 正確分組。"""
    from models.llm import LLMSet
    from backend.db.dto.llm_endpoint import LlmEndpointResponse

    agent = _make_agent_entity(agent_db_id=1, llm_group_id=42)
    levels = [
        _make_llm_level_entity(level=1, is_confidential=False, seq_no=1, endpoint_id=1),
        _make_llm_level_entity(level=2, is_confidential=False, seq_no=2, endpoint_id=2),
        _make_llm_level_entity(level=1, is_confidential=True, seq_no=3, endpoint_id=3),
        _make_llm_level_entity(level=3, is_confidential=True, seq_no=4, endpoint_id=4),
    ]

    fake_session = object()
    agent_dao = FakeAgentDAO(fake_session)
    agent_dao.set_agent(agent)
    level_dao = FakeLlmLevelDAO(fake_session)
    level_dao.set_levels(levels)

    def fake_agent_dao_factory(session: object) -> FakeAgentDAO:
        return agent_dao

    def fake_level_dao_factory(session: object) -> FakeLlmLevelDAO:
        return level_dao

    monkeypatch.setattr("models.llm.async_session_factory", lambda: FakeSessionContext(fake_session))
    monkeypatch.setattr("models.llm.AgentDAO", fake_agent_dao_factory)
    monkeypatch.setattr("models.llm.LlmLevelDAO", fake_level_dao_factory)

    monkeypatch.setattr("models.llm.OpenAIClient", _make_fake_openai_client)

    mock_tools = MagicMock()
    mock_tools.require_env.side_effect = lambda key: f"mock-{key}"
    monkeypatch.setattr("models.llm.Tools", mock_tools)

    result = await LLMSet.from_model(agent_db_id=1)

    assert len(result.level[1]) == 1
    assert isinstance(result.level[1][0], LlmEndpointResponse)
    assert result.level[1][0].endpoint == "https://api.example.com/v1"

    assert len(result.level[2]) == 1
    assert len(result.level[3]) == 0

    assert len(result.sec_level[1]) == 1
    assert len(result.sec_level[3]) == 1


@pytest.mark.asyncio
async def test_from_model_raises_when_agent_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試當 agent 不存在時拋出 ValueError。"""
    from models.llm import LLMSet

    fake_session = object()
    agent_dao = FakeAgentDAO(fake_session)
    agent_dao.set_agent(None)
    level_dao = FakeLlmLevelDAO(fake_session)
    level_dao.set_levels([])

    def fake_agent_dao_factory(session: object) -> FakeAgentDAO:
        return agent_dao

    def fake_level_dao_factory(session: object) -> FakeLlmLevelDAO:
        return level_dao

    monkeypatch.setattr("models.llm.async_session_factory", lambda: FakeSessionContext(fake_session))
    monkeypatch.setattr("models.llm.AgentDAO", fake_agent_dao_factory)
    monkeypatch.setattr("models.llm.LlmLevelDAO", fake_level_dao_factory)
    monkeypatch.setattr("models.llm.Tools", MagicMock())
    monkeypatch.setattr("models.llm.OpenAIClient", _make_fake_openai_client)

    with pytest.raises(ValueError, match="Agent.*不存在"):
        await LLMSet.from_model(agent_db_id=999)


@pytest.mark.asyncio
async def test_from_model_handles_empty_levels(monkeypatch: pytest.MonkeyPatch) -> None:
    """測試當 agent 沒有 LLM 配置時返回空列表。"""
    from models.llm import LLMSet

    agent = _make_agent_entity(agent_db_id=1, llm_group_id=42)
    levels: list[SimpleNamespace] = []

    fake_session = object()
    agent_dao = FakeAgentDAO(fake_session)
    agent_dao.set_agent(agent)
    level_dao = FakeLlmLevelDAO(fake_session)
    level_dao.set_levels(levels)

    def fake_agent_dao_factory(session: object) -> FakeAgentDAO:
        return agent_dao

    def fake_level_dao_factory(session: object) -> FakeLlmLevelDAO:
        return level_dao

    monkeypatch.setattr("models.llm.async_session_factory", lambda: FakeSessionContext(fake_session))
    monkeypatch.setattr("models.llm.AgentDAO", fake_agent_dao_factory)
    monkeypatch.setattr("models.llm.LlmLevelDAO", fake_level_dao_factory)
    monkeypatch.setattr("models.llm.Tools", MagicMock())
    monkeypatch.setattr("models.llm.OpenAIClient", _make_fake_openai_client)

    result = await LLMSet.from_model(agent_db_id=1)

    assert isinstance(result, LLMSet)
    assert result.level == {1: [], 2: [], 3: []}
    assert result.sec_level == {1: [], 2: [], 3: []}
