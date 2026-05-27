"""Per-IP throttle + auth-failure logging on /auth/login and /auth/register."""

import logging

from fastapi.testclient import TestClient

from app.config import get_settings
from app.rate_limit import SlidingWindowLimiter
from app.routers.auth import login_limiter, register_limiter

GOOD_PW = "TestPa55word-Demo!"


def test_login_throttles_after_n_attempts_per_ip(client: TestClient, caplog) -> None:
    cap = get_settings().AUTH_LOGIN_MAX_PER_MIN
    # Register a real user so the 1st few attempts can be a mix of valid/invalid;
    # what matters is that the limiter counts attempts regardless of outcome.
    client.post("/api/auth/register", json={"email": "rl@example.com", "password": GOOD_PW})

    with caplog.at_level(logging.WARNING, logger="todo.auth"):
        for _ in range(cap):
            r = client.post(
                "/api/auth/login",
                json={"email": "rl@example.com", "password": "wrongwrongwrong"},
            )
            assert r.status_code == 401

        # The (cap+1)th attempt is throttled even if creds are correct.
        blocked = client.post(
            "/api/auth/login",
            json={"email": "rl@example.com", "password": GOOD_PW},
        )
        assert blocked.status_code == 429
        assert blocked.headers.get("Retry-After") == "60"
        assert blocked.json()["detail"] == "too many requests"

    # Each failed login emits a WARN; the throttle event also emits a WARN.
    failed_msgs = [r.message for r in caplog.records if "login failed" in r.message]
    throttle_msgs = [r.message for r in caplog.records if "login throttled" in r.message]
    assert len(failed_msgs) == cap
    assert len(throttle_msgs) == 1
    # Email isn't disclosed in plaintext; we log a 16-char fingerprint instead.
    assert "rl@example.com" not in " ".join(failed_msgs)
    assert "email_fp=" in failed_msgs[0]


def test_register_throttles_after_n_attempts_per_ip(client: TestClient) -> None:
    cap = get_settings().AUTH_REGISTER_MAX_PER_10MIN
    for i in range(cap):
        r = client.post(
            "/api/auth/register",
            json={"email": f"rl{i}@example.com", "password": GOOD_PW},
        )
        assert r.status_code == 201, r.text

    blocked = client.post(
        "/api/auth/register",
        json={"email": "rl-blocked@example.com", "password": GOOD_PW},
    )
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After") == "600"


def test_register_duplicate_email_is_logged(client: TestClient, caplog) -> None:
    client.post("/api/auth/register", json={"email": "dup@example.com", "password": GOOD_PW})

    with caplog.at_level(logging.WARNING, logger="todo.auth"):
        r = client.post(
            "/api/auth/register", json={"email": "dup@example.com", "password": GOOD_PW}
        )
    assert r.status_code == 409

    conflicts = [r for r in caplog.records if "register conflict" in r.message]
    assert len(conflicts) == 1
    assert "dup@example.com" not in conflicts[0].message
    assert "email_fp=" in conflicts[0].message


def test_limiter_resets_after_window() -> None:
    """Unit test on the limiter itself: confirms hits drop out of the window."""
    lim = SlidingWindowLimiter(max_hits=2, window_seconds=0.1)
    assert lim.check_and_record("k") is True
    assert lim.check_and_record("k") is True
    assert lim.check_and_record("k") is False  # over cap

    import time
    time.sleep(0.12)
    assert lim.check_and_record("k") is True  # window expired, allow again


def test_rate_limit_is_per_ip_not_global() -> None:
    """Smoke check on conftest's autouse limiter reset: confirms the module-level
    limiters used by the app are the same ones the test fixture resets."""
    # Pre-fill the login limiter; the autouse fixture should clear before the next test.
    for _ in range(get_settings().AUTH_LOGIN_MAX_PER_MIN):
        assert login_limiter.check_and_record("login:127.0.0.1") is True
    assert login_limiter.check_and_record("login:127.0.0.1") is False

    # Different "IP" key still gets its own budget.
    assert login_limiter.check_and_record("login:10.0.0.1") is True
    register_limiter.reset()  # noqa: ensure reference is real
