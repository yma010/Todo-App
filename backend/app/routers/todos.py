from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..deps import get_current_user
from ..models import Todo, User
from ..schemas import TodoCreate, TodoOut, TodoUpdate

if TYPE_CHECKING:
    from ..scheduler import ReminderScheduler  # noqa: F401

router = APIRouter(prefix="/api/todos", tags=["todos"])


def _get_owned_or_404(db: DbSession, todo_id: UUID, user_id: UUID) -> Todo:
    """Returns the row if owned by the user; else 404 (never 403) to avoid leaking row existence."""
    todo = db.get(Todo, todo_id)
    if todo is None or todo.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="todo not found")
    return todo


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@router.get("", response_model=list[TodoOut])
def list_todos(
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
) -> list[Todo]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    rows = db.execute(
        select(Todo)
        .where(Todo.user_id == user.id)
        .order_by(Todo.completed.asc(), Todo.due_at.asc().nulls_last(), Todo.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return list(rows)


@router.post("", response_model=TodoOut, status_code=status.HTTP_201_CREATED)
def create_todo(
    payload: TodoCreate,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> Todo:
    todo = Todo(
        user_id=user.id,
        title=payload.title.strip(),
        description=payload.description,
        due_at=payload.due_at,
    )
    db.add(todo)
    db.commit()
    db.refresh(todo)

    # Reminder scheduling wired up in Phase 5 via an event hook.
    from ..scheduler import on_todo_upserted  # local import to avoid circular at module load
    on_todo_upserted(todo)
    return todo


@router.get("/{todo_id}", response_model=TodoOut)
def get_todo(
    todo_id: UUID,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> Todo:
    return _get_owned_or_404(db, todo_id, user.id)


@router.patch("/{todo_id}", response_model=TodoOut)
def update_todo(
    todo_id: UUID,
    payload: TodoUpdate,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> Todo:
    todo = _get_owned_or_404(db, todo_id, user.id)

    if payload.title is not None:
        todo.title = payload.title.strip()
    if payload.description is not None:
        todo.description = payload.description
    if payload.completed is not None:
        todo.completed = payload.completed
    if payload.clear_due_at:
        todo.due_at = None
    elif payload.due_at is not None:
        todo.due_at = payload.due_at

    todo.updated_at = _utcnow()
    db.commit()
    db.refresh(todo)

    from ..scheduler import on_todo_upserted
    on_todo_upserted(todo)
    return todo


@router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(
    todo_id: UUID,
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
) -> None:
    todo = _get_owned_or_404(db, todo_id, user.id)
    todo_id_val = todo.id
    db.delete(todo)
    db.commit()

    from ..scheduler import on_todo_deleted
    on_todo_deleted(todo_id_val)
    return None
