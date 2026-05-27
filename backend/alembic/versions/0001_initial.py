"""initial schema: users, sessions, todos, notifications.

Revision ID: 0001
Revises:
Create Date: 2026-05-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP, UUID

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_utcnow = sa.text("(now() AT TIME ZONE 'utc')")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", CITEXT(), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=_utcnow),
    )

    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=_utcnow),
        sa.Column("last_used_at", TIMESTAMP(timezone=True), nullable=False, server_default=_utcnow),
        sa.Column("revoked_at", TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    op.create_table(
        "todos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("due_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=_utcnow),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default=_utcnow),
    )
    op.create_index("ix_todos_user_id_due_at", "todos", ["user_id", "due_at"])

    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "todo_id",
            UUID(as_uuid=True),
            sa.ForeignKey("todos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("due_at_snapshot", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default=_utcnow),
        sa.Column("read_at", TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("todo_id", "due_at_snapshot", name="uq_notifications_todo_due_snapshot"),
    )
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_todos_user_id_due_at", table_name="todos")
    op.drop_table("todos")
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")
