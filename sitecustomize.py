"""Ensure backend is in sys.path for all Python executions in this project."""

import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent / "backend"
_backend_str = str(_backend)
if _backend_str not in sys.path:
    sys.path.insert(0, _backend_str)
