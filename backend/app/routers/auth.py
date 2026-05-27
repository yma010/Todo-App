import hashlib
import logging
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from ..config import get_settings
from ..db import get_db
from ..deps import get_current_user
from ..models import User
from ..rate_limit import SlidingWindowLimiter
from ..schemas import LoginIn, RegisterIn, UserOut
from ..security import (
    InvalidPasswordError,
    create_session,
    hash_password,
    revoke_session,
    validate_password,
    verify_password,
)

log = logging.getLogger("todo.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])
_settings = get_settings()

# Per-IP throttles. Module-level so the state survives request boundaries.
# These limit total attempts (success or failure) — bcrypt is expensive,
# so even a successful flood is worth throttling. Tests use reset_auth_limiters().
login_limiter = SlidingWindowLimiter(
    max_hits=_settings.AUTH_LOGIN_MAX_PER_MIN, window_seconds=60
)
register_limiter = SlidingWindowLimiter(
    max_hits=_settings.AUTH_REGISTER_MAX_PER_10MIN, window_seconds=600
)


def reset_auth_limiters() -> None:
    """Test hook: clear the throttle state between tests."""
    login_limiter.reset()
    register_limiter.reset()


def _client_ip(request: Request) -> str:
    # NOTE: trusts request.client.host directly. Behind a reverse proxy,
    # configure uvicorn with --proxy-headers and a trusted-hosts list so
    # X-Forwarded-For is respected without spoofing.
    return request.client.host if request.client else "unknown"


def _email_fp(email: str) -> str:
    """16-char fingerprint of an email for log correlation without disclosure."""
    return hashlib.sha256(email.lower().encode()).hexdigest()[:16]


def _throttle_or_raise(
    limiter: SlidingWindowLimiter, key: str, ip: str, event: str, retry_after: int
) -> None:
    if not limiter.check_and_record(key):
        log.warning("%s throttled: ip=%s", event, ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many requests",
            headers={"Retry-After": str(retry_after)},
        )


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
def register(
    payload: RegisterIn,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> User:
    ip = _client_ip(request)
    _throttle_or_raise(register_limiter, f"register:{ip}", ip, "register", retry_after=600)

    # Check email existence first: a user retrying with a weak password should
    # learn "this email is already registered" rather than re-debugging their
    # password every time.
    existing = db.query(User).filter(User.email == payload.email).one_or_none()
    if existing is not None:
        log.warning("register conflict: email_fp=%s ip=%s", _email_fp(payload.email), ip)
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
        log.warning("register conflict: email_fp=%s ip=%s", _email_fp(payload.email), ip)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")
    db.refresh(user)

    session = create_session(db, user.id)
    _set_session_cookie(response, str(session.id))
    return user


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> User:
    ip = _client_ip(request)
    _throttle_or_raise(login_limiter, f"login:{ip}", ip, "login", retry_after=60)

    user = db.query(User).filter(User.email == payload.email).one_or_none()
    # Generic message: do not leak whether the email exists.
    if user is None or not verify_password(payload.password, user.password_hash):
        log.warning("login failed: email_fp=%s ip=%s", _email_fp(payload.email), ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    session = create_session(db, user.id)
    _set_session_cookie(response, str(session.id))
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    db: DbSession = Depends(get_db),
    session_cookie: str | None = Cookie(default=None, alias=_settings.SESSION_COOKIE_NAME),
) -> Response:
    # Idempotent: 204 even without a valid cookie. Always clear client cookie.
    if session_cookie:
        try:
            revoke_session(db, UUID(session_cookie))
        except ValueError:
            pass
    # Build the response here and clear the cookie on *it*. Mutating an
    # injected Response and then returning a fresh Response drops the
    # Set-Cookie header.
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookie(response)
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
