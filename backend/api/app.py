"""FastAPI application setup."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from db.config import close_db, init_db
from msg_queue.handler import register_all_handlers
from msg_queue.manager import get_queue_manager
from scheduler import TaskScheduler

from api.routes.openai_chat import router as openai_chat_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize shared services for the API process."""
    qm = get_queue_manager()
    register_all_handlers(qm)
    await init_db()
    qm.start()

    scheduler = TaskScheduler()
    await scheduler.start()

    try:
        yield
    finally:
        await scheduler.stop()
        qm.stop()
        await close_db()


app = FastAPI(lifespan=lifespan)
app.include_router(openai_chat_router)
