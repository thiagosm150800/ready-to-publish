"""Iteration 5: login brute-force limit (5 fails / 15 min per email -> 429), success clears counter."""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
PWD = "testpass123"


@pytest.fixture
def throwaway():
    s = requests.Session()
    email = f"test_rl_{uuid.uuid4().hex[:10]}@example.com"
    r = s.post(f"{API}/auth/register", json={"name": "TEST_RateLimit", "email": email, "password": PWD})
    assert r.status_code == 201, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    yield email
    s.delete(f"{API}/auth/account")


def _login(email, pwd):
    return requests.post(f"{API}/auth/login", json={"email": email, "password": pwd})


# 5 wrong -> 6th (even correct) gets 429 with PT message
def test_five_fails_then_429(throwaway):
    for i in range(5):
        r = _login(throwaway, "wrongpass!")
        assert r.status_code == 401, (i, r.text)
        assert r.json()["detail"] == "E-mail ou senha incorretos"
    r = _login(throwaway, "wrongpass!")
    assert r.status_code == 429
    assert "Muitas tentativas" in r.json()["detail"]
    r = _login(throwaway, PWD)
    assert r.status_code == 429, "correct password must also be blocked during lockout"


# Case-insensitive email shares the counter
def test_counter_case_insensitive(throwaway):
    for _ in range(5):
        assert _login(throwaway.upper(), "nope1234").status_code == 401
    assert _login(throwaway, PWD).status_code == 429


# Success before reaching limit clears counter
def test_success_clears_counter(throwaway):
    for _ in range(4):
        assert _login(throwaway, "bad").status_code == 401
    r = _login(throwaway, PWD)
    assert r.status_code == 200 and "access_token" in r.json()
    for _ in range(4):
        assert _login(throwaway, "bad").status_code == 401
    assert _login(throwaway, PWD).status_code == 200


# Counter is per email: other email not affected
def test_counter_per_email(throwaway):
    other = f"test_rl_none_{uuid.uuid4().hex[:8]}@example.com"
    for _ in range(5):
        assert _login(other, "bad").status_code == 401
    assert _login(other, "bad").status_code == 429
    assert _login(throwaway, PWD).status_code == 200


# Main account still logs in (not locked by tests)
def test_main_account_ok():
    r = _login("motorista@teste.com", "teste1234")
    assert r.status_code == 200
