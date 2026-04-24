"""FastAPI application setup."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from db.config import close_db, init_db
from msg_queue.handler import register_all_handlers
from msg_queue.manager import get_queue_manager
from scheduler import TaskScheduler
from task_processor import TaskProcessor, register_method_handlers

from api.routes.openai_chat import router as openai_chat_router
from graph.graph_store import GraphStore


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize shared services for the API process."""
    qm = get_queue_manager()
    register_all_handlers(qm)
    await init_db()
    qm.start()

    scheduler = TaskScheduler()
    await scheduler.start()

    processor = TaskProcessor()
    register_method_handlers()
    await processor.start()

    _, lg_pool = await GraphStore.init_langgraph_checkpointer()

    try:
        yield
    finally:
        await processor.stop()
        await scheduler.stop()
        qm.stop()
        await close_db()
        await lg_pool.close()


app = FastAPI(lifespan=lifespan)
app.include_router(openai_chat_router)
