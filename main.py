import asyncio
import logging
import os
import signal
import sys
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, "backend")

from i18n import _  # type: ignore[import]  # noqa: E402
from logging_setup import setup_logging  # type: ignore[import]  # noqa: E402

setup_logging(
    level=logging.DEBUG if os.getenv("DEBUG", "").lower() == "true" else logging.INFO
)

logger = logging.getLogger(__name__)


async def main() -> None:
    from msg_queue.handler import register_all_handlers  # type: ignore[import]
    from msg_queue.manager import get_queue_manager  # type: ignore[import]

    # Init SQLAlchemy async engine
    from db.config import init_db, close_db as close_sqlalchemy_db  # type: ignore[import]
    await init_db()
    logger.info(_("SQLAlchemy async engine 已初始化"))

    # Init message queue
    qm = get_queue_manager()
    register_all_handlers(qm)
    qm.start()

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)

    logger.info(_("Agent 伺服器已啟動 — 等待訊息"))
    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        t = asyncio.current_task()
        if t is not None:
            t.uncancel()

    logger.info(_("收到關閉訊號 — 正在清理隊列"))

    qm.stop()
    await close_sqlalchemy_db()
    logger.info(_("關閉完成"))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
