import re
from typing import Optional, Dict, Any


class AIDiagnosticEngine:
    """
    Intelligent Root-Cause Analysis (RCA) Engine for Dead Letter Queue failures.
    Analyzes task exceptions, Python stack traces, and input arguments to generate
    human-readable root cause explanations and remediation recommendations.
    """

    @staticmethod
    def analyze_failure(
        task_name: str,
        error_message: Optional[str],
        stack_trace: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        error_str = f"{error_message or ''}\n{stack_trace or ''}".lower()

        # Category 1: Memory / OOM / Segfault
        if any(w in error_str for w in ["out of memory", "oom", "signal 9", "sigkill", "killed", "memoryerror"]):
            return (
                "🚨 [Root Cause]: Process terminated due to Memory Exhaustion (OOM).\n"
                "💡 [Recommendation]: The task required more RAM than allocated. Increase worker container memory "
                "limit or batch the dataset into smaller chunked iterations before processing.\n"
                "🔄 [Replay Safe]: Yes (after allocating additional RAM)."
            )

        # Category 2: Network / Timeout / Gateway issues
        if any(w in error_str for w in ["timeout", "timed out", "connection refused", "504 gateway", "502 bad gateway", "connecterror"]):
            return (
                "🌐 [Root Cause]: Downstream Network / Gateway Timeout.\n"
                "💡 [Recommendation]: The external microservice or database gateway did not respond within the SLA threshold. "
                "Verify service health or configure exponential backoff with higher max interval.\n"
                "🔄 [Replay Safe]: Yes (transient network failure)."
            )

        # Category 3: Schema / JSON / Type validation errors
        if any(w in error_str for w in ["keyerror", "validationerror", "typeerror", "valueerror", "jsondecodeerror", "missing required"]):
            return (
                "📝 [Root Cause]: Data Schema / Serialization Validation Failure.\n"
                "💡 [Recommendation]: The task payload contains invalid, null, or unexpected parameter schemas. "
                "Update client submission arguments to match the expected schema before redriving.\n"
                "🔄 [Replay Safe]: No (requires payload schema fix)."
            )

        # Category 4: Authentication / Permissions
        if any(w in error_str for w in ["unauthorized", "forbidden", "401", "403", "permission denied", "invalid token", "access denied"]):
            return (
                "🔒 [Root Cause]: Authentication / Credential Authorization Rejection.\n"
                "💡 [Recommendation]: The API key or access token expired or lacks sufficient permissions. "
                "Refresh authentication secrets in the environment variables.\n"
                "🔄 [Replay Safe]: Yes (after rotating secrets)."
            )

        # Category 5: Database deadlocks / lock timeouts
        if any(w in error_str for w in ["deadlock", "lock timeout", "canceling statement due to statement timeout"]):
            return (
                "🗄️ [Root Cause]: Database Concurrency Contention / Deadlock.\n"
                "💡 [Recommendation]: Parallel database transactions conflicted on row locks. "
                "Ensure transactions acquire locks in identical sequential order or reduce batch concurrency.\n"
                "🔄 [Replay Safe]: Yes (safe to replay immediately)."
            )

        # Default general failure
        return (
            f"⚠️ [Root Cause]: Unhandled Runtime Exception in Task '{task_name}'.\n"
            f"💡 [Recommendation]: Inspect the attached stack trace and verify handler logic in task registry.\n"
            f"🔄 [Replay Safe]: Check logs before replaying."
        )
