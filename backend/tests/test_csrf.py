"""CSRF defense in depth: Origin-header check on mutating routes."""

from fastapi.testclient import TestClient

from app.config import get_settings

GOOD_PW = "TestPa55word-Demo!"
# FRONTEND_ORIGIN is now a comma-separated list — pick the first parsed
# entry to use as a valid Origin header.
ALLOWED_ORIGIN = get_settings().allowed_origins[0]


def _register(c: TestClient, email: str = "csrf@example.com") -> None:
    r = c.post("/api/auth/register", json={"email": email, "password": GOOD_PW})
    assert r.status_code == 201, r.text


def test_mutating_request_with_mismatched_origin_is_rejected(client: TestClient) -> None:
    _register(client)
    r = client.post(
        "/api/todos",
        json={"title": "csrf-attempt"},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "origin not allowed"


def test_mutating_request_with_null_origin_is_rejected(client: TestClient) -> None:
    """Sandboxed iframes / file:// pages send Origin: null."""
    _register(client)
    r = client.post(
        "/api/todos",
        json={"title": "csrf-null"},
        headers={"Origin": "null"},
    )
    assert r.status_code == 403


def test_mutating_request_with_matching_origin_is_allowed(client: TestClient) -> None:
    _register(client)
    r = client.post(
        "/api/todos",
        json={"title": "ok"},
        headers={"Origin": ALLOWED_ORIGIN},
    )
    assert r.status_code == 201


def test_mutating_request_with_no_origin_is_allowed(client: TestClient) -> None:
    """curl / server-to-server / non-browser clients omit Origin. SameSite=Lax
    covers the browser CSRF case; we don't want to break tooling."""
    _register(client)
    r = client.post("/api/todos", json={"title": "ok"})
    assert r.status_code == 201


def test_get_with_mismatched_origin_is_allowed(client: TestClient) -> None:
    """We only enforce on state-changing methods; GETs aren't blocked."""
    _register(client)
    r = client.get("/api/todos", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200


def test_csrf_check_blocks_auth_endpoints_too(client: TestClient) -> None:
    """A cross-origin /auth/login or /auth/logout would let an attacker
    force a session swap or log a victim out. Confirm the middleware also
    covers /api/auth/*."""
    bad = {"Origin": "https://evil.example"}
    assert client.post("/api/auth/register", json={"email": "x@y.z", "password": GOOD_PW}, headers=bad).status_code == 403
    assert client.post("/api/auth/login", json={"email": "x@y.z", "password": GOOD_PW}, headers=bad).status_code == 403
    assert client.post("/api/auth/logout", headers=bad).status_code == 403
