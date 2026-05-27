"""Password hashing and server-side session lifecycle.

Sessions live in the `sessions` table; the cookie value is the opaque UUID `id`
of that row. Validity is checked server-side on every request (see `deps.py`),
so logout invalidates the credential immediately — the property JWT loses
without a denylist.
"""

import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession, joinedload

from .config import get_settings
from .models import Session as SessionRow

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

PASSWORD_MIN_LENGTH = 12

# Single fixed message returned for every kind of password rejection. The
# vagueness is intentional — we don't want to tell an attacker which rule
# tripped — but the message still tells a legitimate user exactly how to
# construct an acceptable password.
PASSWORD_REQUIREMENTS_MSG = (
    "Invalid password. Must be at least 12 characters and include "
    "at least one number and one symbol."
)

_DIGIT_RE = re.compile(r"\d")
_SYMBOL_RE = re.compile(r"[^A-Za-z0-9]")

# `last_used_at` is audit metadata — minute-level granularity is plenty.
# Writing it on every authenticated request turned every read into a
# write + COMMIT, capping how far the API can scale.
SESSION_TOUCH_INTERVAL = timedelta(seconds=60)


class InvalidPasswordError(ValueError):
    """Raised when a password fails the character-class rules. Single message,
    no per-rule detail (intentional — see PASSWORD_REQUIREMENTS_MSG)."""


def validate_password(password: str) -> None:
    """Enforce length + character-class rules. Returns nothing on success.

    Rules (enforced as a single all-or-nothing check; the caller sees the same
    message regardless of which rule failed):
      - length >= 12
      - at least one digit
      - at least one symbol (anything that is not [A-Za-z0-9])
    """
    if (
        len(password) < PASSWORD_MIN_LENGTH
        or _DIGIT_RE.search(password) is None
        or _SYMBOL_RE.search(password) is None
    ):
        raise InvalidPasswordError(PASSWORD_REQUIREMENTS_MSG)


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_session(db: DbSession, user_id: UUID) -> SessionRow:
    settings = get_settings()
    row = SessionRow(
        user_id=user_id,
        expires_at=_utcnow() + timedelta(days=settings.SESSION_EXPIRES_DAYS),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def lookup_session(db: DbSession, session_id: UUID) -> SessionRow | None:
    """Return the session row only if active, with `.user` eagerly loaded.

    Folds the user fetch into the session query (joinedload) so `get_current_user`
    doesn't need a second round-trip. Throttles the `last_used_at` write to
    SESSION_TOUCH_INTERVAL so most authenticated requests are pure reads.
    """
    row = db.execute(
        select(SessionRow)
        .options(joinedload(SessionRow.user))
        .where(SessionRow.id == session_id)
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.revoked_at is not None:
        return None
    now = _utcnow()
    if row.expires_at <= now:
        return None
    if now - row.last_used_at >= SESSION_TOUCH_INTERVAL:
        row.last_used_at = now
        db.commit()
    return row


def revoke_session(db: DbSession, session_id: UUID) -> None:
    row = db.get(SessionRow, session_id)
    if row is None or row.revoked_at is not None:
        return
    row.revoked_at = _utcnow()
    db.commit()
