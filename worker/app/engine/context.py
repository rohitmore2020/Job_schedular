import uuid
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable, Awaitable
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("scheduler.context")


@dataclass
class ExecutionContext:
    """
    Rich Execution Context passed into task handlers during execution.
    Provides execution_id, attempt_number, job metadata, and built-in helpers
    for idempotent external side-effects in at-least-once distributed execution.
    """
    execution_id: uuid.UUID
    job_id: uuid.UUID
    queue_id: uuid.UUID
    job_name: str
    attempt_number: int
    max_retries: int
    idempotency_key: Optional[str] = None
    lease_token: Optional[uuid.UUID] = None
    worker_id: Optional[str] = None
    db_session: Optional[AsyncSession] = None

    def get_side_effect_key(self, operation: str) -> str:
        """
        Generate a deterministic idempotency key for an external operation.
        Format: 'job:<job_id>:op:<operation>'
        """
        return f"job:{self.job_id}:op:{operation}"

    async def execute_idempotent_operation(
        self,
        operation: str,
        func: Callable[[], Awaitable[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """
        Executes an external side effect (e.g. Stripe charge, API call, email dispatch)
        idempotently by persisting and verifying operation state in `idempotency_records`.

        Workflow:
        1. Query `idempotency_records` for key 'job:<job_id>:op:<operation>'.
        2. If already completed (from a prior attempt before a lease timeout/crash),
           skip calling `func()` and immediately return the stored `response_payload`.
        3. If not completed, execute `func()`, persist result in `idempotency_records`, and return.
        """
        if not self.db_session:
            return await func()

        from backend.app.models.idempotency import IdempotencyRecord

        key = self.get_side_effect_key(operation)

        # Check existing record
        stmt = select(IdempotencyRecord).where(IdempotencyRecord.key == key)
        res = await self.db_session.execute(stmt)
        record = res.scalar_one_or_none()

        if record and record.status == "completed":
            logger.info(
                f"🛡️ [Idempotency Guard] Skipping duplicate external side-effect for key '{key}' "
                f"(Attempt: {self.attempt_number}, Execution: {self.execution_id})"
            )
            return record.response_payload or {}

        # Execute external operation
        result = await func()

        if record:
            record.status = "completed"
            record.response_payload = result
        else:
            new_record = IdempotencyRecord(
                job_id=self.job_id,
                key=key,
                scope="external_side_effect",
                status="completed",
                response_payload=result,
            )
            self.db_session.add(new_record)

        await self.db_session.flush()
        return result
