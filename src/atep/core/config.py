from functools import lru_cache
from pathlib import Path

from pydantic import EmailStr, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ATEP_", extra="ignore")

    app_name: str = "ATEP Core Platform"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://atep:atep@localhost:5432/atep"
    redis_url: str = "redis://localhost:6379/0"
    rabbitmq_url: str = "amqp://atep:atep@localhost:5672/"
    jwt_secret: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = Field(default=30, ge=5, le=1440)
    refresh_token_days: int = Field(default=30, ge=1, le=365)
    rate_limit_enabled: bool = True
    auth_rate_limit_requests: int = Field(default=5, ge=1, le=10_000)
    auth_rate_limit_ip_requests: int = Field(default=20, ge=1, le=100_000)
    auth_rate_limit_window_seconds: int = Field(default=60, ge=1, le=86_400)
    api_rate_limit_requests: int = Field(default=300, ge=1, le=1_000_000)
    api_rate_limit_window_seconds: int = Field(default=60, ge=1, le=86_400)
    module_reconciliation_enabled: bool = True
    module_reconciliation_interval_seconds: int = Field(default=15, ge=1, le=300)
    test_scheduler_enabled: bool = True
    test_scheduler_interval_seconds: int = Field(default=5, ge=1, le=300)
    test_scheduler_batch_size: int = Field(default=20, ge=1, le=200)
    test_artifact_storage_path: Path = Path(".atep/artifacts")
    test_artifact_max_bytes: int = Field(default=25 * 1024 * 1024, ge=1, le=1024 * 1024 * 1024)
    metrics_enabled: bool = True
    tracing_enabled: bool = False
    otel_service_name: str = Field(default="atep-core", min_length=1, max_length=80)
    otel_exporter_otlp_endpoint: str | None = None
    otel_trace_sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    bootstrap_admin_email: EmailStr | None = None
    bootstrap_admin_password: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
