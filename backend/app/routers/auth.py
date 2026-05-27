from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from ..config import get_settings
from ..db import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import LoginIn, RegisterIn, UserOut
from ..security import (
    InvalidPasswordError,
    create_session,
    hash_password,
    revoke_session,
    validate_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
_settings = get_settings()


def _set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        key=_settings.SESSION_COOKIE_NAME,
        value=session_id,
        max_age=_settings.SESSION_EXPIRES_DAYS * 24 * 3600,
        httponly=True,
        secure=_settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_settings.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=_settings.COOKIE_SECURE,
        samesite="lax",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, response: Response, db: DbSession = Depends(get_db)) -> User:
    # Check email existence first: a user retrying with a weak password should
    # learn "this email is already registered" rather than re-debugging their
    # password every time.
    existing = db.query(User).filter(User.email == payload.email).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")

    try:
        validate_password(payload.password)
    except InvalidPasswordError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Race: another concurrent register won the unique constraint.
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")
    db.refresh(user)

    session = create_session(db, user.id)
    _set_session_cookie(response, str(session.id))
    return user


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, db: DbSession = Depends(get_db)) -> User:
    user = db.query(User).filter(User.email == payload.email).one_or_none()
    # Generic message: do not leak whether the email exists.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    session = create_session(db, user.id)
    _set_session_cookie(response, str(session.id))
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: DbSession = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=_settings.SESSION_COOKIE_NAME),
) -> Response:
    # Idempotent: 204 even without a valid cookie. Always clear client cookie.
    if session_cookie:
        try:
            revoke_session(db, UUID(session_cookie))
        except ValueError:
            pass
    _clear_session_cookie(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
