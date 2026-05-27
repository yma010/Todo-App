"""Test fixtures.

We use a dedicated `todo_test` Postgres database — recreated once per pytest
session — and a fresh APScheduler with an in-memory job store so reminder
tests can introspect/modify jobs without persistent state leaking across runs.
"""

import os
from collections.abc import Iterator

import pytest
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


def _admin_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_ADMIN_URL",
        "postgresql+psycopg://todo:todo@localhost:5432/postgres",
    )


def _test_db_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://todo:todo@localhost:5432/todo_test",
    )


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_database() -> Iterator[None]:
    """Create todo_test if it doesn't exist, then apply migrations."""
    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT", future=True)
    with admin.connect() as c:
        exists = c.execute(text("SELECT 1 FROM pg_database WHERE datname='todo_test'")).first()
        if not exists:
            c.execute(text("CREATE DATABASE todo_test"))
    admin.dispose()

    # Point app at test DB *before* importing app modules that cache settings.
    os.environ["DATABASE_URL"] = _test_db_url()

    # Apply schema.
    from app.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]
    from app import db as app_db  # noqa: F401
    # Recreate engine for the new URL.
    app_db.engine.dispose()
    app_db.engine = create_engine(_test_db_url(), future=True, pool_pre_ping=True)
    from sqlalchemy.orm import sessionmaker
    app_db.SessionLocal = sessionmaker(bind=app_db.engine, autoflush=False, autocommit=False, future=True)

    # citext extension + create_all.
    with app_db.engine.begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS citext"))
    from app import models  # noqa: F401  -- register models on Base.metadata
    app_db.Base.metadata.drop_all(app_db.engine)
    app_db.Base.metadata.create_all(app_db.engine)
    yield


@pytest.fixture(autouse=True)
def _truncate_between_tests() -> Iterator[None]:
    """Wipe rows AND clear the in-process auth rate-limiter so each test
    starts clean (otherwise a chatty test can poison its neighbor with 429s)."""
    from app import db as app_db
    from app.routers.auth import reset_auth_limiters
    reset_auth_limiters()
    yield
    reset_auth_limiters()
    with app_db.engine.begin() as c:
        c.execute(
            text(
                "TRUNCATE notifications, todos, sessions, users RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def test_scheduler() -> Iterator[BackgroundScheduler]:
    """Replace the global scheduler with a memory-backed one for the duration of a test."""
    from app import scheduler as sch
    sched = BackgroundScheduler(
        jobstores={"default": MemoryJobStore()},
        timezone="UTC",
        job_defaults={"coalesce": True, "misfire_grace_time": 3600, "max_instances": 1},
    )
    sched.start()
    original = sch._scheduler  # noqa: SLF001
    sch._scheduler = sched
    try:
        yield sched
    finally:
        sch._scheduler = original
        sched.shutdown(wait=False)


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A TestClient with its own cookie jar (per-test, per-client)."""
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def second_client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as c:
        yield c
