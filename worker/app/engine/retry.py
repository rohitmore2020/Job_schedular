import random
from typing import Optional
from datetime import timedelta
from backend.app.models.queue import RetryPolicy
from backend.app.models.enums import RetryStrategy


class RetryBackoffCalculator:
    """
    Calculates delay intervals for failed jobs based on queue retry policies.
    Supports Fixed delay, Linear backoff, and Exponential backoff with Full Jitter.
    """

    @staticmethod
    def calculate_delay(
        attempt_number: int,
        policy: Optional[RetryPolicy] = None,
    ) -> float:
        """
        Calculate delay in seconds before next execution attempt.
        `attempt_number` is 1-indexed (1st retry, 2nd retry, etc.)
        """
        if not policy:
            # Fallback default: Exponential backoff (5s, 10s, 20s...)
            strategy = RetryStrategy.EXPONENTIAL
            initial = 5
            max_int = 3600
            mult = 2.0
            use_jitter = True
        else:
            strategy = policy.strategy
            initial = policy.initial_interval_sec
            max_int = policy.max_interval_sec
            mult = policy.backoff_multiplier
            use_jitter = policy.jitter

        # Base calculations
        attempt_idx = max(1, attempt_number)

        if strategy == RetryStrategy.FIXED:
            delay = float(initial)

        elif strategy == RetryStrategy.LINEAR:
            raw_delay = float(initial * attempt_idx)
            delay = min(float(max_int), raw_delay)

        elif strategy == RetryStrategy.EXPONENTIAL:
            # Formula: initial * (multiplier ^ (attempt - 1))
            power = max(0, attempt_idx - 1)
            raw_delay = float(initial) * (float(mult) ** power)
            capped_delay = min(float(max_int), raw_delay)

            if use_jitter:
                # Full Jitter (decorrelated uniform between 0.5 * delay and delay)
                min_jitter = 0.5 * capped_delay
                delay = random.uniform(min_jitter, capped_delay)
            else:
                delay = capped_delay

        else:
            delay = float(initial)

        return max(1.0, round(delay, 2))
