from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://todo:todo@localhost:5432/todo"
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    SESSION_COOKIE_NAME: str = "todo_session"
    SESSION_EXPIRES_DAYS: int = 14
    COOKIE_SECURE: bool = False

    REMINDER_LEAD_SECONDS: int = 900
    SCHEDULER_MISFIRE_GRACE_SECONDS: int = 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()
