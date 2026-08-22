import asyncio
import io
import sys
import logging
from typing import Callable, Dict, Any, Awaitable, Optional, Union

logger = logging.getLogger("scheduler.tasks")

# Function signature for async task handlers
TaskHandler = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


class TaskRegistry:
    def __init__(self):
        self._registry: Dict[str, TaskHandler] = {}

    def register(self, name: str, handler: Optional[TaskHandler] = None):
        """
        Register a task handler by name. Can be used as a decorator or direct method call.
        """
        if handler is not None:
            self._registry[name] = handler
            logger.debug(f"Registered task handler: {name}")
            return handler

        def decorator(fn: TaskHandler) -> TaskHandler:
            self._registry[name] = fn
            logger.debug(f"Registered task handler: {name}")
            return fn

        return decorator

    def get(self, name: str) -> TaskHandler:
        """Retrieve a task handler or return a default generic handler."""
        return self._registry.get(name, self._default_generic_handler)

    @staticmethod
    async def _default_generic_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Default handler for arbitrary tasks without explicit implementation."""
        print(f"[Generic Task] Processing generic job payload: {payload}")
        duration = payload.get("duration", 0.01)
        if duration > 0:
            await asyncio.sleep(duration)
        return {
            "status": "success",
            "message": "Generic task processed successfully",
            "received_payload": payload,
        }


# Global Task Registry Instance
task_registry = TaskRegistry()


# --- Built-in Demonstration Task Handlers ---

@task_registry.register("send_email")
@task_registry.register("send_welcome_email")
async def handle_send_email(payload: Dict[str, Any]) -> Dict[str, Any]:
    recipient = payload.get("email", "user@example.com")
    subject = payload.get("subject", "Notification")
    print(f"[SES Client] Connecting to SMTP endpoint...")
    print(f"[SES Client] Delivering email to {recipient} with subject '{subject}'...")
    await asyncio.sleep(0.01)
    print(f"[SES Client] Message accepted by gateway. MessageID: <msg-{recipient[:4]}-123>")
    return {
        "status": "delivered",
        "recipient": recipient,
        "message_id": f"msg_aws_{recipient[:4]}_9988",
    }


@task_registry.register("process_video")
@task_registry.register("transcode_4k_stream")
async def handle_process_video(payload: Dict[str, Any]) -> Dict[str, Any]:
    video_url = payload.get("video_url", "https://s3.amazonaws.com/video.mp4")
    codec = payload.get("codec", "h264")
    print(f"[FFmpeg] Opening video stream from {video_url}...")
    print(f"[FFmpeg] Transcoding video using codec {codec} at 1080p60...")
    await asyncio.sleep(0.01)
    print(f"[FFmpeg] Transcoding complete. 1440 frames encoded.")
    return {
        "status": "transcoded",
        "codec": codec,
        "output_url": "https://cdn.example.com/videos/output.mp4",
        "frames_processed": 1440,
    }


@task_registry.register("mock_failing_task")
async def handle_failing_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    error_type = payload.get("error_type", "RuntimeError")
    print(f"[Worker] Starting risky task with error trigger '{error_type}'...")
    await asyncio.sleep(0.01)
    raise RuntimeError(f"Simulated task failure: {error_type} triggered during processing")


@task_registry.register("calculate_report")
@task_registry.register("generate_report_pdf")
async def handle_calculate_report(payload: Dict[str, Any]) -> Dict[str, Any]:
    report_type = payload.get("report_type", "monthly_financials")
    print(f"[Analytics] Aggregating data records for report '{report_type}'...")
    await asyncio.sleep(0.01)
    print(f"[Analytics] Aggregated 45,000 ledger rows.")
    return {
        "report_type": report_type,
        "total_rows_aggregated": 45000,
        "download_url": f"https://cdn.example.com/reports/{report_type}.pdf",
    }
