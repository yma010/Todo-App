"""APScheduler-backed reminder scheduling.

Design:
- Jobs are persisted in Postgres via SQLAlchemyJobStore so they survive restart.
- Each reminder is keyed by `reminder:{todo_id}`, so reschedule is `replace_existing=True`.
- The fire job re-reads the todo and bails if it was deleted/completed or the due_at
  no longer matches the snapshot (handles edit-mid-fire races cleanly).
- The notifications table has UNIQUE(todo_id, due_at_snapshot); we wrap the insert in
  try/except IntegrityError so a double-fire produces exactly one row.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.exc import IntegrityError

from .config import get_settings
from .db import SessionLocal, engine

if TYPE_CHECKING:
    from .models import Todo

log = logging.getLogger("todo.scheduler")

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    if _scheduler is None:
        raise RuntimeError("scheduler not started")
    return _scheduler


def start_scheduler() -> BackgroundScheduler:
    """Start the global scheduler. Called from FastAPI lifespan."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    settings = get_settings()
    jobstore = SQLAlchemyJobStore(engine=engine, tablename="apscheduler_jobs")
    sched = BackgroundScheduler(
        jobstores={"default": jobstore},
        timezone="UTC",
        job_defaults={
            "coalesce": True,
            "misfire_grace_time": settings.SCHEDULER_MISFIRE_GRACE_SECONDS,
            "max_instances": 1,
        },
    )
    sched.start()
    _scheduler = sched
    log.info("scheduler started")
    return sched


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def _job_id(todo_id: UUID) -> str:
    return f"reminder:{todo_id}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _reminder_fire_time(due_at: datetime) -> datetime:
    lead = timedelta(seconds=get_settings().REMINDER_LEAD_SECONDS)
    return due_at - lead


def on_todo_upserted(todo: "Todo") -> None:
    """Schedule or reschedule the reminder for this todo.

    Cancels any existing job if the todo has no future due_at (no due, completed,
    or due in the past). Otherwise (re)schedules `reminder:{todo_id}` to fire at
    due_at - REMINDER_LEAD_SECONDS.
    """
    if _scheduler is None:
        # Scheduler not started (e.g. tests that don't need it).
        return

    job_id = _job_id(todo.id)
    if todo.completed or todo.due_at is None:
        _remove_job_quiet(job_id)
        return

    fire_at = _reminder_fire_time(todo.due_at)
    # If the fire time is already past the misfire grace window, schedule for "now"
    # so APScheduler picks it up; the job itself will decide whether to fire.
    if fire_at <= _utcnow():
        # Don't drop it on the floor — fire ASAP (still subject to job-side guards).
        fire_at = _utcnow() + timedelta(seconds=1)

    _scheduler.add_job(
        fire_reminder,
        trigger="date",
        run_date=fire_at,
        args=[str(todo.id), todo.due_at.isoformat()],
        id=job_id,
        replace_existing=True,
    )


def on_todo_deleted(todo_id: UUID) -> None:
    if _scheduler is None:
        return
    _remove_job_quiet(_job_id(todo_id))


def _remove_job_quiet(job_id: str) -> None:
    try:
        _scheduler.remove_job(job_id)  # type: ignore[union-attr]
    except Exception:
        # APScheduler raises JobLookupError if the job doesn't exist; ignore.
        pass


def fire_reminder(todo_id_str: str, due_at_iso: str) -> None:
    """Job body. Runs in a scheduler thread, not in request scope."""
    from .models import Notification, Todo  # local import: avoid load-time cycle

    todo_id = UUID(todo_id_str)
    due_at_snapshot = datetime.fromisoformat(due_at_iso)
    db = SessionLocal()
    try:
        todo = db.get(Todo, todo_id)
        if todo is None or todo.completed:
            # Cancellation that beat the cancel-job call, or completed mid-flight. No-op.
            log.info("reminder skip: todo %s gone or completed", todo_id)
            return
        if todo.due_at is None or todo.due_at != due_at_snapshot:
            # Stale job — due_at changed between schedule and fire. The new schedule
            # will run its own reminder.
            log.info("reminder skip: stale due_at for todo %s", todo_id)
            return

        notif = Notification(
            user_id=todo.user_id,
            todo_id=todo.id,
            due_at_snapshot=due_at_snapshot,
            message=f'Reminder: "{todo.title}" is due',
        )
        db.add(notif)
        try:
            db.commit()
            log.info("reminder fired: todo=%s notification=%s", todo_id, notif.id)
        except IntegrityError:
            db.rollback()
            log.info("reminder dedup (unique idx hit): todo=%s due=%s", todo_id, due_at_iso)
    except Exception:
        log.exception("reminder job failed for todo=%s", todo_id)
    finally:
        db.close()
