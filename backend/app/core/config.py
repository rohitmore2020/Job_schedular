from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application Info
    PROJECT_NAME: str = "Distributed Job Scheduler"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # PostgreSQL Database
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "job_scheduler"

    # Async Database URL (SQLAlchemy + asyncpg)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/job_scheduler"

    # Synchronous Database URL (Alembic)
    SYNC_DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/job_scheduler"

    # Security & JWT Auth
    SECRET_KEY: str = "super_secret_jwt_key_change_in_production_min_32_bytes_long_string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Worker & Scheduling Defaults
    WORKER_CONCURRENCY: int = 5
    HEARTBEAT_INTERVAL_SECONDS: int = 5
    JOB_LOCK_TIMEOUT_SECONDS: int = 30
    REAPER_SCAN_INTERVAL_SECONDS: int = 10
    CRON_SCAN_INTERVAL_SECONDS: int = 5

    # Server & CORS
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    # AI / LLM Failure Analysis
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


settings = Settings()
