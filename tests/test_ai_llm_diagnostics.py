import pytest
from unittest.mock import patch, MagicMock
from worker.app.engine.ai_diagnostics import AIDiagnosticEngine


def test_ai_diagnostic_gemini_api_integration():
    """
    Verifies that when GEMINI_API_KEY is configured, AIDiagnosticEngine
    calls the Gemini API and parses the LLM-generated response.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                "🤖 [AI Root Cause]: Downstream Stripe payment gateway timed out after 30s.\n"
                                "💡 [Recommendation]: Verify webhook endpoints and extend client timeout.\n"
                                "🔄 [Replay Safe]: Yes (idempotent charge token detected)."
                            )
                        }
                    ]
                }
            }
        ]
    }

    with patch("backend.app.core.config.settings.GEMINI_API_KEY", "fake-gemini-key-12345"):
        with patch("httpx.Client.post", return_value=mock_response) as mock_post:
            result = AIDiagnosticEngine.analyze_failure(
                task_name="process_stripe_payment",
                error_message="StripeConnectTimeout: connection dropped",
                stack_trace="Traceback (most recent call last):\n  File 'charge.py', line 42",
                payload={"amount_cents": 5000, "customer_id": "cust_123"},
            )

            assert mock_post.called
            assert "Downstream Stripe payment gateway" in result
            assert "idempotent charge token" in result


def test_ai_diagnostic_openai_api_integration():
    """
    Verifies that when OPENAI_API_KEY is configured (and GEMINI not set),
    AIDiagnosticEngine calls the OpenAI API.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": (
                        "🤖 [AI Root Cause]: PostgreSQL deadlocked on order_items table.\n"
                        "💡 [Recommendation]: Sort item IDs before acquiring row locks.\n"
                        "🔄 [Replay Safe]: Yes (concurrency conflict resolved upon replay)."
                    )
                }
            }
        ]
    }

    with patch("backend.app.core.config.settings.GEMINI_API_KEY", ""):
        with patch("backend.app.core.config.settings.OPENAI_API_KEY", "fake-openai-key-67890"):
            with patch("httpx.Client.post", return_value=mock_response) as mock_post:
                result = AIDiagnosticEngine.analyze_failure(
                    task_name="update_inventory",
                    error_message="DeadlockDetected: process 1024 waited on lock",
                    stack_trace="Traceback...",
                    payload={"order_id": 999},
                )

                assert mock_post.called
                assert "PostgreSQL deadlocked on order_items" in result
                assert "Sort item IDs before acquiring row locks" in result


def test_ai_diagnostic_offline_fallback_on_api_error():
    """
    Verifies that if LLM API call fails (HTTP 500 / network error),
    AIDiagnosticEngine gracefully falls back to the deterministic rule engine.
    """
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch("backend.app.core.config.settings.GEMINI_API_KEY", "fake-key"):
        with patch("backend.app.core.config.settings.OPENAI_API_KEY", ""):
            with patch("httpx.Client.post", return_value=mock_response):
                result = AIDiagnosticEngine.analyze_failure(
                    task_name="send_invoice_email",
                    error_message="HTTP 504 Gateway Timeout: upstream host unresponsive",
                    stack_trace="ConnectError: connection timed out",
                )

                # Fallback rule engine should catch "504 gateway" / "timeout"
                assert "Downstream Network / Gateway Timeout" in result
                assert "Replay Safe]: Yes" in result


def test_ai_diagnostic_offline_fallback_when_no_keys_configured():
    """
    Verifies that when no LLM keys are configured, the rule engine provides
    instant, zero-latency local heuristic analysis.
    """
    with patch("backend.app.core.config.settings.GEMINI_API_KEY", ""):
        with patch("backend.app.core.config.settings.OPENAI_API_KEY", ""):
            oom_result = AIDiagnosticEngine.analyze_failure(
                task_name="render_video",
                error_message="MemoryError: unable to allocate 8.00 GiB for array",
            )
            assert "Memory Exhaustion (OOM)" in oom_result

            auth_result = AIDiagnosticEngine.analyze_failure(
                task_name="sync_s3_bucket",
                error_message="AccessDenied: 403 Forbidden",
            )
            assert "Authentication / Credential Authorization Rejection" in auth_result
