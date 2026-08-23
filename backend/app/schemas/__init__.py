"""Pydantic v2 schemas for request validation and response serialization"""

from backend.app.schemas.user import UserResponse, OrganizationResponse
from backend.app.schemas.auth import (
    SignupRequest,
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from backend.app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectAPIKeyCreate,
    ProjectAPIKeyResponse,
    ProjectAPIKeyWithSecretResponse,
)
from backend.app.schemas.queue import (
    QueueCreate,
    QueueUpdate,
    QueueResponse,
    QueueStats,
    RetryPolicyCreate,
    RetryPolicyUpdate,
    RetryPolicyResponse,
)
from backend.app.schemas.job import (
    JobCreate,
    JobBatchCreate,
    JobResponse,
    JobDetailResponse,
    JobExecutionResponse,
    DLQEntryResponse,
    JobListResponse,
)
from backend.app.schemas.worker import (
    WorkerResponse,
    WorkerHeartbeatResponse,
)
from backend.app.schemas.dlq import (
    DLQEntryDetailResponse,
    DLQListResponse,
    DLQReplayResponse,
)
from backend.app.schemas.schedule import (
    ScheduledJobCreate,
    ScheduledJobUpdate,
    ScheduledJobResponse,
)
from backend.app.schemas.batch import (
    BatchCreate,
    BatchResponse,
    BatchDetailResponse,
    BatchListResponse,
)

__all__ = [
    "UserResponse",
    "OrganizationResponse",
    "SignupRequest",
    "LoginRequest",
    "RefreshTokenRequest",
    "TokenResponse",
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectResponse",
    "ProjectAPIKeyCreate",
    "ProjectAPIKeyResponse",
    "ProjectAPIKeyWithSecretResponse",
    "QueueCreate",
    "QueueUpdate",
    "QueueResponse",
    "QueueStats",
    "RetryPolicyCreate",
    "RetryPolicyUpdate",
    "RetryPolicyResponse",
    "JobCreate",
    "JobBatchCreate",
    "JobResponse",
    "JobDetailResponse",
    "JobExecutionResponse",
    "DLQEntryResponse",
    "JobListResponse",
    "WorkerResponse",
    "WorkerHeartbeatResponse",
    "DLQEntryDetailResponse",
    "DLQListResponse",
    "DLQReplayResponse",
    "ScheduledJobCreate",
    "ScheduledJobUpdate",
    "ScheduledJobResponse",
    "BatchCreate",
    "BatchResponse",
    "BatchDetailResponse",
    "BatchListResponse",
]
