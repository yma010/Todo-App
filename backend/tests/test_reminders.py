"""Critical-path: reminder scheduling lifecycle + idempotent fire."""

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.testclient import TestClient


_GOOD_PW = "TestPa55word-Demo!"


def _register(c: TestClient, email: str = "r@example.com") -> dict:
    r = c.post("/api/auth/register", json={"email": email, "password": _GOOD_PW})
    assert r.status_code == 201, r.text
    return r.json()


def _make_todo(c: TestClient, **kwargs) -> dict:
    r = c.post("/api/todos", json=kwargs)
    assert r.status_code == 201, r.text
    return r.json()


def _job_id(todo_id: str) -> str:
    return f"reminder:{todo_id}"


def test_create_with_due_schedules_a_job(
    client: TestClient, test_scheduler: BackgroundScheduler
) -> None:
    _register(client)
    due = datetime.now(timezone.utc) + timedelta(minutes=20)
    todo = _make_todo(client, title="call mom", due_at=due.isoformat())

    job = test_scheduler.get_job(_job_id(todo["id"]))
    assert job is not None
    # Lead default is 900s = 15 minutes; fire ~5 minutes from now.
    assert abs((job.next_run_time - (due - timedelta(seconds=900))).total_seconds()) < 2


def test_update_due_at_reschedules_job(
    client: TestClient, test_scheduler: BackgroundScheduler
) -> None:
    _register(client)
    due = datetime.now(timezone.utc) + timedelta(minutes=20)
    todo = _make_todo(client, title="t", due_at=due.isoformat())
    original_run = test_scheduler.get_job(_job_id(todo["id"])).next_run_time

    new_due = due + timedelta(minutes=30)
    r = client.patch(f"/api/todos/{todo['id']}", json={"due_at": new_due.isoformat()})
    assert r.status_code == 200

    job = test_scheduler.get_job(_job_id(todo["id"]))
    assert job is not None
    assert job.next_run_time > original_run
    assert abs((job.next_run_time - (new_due - timedelta(seconds=900))).total_seconds()) < 2


def test_delete_removes_job(client: TestClient, test_scheduler: BackgroundScheduler) -> None:
    _register(client)
    due = datetime.now(timezone.utc) + timedelta(minutes=20)
    todo = _make_todo(client, title="t", due_at=due.isoformat())
    assert test_scheduler.get_job(_job_id(todo["id"])) is not None

    r = client.delete(f"/api/todos/{todo['id']}")
    assert r.status_code == 204
    assert test_scheduler.get_job(_job_id(todo["id"])) is None


def test_marking_complete_cancels_job(
    client: TestClient, test_scheduler: BackgroundScheduler
) -> None:
    _register(client)
    due = datetime.now(timezone.utc) + timedelta(minutes=20)
    todo = _make_todo(client, title="t", due_at=due.isoformat())
    assert test_scheduler.get_job(_job_id(todo["id"])) is not None

    r = client.patch(f"/api/todos/{todo['id']}", json={"completed": True})
    assert r.status_code == 200
    assert test_scheduler.get_job(_job_id(todo["id"])) is None


def test_clearing_due_at_cancels_job(
    client: TestClient, test_scheduler: BackgroundScheduler
) -> None:
    _register(client)
    due = datetime.now(timezone.utc) + timedelta(minutes=20)
    todo = _make_todo(client, title="t", due_at=due.isoformat())
    assert test_scheduler.get_job(_job_id(todo["id"])) is not None

    r = client.patch(f"/api/todos/{todo['id']}", json={"clear_due_at": True})
    assert r.status_code == 200
    assert test_scheduler.get_job(_job_id(todo["id"])) is None


def test_fire_reminder_is_idempotent(
    client: TestClient, test_scheduler: BackgroundScheduler
) -> None:
    """The job must produce exactly one notification per (todo_id, due_at_snapshot)
    even if invoked multiple times. This is what the UNIQUE index guarantees and
    what the IntegrityError-swallow in scheduler.fire_reminder relies on.
    """
    _register(client)
    due = datetime.now(timezone.utc) + timedelta(minutes=20)
    todo = _make_todo(client, title="t", due_at=due.isoformat())

    from app.scheduler import fire_reminder

    fire_reminder(todo["id"], due.isoformat())
    fire_reminder(todo["id"], due.isoformat())
    fire_reminder(todo["id"], due.isoformat())

    notifs = client.get("/api/notifications").json()
    assert len(notifs) == 1
    assert notifs[0]["todo_id"] == todo["id"]


def test_fire_reminder_skips_when_todo_deleted(
    client: TestClient, test_scheduler: BackgroundScheduler
) -> None:
    _register(client)
    due = datetime.now(timezone.utc) + timedelta(minutes=20)
    todo = _make_todo(client, title="t", due_at=due.isoformat())

    client.delete(f"/api/todos/{todo['id']}")

    from app.scheduler import fire_reminder
    fire_reminder(todo["id"], due.isoformat())

    notifs = client.get("/api/notifications").json()
    assert notifs == []


def test_fire_reminder_skips_when_due_at_changed(
    client: TestClient, test_scheduler: BackgroundScheduler
) -> None:
    """A job created for the original due_at must not fire a notification after
    the user edits the due_at — the new schedule has its own job."""
    _register(client)
    due = datetime.now(timezone.utc) + timedelta(minutes=20)
    todo = _make_todo(client, title="t", due_at=due.isoformat())

    new_due = due + timedelta(hours=1)
    client.patch(f"/api/todos/{todo['id']}", json={"due_at": new_due.isoformat()})

    from app.scheduler import fire_reminder
    # Fire the OLD job — the snapshot won't match the current row.
    fire_reminder(todo["id"], due.isoformat())

    notifs = client.get("/api/notifications").json()
    assert notifs == []
