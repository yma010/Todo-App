from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session as DbSession

from .config import get_settings
from .db import get_db
from .models import User
from .security import lookup_session

_settings = get_settings()


def _cookie_clear_headers() -> dict[str, str]:
    # We can't mutate the injected Response and then `raise HTTPException` —
    # FastAPI's exception handler builds a fresh response and drops those
    # mutations. Instead, build the Set-Cookie deletion header here and
    # attach it to the HTTPException so it survives.
    tmp = Response()
    tmp.delete_cookie(
        key=_settings.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=_settings.COOKIE_SECURE,
        samesite="lax",
    )
    return {"set-cookie": tmp.headers["set-cookie"]}


def get_current_user(
    db: DbSession = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=_settings.SESSION_COOKIE_NAME),
) -> User:
    if not session_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    try:
        session_id = UUID(session_cookie)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid session",
            headers=_cookie_clear_headers(),
        )

    session = lookup_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="session expired",
            headers=_cookie_clear_headers(),
        )

    # `session.user` is eager-loaded by lookup_session — no extra round-trip.
    user = session.user
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user missing",
            headers=_cookie_clear_headers(),
        )
    return user
