import sys
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import asyncio
import logging
import signal
from rich.logging import RichHandler

from backend.app.core.config import settings
from worker.app.engine.daemon import WorkerDaemon

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger("scheduler.worker")


async def main():
    daemon = WorkerDaemon(
        concurrency=settings.WORKER_CONCURRENCY,
    )
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(daemon.stop()))

    await daemon.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Worker process exited.")
