from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, "backend")

from backend.graph.graph_store import GraphStore  # noqa: E402

from api.app import app  # type: ignore[import]  # noqa: E402
from logging_setup import setup_logging  # type: ignore[import]  # noqa: E402

setup_logging(
    level=logging.DEBUG if os.getenv("DEBUG", "").lower() == "true" else logging.INFO
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8600")))
