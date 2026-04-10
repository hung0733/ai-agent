from __future__ import annotations

import importlib
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def test_engine_echo_is_disabled_even_when_debug_true(monkeypatch) -> None:
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://user:pass@127.0.0.1:5432/test_db",
    )

    sys.modules.pop("db.config", None)
    config = importlib.import_module("db.config")

    assert config.engine.echo is False
