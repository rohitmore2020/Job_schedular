import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    CLAIMED = "claimed"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD_LETTER = "dead_letter"


class RetryStrategy(str, enum.Enum):
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


class WorkerStatus(str, enum.Enum):
    ALIVE = "alive"
    DRAINING = "draining"
    DEAD = "dead"


class ExecutionStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    KILLED = "killed"
