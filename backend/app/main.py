from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .routers import auth as auth_router
from .routers import notifications as notifications_router
from .routers import todos as todos_router
from .scheduler import start_scheduler, stop_scheduler

settings = get_settings()

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _docs_url(path: str, env: str) -> str | None:
    """Return the docs path in dev, None in prod (which disables the route).

    Hides the auto-generated /docs, /redoc, /openapi.json surface in prod —
    they're free reconnaissance otherwise (every route, every field, every
    validation rule). Kept on in dev for ergonomics.
    """
    return path if env != "prod" else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail closed: if ENV=prod with insecure defaults, refuse to start.
    settings.validate_for_env()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(
    title="Todo API",
    lifespan=lifespan,
    docs_url=_docs_url("/docs", settings.ENV),
    redoc_url=_docs_url("/redoc", settings.ENV),
    openapi_url=_docs_url("/openapi.json", settings.ENV),
)


@app.middleware("http")
async def origin_check(request: Request, call_next):
    """CSRF defense in depth.

    Rejects any state-changing request whose Origin is present but doesn't
    match FRONTEND_ORIGIN (covers "Origin: null" from sandboxed iframes too,
    since "null" != FRONTEND_ORIGIN). Missing Origin is allowed — curl,
    server-to-server, and TestClient all skip it; browsers always send it
    on mutating XHR/fetch, so combined with SameSite=Lax this blocks the
    real CSRF case without breaking non-browser clients.
    """
    if request.method in _MUTATING_METHODS:
        origin = request.headers.get("origin")
        if origin is not None and origin not in settings.allowed_origins:
            return JSONResponse(
                {"detail": "origin not allowed"},
                status_code=403,
            )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add baseline security headers to every response.

    - X-Content-Type-Options: nosniff — disable MIME sniffing.
    - X-Frame-Options: DENY — block all framing (defense in depth alongside CSP).
    - Strict-Transport-Security — browsers ignore over plain HTTP, so safe to
      send unconditionally; matters once the app is reachable via HTTPS.
    - Cache-Control: no-store on /api/* — keep user-private data out of
      shared/intermediary caches.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault(
        "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
    )
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router.router)
app.include_router(todos_router.router)
app.include_router(notifications_router.router)


@app.get("/api/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
