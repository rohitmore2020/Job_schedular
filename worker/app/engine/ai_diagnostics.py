import os
import json
import logging
from typing import Optional, Dict, Any
import httpx

from backend.app.core.config import settings

logger = logging.getLogger("scheduler.ai_diagnostics")


class AIDiagnosticEngine:
    """
    Intelligent Root-Cause Analysis (RCA) Engine for Dead Letter Queue failures.
    Calls LLM APIs (Google Gemini, OpenAI, or compatible) when API keys are configured,
    and falls back to an internal heuristic rule engine when offline or unconfigured.
    """

    @staticmethod
    def _build_prompt(
        task_name: str,
        error_message: Optional[str],
        stack_trace: Optional[str],
        payload: Optional[Dict[str, Any]],
    ) -> str:
        return (
            f"You are an automated Distributed Systems Diagnostic AI for a mission-critical job scheduler.\n"
            f"Analyze the following failed task execution and generate a structured root-cause diagnostic.\n\n"
            f"Task Name: {task_name}\n"
            f"Error Message: {error_message or 'None'}\n"
            f"Stack Trace:\n{stack_trace or 'No stack trace provided'}\n"
            f"Input Payload:\n{json.dumps(payload or {}, default=str)}\n\n"
            f"Respond concisely in the following format:\n"
            f"🤖 [AI Root Cause]: <Concise explanation of what caused the failure>\n"
            f"💡 [Recommendation]: <Actionable remediation or code fix>\n"
            f"🔄 [Replay Safe]: <Yes/No with brief justification>"
        )

    @classmethod
    def _call_gemini_api(
        cls,
        api_key: str,
        task_name: str,
        error_message: Optional[str],
        stack_trace: Optional[str],
        payload: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Call Google Gemini API for intelligent failure diagnosis."""
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            prompt = cls._build_prompt(task_name, error_message, stack_trace, payload)
            body = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 300,
                },
            }
            with httpx.Client(timeout=8.0) as client:
                response = client.post(url, json=body)
                if response.status_code == 200:
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts and "text" in parts[0]:
                            logger.info(f"✨ [AI Diagnostic] Generated failure analysis via Gemini LLM for task '{task_name}'")
                            return parts[0]["text"].strip()
                logger.warning(f"⚠️ Gemini API returned HTTP {response.status_code}: {response.text[:200]}")
        except Exception as e:
            logger.warning(f"⚠️ Failed calling Gemini API for failure diagnosis: {e}")
        return None

    @classmethod
    def _call_openai_api(
        cls,
        api_key: str,
        task_name: str,
        error_message: Optional[str],
        stack_trace: Optional[str],
        payload: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Call OpenAI API for intelligent failure diagnosis."""
        try:
            url = "https://api.openai.com/v1/chat/completions"
            prompt = cls._build_prompt(task_name, error_message, stack_trace, payload)
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a distributed systems diagnostic expert.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 300,
                "temperature": 0.2,
            }
            with httpx.Client(timeout=8.0) as client:
                response = client.post(url, headers=headers, json=body)
                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                        if content:
                            logger.info(f"✨ [AI Diagnostic] Generated failure analysis via OpenAI LLM for task '{task_name}'")
                            return content.strip()
                logger.warning(f"⚠️ OpenAI API returned HTTP {response.status_code}: {response.text[:200]}")
        except Exception as e:
            logger.warning(f"⚠️ Failed calling OpenAI API for failure diagnosis: {e}")
        return None

    @classmethod
    def _fallback_rule_engine(
        cls,
        task_name: str,
        error_message: Optional[str],
        stack_trace: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Deterministic heuristic rule engine fallback when offline or no API key."""
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

    @classmethod
    def analyze_failure(
        cls,
        task_name: str,
        error_message: Optional[str],
        stack_trace: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Main entry point for AI Failure Diagnostics.
        Attempts LLM API call first if GEMINI_API_KEY or OPENAI_API_KEY is configured;
        falls back to offline heuristic rule engine seamlessly.
        """
        gemini_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        if gemini_key:
            llm_result = cls._call_gemini_api(gemini_key, task_name, error_message, stack_trace, payload)
            if llm_result:
                return llm_result

        openai_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
        if openai_key:
            llm_result = cls._call_openai_api(openai_key, task_name, error_message, stack_trace, payload)
            if llm_result:
                return llm_result

        # Fallback to local heuristic rule engine
        return cls._fallback_rule_engine(task_name, error_message, stack_trace, payload)
