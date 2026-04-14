from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from graph.graph_node import GraphNode


def test_prepare_chat_node_config_includes_session_db_id() -> None:
    config = GraphNode.prepare_chat_node_config(
        thread_id="thread-1",
        models=[],
        sys_prompt="system prompt",
        involves_secrets=False,
        think_mode=False,
        agent_db_id=11,
        session_db_id=22,
        user_db_id=33,
    )

    assert config["configurable"]["session_db_id"] == 22
    assert config["configurable"]["user_db_id"] == 33
