from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow_server_default() -> text:
    return text("(now() AT TIME ZONE 'utc')")


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(CITEXT(), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=_utcnow_server_default(), nullable=False
    )

    sessions: Mapped[list["Session"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    todos: Mapped[list["Todo"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=_utcnow_server_default(), nullable=False
    )
    last_used_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=_utcnow_server_default(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")

    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )


class Todo(Base):
    __tablename__ = "todos"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    due_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=_utcnow_server_default(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=_utcnow_server_default(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="todos")
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="todo", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_todos_user_id_due_at", "user_id", "due_at"),)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    todo_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("todos.id", ondelete="CASCADE"), nullable=False
    )
    # Snapshot of the todo's due_at at the moment the reminder was scheduled.
    # The UNIQUE(todo_id, due_at_snapshot) index below makes the fire job idempotent.
    due_at_snapshot: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=_utcnow_server_default(), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    todo: Mapped[Todo] = relationship(back_populates="notifications")

    __table_args__ = (
        UniqueConstraint("todo_id", "due_at_snapshot", name="uq_notifications_todo_due_snapshot"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
    )
