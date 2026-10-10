"""Environment-backed configuration for the hosted API."""

from __future__ import annotations

from dataclasses import dataclass
import os


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        value.strip().rstrip("/")
        for value in os.environ.get(name, default).split(",")
        if value.strip()
    )


def _bool(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    environment: str = os.environ.get("JARVIS_ENV", "development").lower()
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "sqlite:///./tmp/jarvis_web.db",
    )
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    jwt_secret: str = os.environ.get("JWT_SECRET", "local-development-only-change-me")
    encryption_key: str = os.environ.get("JARVIS_ENCRYPTION_KEY", "")
    access_token_minutes: int = int(os.environ.get("ACCESS_TOKEN_MINUTES", "1440"))
    cors_origins: tuple[str, ...] = _csv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    chat_model: str = os.environ.get("JARVIS_CHAT_MODEL", "gemini-2.5-flash")
    auto_create_tables: bool = _bool("AUTO_CREATE_TABLES", "1")
    redis_required: bool = _bool("REDIS_REQUIRED", "0")
    lilith_notifications_enabled: bool = _bool("JARVIS_LILITH_NOTIFICATIONS_ENABLED", "0")
    lilith_voice_notifications_enabled: bool = _bool("JARVIS_LILITH_VOICE_NOTIFICATIONS_ENABLED", "0")
    lilith_notification_poll_seconds: float = float(os.environ.get("JARVIS_LILITH_NOTIFICATION_POLL_SECONDS", "30"))

    def validate_production(self) -> None:
        if self.environment != "production":
            return
        if self.jwt_secret == "local-development-only-change-me":
            raise RuntimeError("JWT_SECRET must be configured in production")
        if not self.encryption_key:
            raise RuntimeError("JARVIS_ENCRYPTION_KEY must be configured in production")
        if not self.database_url.startswith(("postgresql://", "postgres://", "postgresql+")):
            raise RuntimeError("Production DATABASE_URL must point to Postgres")


settings = Settings()
