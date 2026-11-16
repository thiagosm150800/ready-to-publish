"""Iteration 4: JWT auth, per-driver data isolation, monthly report, privacy page, account deletion."""
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
TZ = -180
MAIN = {"email": "motorista@teste.com", "password": "teste1234"}


def _new_user(name="TEST_Driver"):
    s = requests.Session()
    email = f"test_{uuid.uuid4().hex[:10]}@example.com"
    r = s.post(f"{API}/auth/register", json={"name": name, "email": email, "password": "testpass123"})
    assert r.status_code == 201, r.text
    d = r.json()
    s.headers["Authorization"] = f"Bearer {d['access_token']}"
    return s, email, d


@pytest.fixture
def user_a():
    s, email, d = _new_user("TEST_Ana Silva")
    yield s, email, d
    s.delete(f"{API}/auth/account")


@pytest.fixture
def user_b():
    s, email, d = _new_user("TEST_Bruno")
    yield s, email, d
    s.delete(f"{API}/auth/account")


# --- auth ---
def test_register_returns_token_and_user(user_a):
    s, email, d = user_a
    assert d["token_type"] == "bearer" and d["access_token"]
    assert d["user"]["email"] == email and d["user"]["name"] == "TEST_Ana Silva"
    assert "password_hash" not in d["user"] and "_id" not in d["user"]


def test_register_duplicate_409(user_a):
    _, email, _ = user_a
    r = requests.post(f"{API}/auth/register", json={"name": "X", "email": email.upper(), "password": "testpass123"})
    assert r.status_code == 409


@pytest.mark.parametrize("body", [
    {"name": "X", "email": "test_short@example.com", "password": "1234567"},
    {"name": "", "email": "test_noname@example.com", "password": "testpass123"},
    {"name": "X", "email": "not-an-email", "password": "testpass123"},
])
def test_register_validation_422(body):
    assert requests.post(f"{API}/auth/register", json=body).status_code == 422


def test_login_ok_and_wrong(user_a):
    _, email, _ = user_a
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "testpass123"})
    assert r.status_code == 200 and r.json()["user"]["email"] == email
    assert requests.post(f"{API}/auth/login", json={"email": email, "password": "wrongpass1"}).status_code == 401
    assert requests.post(f"{API}/auth/login", json={"email": "test_nobody@example.com", "password": "x12345678"}).status_code == 401


def test_main_credentials_login():
    r = requests.post(f"{API}/auth/login", json=MAIN)
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200 and me.json()["email"] == MAIN["email"]


def test_me(user_a):
    s, email, d = user_a
    me = s.get(f"{API}/auth/me").json()
    assert me == d["user"]


@pytest.mark.parametrize("method,path", [
    ("get", "/auth/me"), ("get", "/settings"), ("put", "/settings"), ("post", "/simulate"),
    ("post", "/rides/bulk"), ("get", "/rides"), ("delete", "/rides"), ("get", "/stats"),
    ("get", "/stats/weekly"), ("get", "/stats/monthly"), ("delete", "/auth/account"),
])
def test_protected_401(method, path):
    r = getattr(requests, method)(f"{API}{path}", json={} if method in ("put",) else ([] if path == "/rides/bulk" else None))
    assert r.status_code == 401, (path, r.status_code)
    r = getattr(requests, method)(f"{API}{path}", headers={"Authorization": "Bearer garbage.token.x"})
    assert r.status_code == 401, (path, r.status_code)


# --- isolation ---
def test_data_isolation(user_a, user_b):
    a, _, _ = user_a
    b, _, _ = user_b
    a.put(f"{API}/settings", json={"min_fare": 0, "min_price_per_km": 0, "max_pickup_km": 100})
    b.put(f"{API}/settings", json={"min_fare": 55.5})
    assert a.get(f"{API}/settings").json()["min_fare"] == 0
    assert b.get(f"{API}/settings").json()["min_fare"] == 55.5
    ids = [a.post(f"{API}/simulate?tz={TZ}").json()["id"] for _ in range(3)]
    assert {x["id"] for x in a.get(f"{API}/rides").json()} == set(ids)
    assert b.get(f"{API}/rides").json() == []
    assert b.get(f"{API}/stats").json()["today_total"] == 0
    assert b.get(f"{API}/stats/weekly?tz={TZ}").json()["week_total"] == 0
    assert b.get(f"{API}/stats/monthly?tz={TZ}").json()["total"] == 0
    assert a.get(f"{API}/stats/monthly?tz={TZ}").json()["total"] == 3
    # B clearing history must not touch A
    assert b.delete(f"{API}/rides").json()["deleted"] == 0
    assert len(a.get(f"{API}/rides").json()) == 3
    assert a.delete(f"{API}/rides").json()["deleted"] == 3
    assert a.get(f"{API}/rides").json() == []


# --- monthly ---
def test_monthly_values(user_a):
    s, _, _ = user_a
    now_local = datetime.now(timezone.utc) + timedelta(minutes=TZ)
    month = now_local.strftime("%Y-%m")
    d1 = now_local.replace(day=1, hour=10, minute=0, second=0, microsecond=0)
    ts1 = d1.strftime("%Y-%m-%dT%H:%M:%S") + "-03:00"
    ts2 = d1.replace(hour=18).strftime("%Y-%m-%dT%H:%M:%S") + "-03:00"
    items = [
        {"price": 30.0, "trip_km": 10.0, "accepted": True, "created_at": ts1},
        {"price": 20.0, "trip_km": 5.0, "accepted": True, "created_at": ts2},
        {"price": 4.0, "trip_km": 10.0, "accepted": False, "reasons": ["R$/km abaixo do mínimo", "Valor abaixo do mínimo"], "created_at": ts2},
        # previous month, last local minute (must NOT count in current month)
        {"price": 99.0, "trip_km": 10.0, "accepted": True,
         "created_at": (d1.replace(hour=0) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S") + "-03:00"},
    ]
    assert s.post(f"{API}/rides/bulk", json=items).json()["inserted"] == 4
    r = s.get(f"{API}/stats/monthly", params={"tz": TZ, "month": month})
    assert r.status_code == 200
    d = r.json()
    assert d["month"] == month
    assert d["earnings"] == 50.0 and d["accepted"] == 2 and d["total"] == 3
    assert d["accept_rate"] == 66.7 and d["km"] == 15.0
    assert d["avg_price_per_km"] == round(50 / 15, 2) and d["avg_ride"] == 25.0
    assert d["active_days"] == 1 and d["avg_per_day"] == 50.0
    assert len(d["hours"]) == 24 and d["hours"][10]["earnings"] == 30.0 and d["hours"][18]["total"] == 2
    assert [h["hour"] for h in d["best_hours"]] == [10, 18]
    assert d["best_days"][0]["earnings"] == 50.0
    assert {"reason": "R$/km abaixo do mínimo", "count": 1} in d["rejection_reasons"]
    prev = (d1 - timedelta(days=1)).strftime("%Y-%m")
    p = s.get(f"{API}/stats/monthly", params={"tz": TZ, "month": prev}).json()
    assert p["earnings"] == 99.0 and p["total"] == 1
    # default month == current
    assert s.get(f"{API}/stats/monthly", params={"tz": TZ}).json()["month"] == month


@pytest.mark.parametrize("bad", ["2025-13", "2025-1", "abcd-ef", "2025-00", "202501"])
def test_monthly_invalid_month_422(user_a, bad):
    s, _, _ = user_a
    assert s.get(f"{API}/stats/monthly", params={"month": bad}).status_code == 422


def test_monthly_empty_month(user_a):
    s, _, _ = user_a
    d = s.get(f"{API}/stats/monthly", params={"tz": TZ, "month": "2020-02"}).json()
    assert d["earnings"] == 0 and d["total"] == 0 and d["best_hours"] == [] and d["label"] == "Fevereiro 2020"


# --- privacy / account deletion ---
def test_privacy_public_html():
    r = requests.get(f"{API}/privacy")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "Política de Privacidade" in r.text and "Acessibilidade" in r.text


def test_delete_account_removes_everything():
    s, email, d = _new_user("TEST_Del")
    s.post(f"{API}/simulate")
    s.put(f"{API}/settings", json={"min_fare": 3})
    assert s.delete(f"{API}/auth/account").json() == {"deleted": True}
    assert s.get(f"{API}/auth/me").status_code == 401
    assert requests.post(f"{API}/auth/login", json={"email": email, "password": "testpass123"}).status_code == 401
    from pymongo import MongoClient
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).parent.parent / ".env")
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    uid = d["user"]["id"]
    assert db.rides.count_documents({"user_id": uid}) == 0
    assert db.settings.count_documents({"user_id": uid}) == 0
