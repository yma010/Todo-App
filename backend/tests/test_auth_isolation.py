"""Critical-path: cross-user data isolation + logout invalidation + password rules."""

from fastapi.testclient import TestClient

from app.security import PASSWORD_REQUIREMENTS_MSG

# Meets all rules: length >= 12, has digit (5), has symbol (-, !).
GOOD_PW = "TestPa55word-Demo!"


def _register(c: TestClient, email: str, password: str = GOOD_PW) -> dict:
    r = c.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


def test_register_login_me_logout_revokes_session(client: TestClient) -> None:
    _register(client, "alice@example.com")

    # /me is now reachable via the session cookie set by register.
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"

    # Logout invalidates the session row server-side AND clears the
    # client cookie via Set-Cookie: …; Max-Age=0.
    out = client.post("/api/auth/logout")
    assert out.status_code == 204
    set_cookie = out.headers.get("set-cookie", "")
    assert "todo_session=" in set_cookie
    assert "Max-Age=0" in set_cookie
    assert "todo_session" not in client.cookies

    # Even if the cookie somehow lingered, the server-side revocation
    # means /me is 401.
    after = client.get("/api/auth/me")
    assert after.status_code == 401


def test_request_with_malformed_session_cookie_clears_it(client: TestClient) -> None:
    """A non-UUID session cookie must be cleared by the server's 401 so
    a real browser stops re-sending a doomed credential."""
    # Use httpx's explicit-cookie kwarg so it isn't stored in the client jar
    # (avoids domain-matching quirks of TestClient.cookies.set on the assertion).
    r = client.get("/api/auth/me", cookies={"todo_session": "not-a-uuid"})
    assert r.status_code == 401
    set_cookie = r.headers.get("set-cookie", "")
    assert "todo_session=" in set_cookie
    assert "Max-Age=0" in set_cookie


def test_request_with_revoked_session_cookie_clears_it(client: TestClient) -> None:
    """If a client somehow re-sends a revoked cookie, the 401 carries
    a Set-Cookie deletion header so the browser drops it."""
    _register(client, "stale@example.com")
    stale_cookie = client.cookies.get("todo_session")
    assert stale_cookie is not None

    out = client.post("/api/auth/logout")
    assert out.status_code == 204

    r = client.get("/api/auth/me", cookies={"todo_session": stale_cookie})
    assert r.status_code == 401
    set_cookie = r.headers.get("set-cookie", "")
    assert "todo_session=" in set_cookie
    assert "Max-Age=0" in set_cookie


def test_unauthenticated_requests_are_401(client: TestClient) -> None:
    assert client.get("/api/todos").status_code == 401
    assert client.get("/api/notifications").status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_user_b_cannot_see_or_mutate_user_a_todo(
    client: TestClient, second_client: TestClient
) -> None:
    _register(client, "a@example.com")
    _register(second_client, "b@example.com")

    created = client.post("/api/todos", json={"title": "a's secret"})
    assert created.status_code == 201
    todo_id = created.json()["id"]

    # B's list does not include A's todo.
    rows = second_client.get("/api/todos").json()
    assert rows == []

    # B gets 404 (not 403) on direct GET/PATCH/DELETE.
    assert second_client.get(f"/api/todos/{todo_id}").status_code == 404
    assert (
        second_client.patch(f"/api/todos/{todo_id}", json={"title": "hijack"}).status_code
        == 404
    )
    assert second_client.delete(f"/api/todos/{todo_id}").status_code == 404

    # A still owns it unchanged.
    after = client.get(f"/api/todos/{todo_id}").json()
    assert after["title"] == "a's secret"


def test_duplicate_registration_returns_409(client: TestClient) -> None:
    _register(client, "dup@example.com")
    r = client.post(
        "/api/auth/register", json={"email": "dup@example.com", "password": GOOD_PW}
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "email already registered"


def test_duplicate_email_check_runs_before_password_check(client: TestClient) -> None:
    """Email-exists must surface as 409 even when the retry password is invalid —
    a user retrying a registration should not be sent through password debugging
    every time when the real problem is that the account already exists."""
    _register(client, "first@example.com")
    r = client.post(
        "/api/auth/register",
        # weak password + existing email: must report the email problem first.
        json={"email": "first@example.com", "password": "short"},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "email already registered"


# --- password validation: single fixed message regardless of which rule failed ---


def _expect_invalid_password(client: TestClient, password: str) -> None:
    r = client.post(
        "/api/auth/register", json={"email": "pw@example.com", "password": password}
    )
    assert r.status_code == 422, r.text
    # The same generic message for every failure — no per-rule disclosure.
    assert r.json()["detail"] == PASSWORD_REQUIREMENTS_MSG


def test_password_too_short_rejected(client: TestClient) -> None:
    _expect_invalid_password(client, "Ab1!short")  # 9 chars, has digit + symbol


def test_password_missing_digit_rejected(client: TestClient) -> None:
    _expect_invalid_password(client, "no-digits-here!!")  # 16 chars, symbol, no digit


def test_password_missing_symbol_rejected(client: TestClient) -> None:
    _expect_invalid_password(client, "AllLettersAnd123")  # 16 chars, digits, no symbol


def test_sequential_digits_rejected_by_char_class_rules(client: TestClient) -> None:
    """The original reported case: a long sequential-digits string passes
    length but has no symbol → rejected by the symbol rule."""
    _expect_invalid_password(client, "123456789101112")


def test_all_repeated_chars_rejected(client: TestClient) -> None:
    _expect_invalid_password(client, "aaaaaaaaaaaaaa")  # no digit, no symbol


def test_login_wrong_password_is_generic_401(client: TestClient) -> None:
    _register(client, "auth@example.com")
    r = client.post(
        "/api/auth/login", json={"email": "auth@example.com", "password": "wrongwrongwrong"}
    )
    assert r.status_code == 401
    # Generic message — must not leak that the user exists vs. doesn't.
    assert r.json()["detail"] == "invalid credentials"

    r2 = client.post(
        "/api/auth/login",
        json={"email": "noone@example.com", "password": "anyanyanyanyany"},
    )
    assert r2.status_code == 401
    assert r2.json()["detail"] == "invalid credentials"
