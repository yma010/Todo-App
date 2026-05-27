from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session as DbSession

from .config import get_settings
from .db import get_db
from .models import User
from .security import lookup_session

_settings = get_settings()


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_settings.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=_settings.COOKIE_SECURE,
        samesite="lax",
    )


def get_current_user(
    response: Response,
    db: DbSession = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=_settings.SESSION_COOKIE_NAME),
) -> User:
    if not session_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    try:
        session_id = UUID(session_cookie)
    except ValueError:
        _clear_session_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session")

    session = lookup_session(db, session_id)
    if session is None:
        _clear_session_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired")

    user = db.get(User, session.user_id)
    if user is None:
        _clear_session_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user missing")
    return user
