"""Test configuration - MUST be loaded before any test modules."""

from __future__ import annotations

import sys
from pathlib import Path

# Add backend to sys.path BEFORE any test modules are loaded
# This must happen at import time, not in a hook
_backend_path = str(Path(__file__).resolve().parent.parent / "backend")
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

# Force reload of scheduler module if it was partially loaded
if "scheduler" in sys.modules:
    del sys.modules["scheduler"]
if "scheduler.manager" in sys.modules:
    del sys.modules["scheduler.manager"]
if "scheduler.scheduler" in sys.modules:
    del sys.modules["scheduler.scheduler"]

# Ensure memory module can be imported
if "memory" not in sys.modules:
    try:
        import memory
    except ImportError:
        pass


