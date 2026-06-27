from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Application settings loaded from environment or a .env file.

    Usage:
        from config import settings
        print(settings.MAIAGENT_API_KEY)
    """

    # AI / Agent
    MAIAGENT_API_KEY: Optional[str] = Field(None, description="Groq / MAI Agent API key")
    MAIAGENT_CHATBOT_ID: Optional[str] = Field(None)
    MAIAGENT_WEBCHAT_ID: Optional[str] = Field(None)

    # Supabase
    SUPABASE_URL: Optional[str] = Field(None)
    SUPABASE_KEY: Optional[str] = Field(None)

    # Redis
    REDIS_HOST: str = Field("localhost")
    REDIS_PORT: int = Field(6379)
    REDIS_PASSWORD: Optional[str] = Field(None)
    REDIS_DB: int = Field(0)
    REDIS_MAX_CONNECTIONS: int = Field(50)

    # Postgres / DB
    POSTGRES_URL: Optional[str] = Field(None)
    POSTGRES_HOST: Optional[str] = Field(None)
    POSTGRES_PORT: Optional[int] = Field(None)
    POSTGRES_USER: Optional[str] = Field(None)
    POSTGRES_PASSWORD: Optional[str] = Field(None)
    POSTGRES_DB: Optional[str] = Field(None)
    DB_PATH: str = Field("history.db")

    # FastAPI / runtime
    ENVIRONMENT: str = Field("development")
    DEBUG: bool = Field(False)
    TZ: str = Field("Asia/Taipei")
    LOG_LEVEL: str = Field("INFO")
    LOG_FORMAT: str = Field("json")
    API_HOST: str = Field("0.0.0.0")
    API_PORT: int = Field(8000)
    API_WORKERS: int = Field(4)

    # Email / notifier
    EMAIL_SENDER: Optional[str] = Field(None)
    EMAIL_PASSWORD: Optional[str] = Field(None)
    EMAIL_RECEIVER: Optional[str] = Field(None)

    # Third-party keys
    GEMINI_API_KEY: Optional[str] = Field(None)
    MULTION_API_KEY: Optional[str] = Field(None)
    NEWS_API_KEY: Optional[str] = Field(None)

    # ML / cache / tasks
    ML_MODEL_PATH: str = Field("./models")
    ML_FEATURE_CACHE_SIZE: int = Field(1000)
    ML_PCA_COMPONENTS: int = Field(10)

    CACHE_TYPE: str = Field("redis")
    CACHE_TTL_KLINE: int = Field(86400)
    CACHE_TTL_SENTIMENT: int = Field(3600)
    CACHE_TTL_ANALYSIS: int = Field(1800)
    CACHE_TTL_MACRO: int = Field(300)

    TASK_QUEUE_WORKERS: int = Field(10)
    TASK_MAX_RETRIES: int = Field(3)
    TASK_TIMEOUT: int = Field(300)

    # Monitoring
    ENABLE_METRICS: bool = Field(True)
    METRICS_PORT: int = Field(8001)
    SENTRY_DSN: Optional[str] = Field(None)

    # Docker / CI
    DOCKER_REGISTRY: Optional[str] = Field(None)
    DOCKER_IMAGE_TAG: Optional[str] = Field(None)
    DOCKER_PULL_POLICY: Optional[str] = Field(None)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
