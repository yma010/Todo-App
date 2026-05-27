"""M3 (prod config fail-closed) + M6 (security response headers)."""

import pytest
from fastapi.testclient import TestClient

from app.config import ProdConfigError, Settings


# ---------- M3: prod config validation ----------


def test_validate_for_env_dev_passes_with_insecure_defaults() -> None:
    s = Settings(ENV="dev", COOKIE_SECURE=False, FRONTEND_ORIGIN="http://localhost:5173")
    s.validate_for_env()  # no raise


def test_validate_for_env_prod_rejects_insecure_cookie() -> None:
    s = Settings(ENV="prod", COOKIE_SECURE=False, FRONTEND_ORIGIN="https://app.example")
    with pytest.raises(ProdConfigError, match="COOKIE_SECURE"):
        s.validate_for_env()


def test_validate_for_env_prod_rejects_http_origin() -> None:
    s = Settings(ENV="prod", COOKIE_SECURE=True, FRONTEND_ORIGIN="http://app.example")
    with pytest.raises(ProdConfigError, match="FRONTEND_ORIGIN"):
        s.validate_for_env()


def test_validate_for_env_prod_passes_with_secure_settings() -> None:
    s = Settings(ENV="prod", COOKIE_SECURE=True, FRONTEND_ORIGIN="https://app.example")
    s.validate_for_env()  # no raise


def test_validate_for_env_prod_reports_all_problems_at_once() -> None:
    s = Settings(ENV="prod", COOKIE_SECURE=False, FRONTEND_ORIGIN="http://app.example")
    with pytest.raises(ProdConfigError) as excinfo:
        s.validate_for_env()
    # Both failures surface in a single error — easier than re-running and
    # debugging one issue at a time.
    assert "COOKIE_SECURE" in str(excinfo.value)
    assert "FRONTEND_ORIGIN" in str(excinfo.value)


# ---------- M6: security headers ----------


def _assert_baseline_security_headers(headers) -> None:
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    sts = headers.get("strict-transport-security", "")
    assert "max-age=" in sts


def test_security_headers_on_healthz(client: TestClient) -> None:
    r = client.get("/api/healthz")
    assert r.status_code == 200
    _assert_baseline_security_headers(r.headers)


def test_api_responses_are_no_store(client: TestClient) -> None:
    """User-private API responses must not be cached by intermediaries."""
    r = client.get("/api/healthz")
    assert r.headers.get("cache-control") == "no-store"

    # Also on auth failures — don't let a cache hold onto an old session payload.
    r2 = client.get("/api/auth/me")
    assert r2.status_code == 401
    assert r2.headers.get("cache-control") == "no-store"


def test_security_headers_on_csrf_403(client: TestClient) -> None:
    """Headers must still be applied to early-return responses from middleware
    (i.e. the 403 from origin_check)."""
    r = client.post(
        "/api/todos",
        json={"title": "x"},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403
    _assert_baseline_security_headers(r.headers)


# ---------- docs gating ----------


def test_docs_url_helper_disables_in_prod() -> None:
    from app.main import _docs_url

    assert _docs_url("/docs", "dev") == "/docs"
    assert _docs_url("/docs", "test") == "/docs"
    assert _docs_url("/docs", "prod") is None
    assert _docs_url("/openapi.json", "prod") is None


def test_docs_reachable_in_dev_env(client: TestClient) -> None:
    """In the dev/test env the auto-docs stay on for ergonomics."""
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_disabled_in_prod_env() -> None:
    """Construct an isolated app with ENV=prod-equivalent docs config and
    confirm the routes 404 — proves the gating actually wires into FastAPI."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient as _TC

    from app.main import _docs_url

    env = "prod"
    prod_app = FastAPI(
        title="probe",
        docs_url=_docs_url("/docs", env),
        redoc_url=_docs_url("/redoc", env),
        openapi_url=_docs_url("/openapi.json", env),
    )
    with _TC(prod_app) as c:
        assert c.get("/docs").status_code == 404
        assert c.get("/redoc").status_code == 404
        assert c.get("/openapi.json").status_code == 404
