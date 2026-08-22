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
from worker.app.reaper import LeaseReaper
from worker.app.cron import CronDispatcher

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)],
)
logger = logging.getLogger("scheduler.daemon")


async def main():
    reaper = LeaseReaper(scan_interval=settings.REAPER_SCAN_INTERVAL_SECONDS)
    cron = CronDispatcher(check_interval_seconds=5)

    loop = asyncio.get_running_loop()

    async def shutdown():
        logger.info("🛑 Shutting down scheduler daemons...")
        await reaper.stop()
        await cron.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))

    await reaper.start()
    await cron.start()
    logger.info("🚀 Scheduler Daemons (Lease Reaper + Cron Dispatcher) running successfully.")

    try:
        while reaper.is_running and cron.is_running:
            await asyncio.sleep(1)
    except (asyncio.CancelledError, KeyboardInterrupt):
        await shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("👋 Scheduler process exited.")
