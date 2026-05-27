from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ProdConfigError(RuntimeError):
    """Raised when ENV=prod but security-critical settings are still at dev defaults."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "dev" | "prod". When "prod", validate_for_env() enforces secure defaults
    # and the app refuses to start with an insecure config.
    ENV: str = "dev"

    DATABASE_URL: str = "postgresql+psycopg://todo:todo@localhost:5432/todo"
    # Comma-separated list of origins the browser may legitimately send on
    # mutating requests. localhost and 127.0.0.1 are both included by default
    # because browsers don't canonicalize them to each other — Vite prints
    # both as accessible URLs and we don't want a "what hostname did you
    # type" trap. In prod this becomes the single https origin of the SPA.
    FRONTEND_ORIGIN: str = "http://localhost:5173,http://127.0.0.1:5173"

    SESSION_COOKIE_NAME: str = "todo_session"
    SESSION_EXPIRES_DAYS: int = 14
    COOKIE_SECURE: bool = False

    REMINDER_LEAD_SECONDS: int = 900
    SCHEDULER_MISFIRE_GRACE_SECONDS: int = 3600

    # Auth throttling (per-IP, in-process — single worker only).
    AUTH_LOGIN_MAX_PER_MIN: int = 10
    AUTH_REGISTER_MAX_PER_10MIN: int = 5

    @property
    def allowed_origins(self) -> list[str]:
        """Parsed FRONTEND_ORIGIN. Trims whitespace; drops empties."""
        return [o.strip() for o in self.FRONTEND_ORIGIN.split(",") if o.strip()]

    def validate_for_env(self) -> None:
        """Fail closed if ENV=prod but security-critical settings are still dev defaults.

        Called from FastAPI's lifespan so misconfig surfaces at startup, not on
        first authenticated request. Dev/test ENVs skip the check.
        """
        if self.ENV != "prod":
            return
        problems: list[str] = []
        if not self.COOKIE_SECURE:
            problems.append("COOKIE_SECURE must be true in prod")
        origins = self.allowed_origins
        if not origins:
            problems.append("FRONTEND_ORIGIN must contain at least one origin")
        for o in origins:
            if not o.startswith("https://"):
                problems.append(f"FRONTEND_ORIGIN entries must be https:// in prod (got {o!r})")
        if problems:
            raise ProdConfigError("invalid prod config: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
