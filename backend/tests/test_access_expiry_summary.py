# AutoCorrida backend: admin access periods (access_days), access expiry, today summary per app
import os
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import requests
from bson import ObjectId
from pymongo import MongoClient


def _env(key, path):
    v = os.environ.get(key)
    if v:
        return v
    for line in Path(path).read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError(f"{key} missing")


BASE_URL = _env("EXPO_PUBLIC_BACKEND_URL", "/app/frontend/.env").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_PASSWORD = _env("ADMIN_PASSWORD", "/app/backend/.env")
mdb = MongoClient(_env("MONGO_URL", "/app/backend/.env"))[_env("DB_NAME", "/app/backend/.env")]


def gen_cpf():
    d = [random.randint(0, 9) for _ in range(9)]
    for n in (9, 10):
        s = sum(d[i] * (n + 1 - i) for i in range(n))
        d.append((s * 10) % 11 % 10)
    c = "".join(map(str, d))
    if c == c[0] * 11 or mdb.users.find_one({"cpf": c}):
        return gen_cpf()
    return c


@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    ses.headers.update({"Content-Type": "application/json"})
    return ses


@pytest.fixture(scope="module")
def admin_h(s):
    r = s.post(f"{API}/admin/login", json={"password": ADMIN_PASSWORD})
    if r.status_code != 200:
        pytest.skip(f"admin login failed {r.status_code} {r.text}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def created():
    ids = []
    yield ids
    for uid in ids:
        mdb.users.delete_one({"_id": ObjectId(uid)})
        mdb.rides.delete_many({"user_id": uid})
        mdb.settings.delete_many({"user_id": uid})


def make_user(created, status="pending"):
    cpf = gen_cpf()
    res = mdb.users.insert_one({"cpf": cpf, "name": "TEST_expiry", "status": status,
                                "created_at": datetime.now(timezone.utc).isoformat(), "expires_at": None})
    uid = str(res.inserted_id)
    created.append(uid)
    return uid, cpf


def login(s, cpf):
    return s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": "test-device-1"})


# --- access_days grant ---
class TestAccessDays:
    @pytest.mark.parametrize("days", [7, 15, 30])
    def test_grant_days_sets_approved_and_expiry(self, s, admin_h, created, days):
        uid, cpf = make_user(created)
        before = datetime.now(timezone.utc)
        r = s.patch(f"{API}/admin/users/{uid}", json={"access_days": days}, headers=admin_h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "approved"
        assert d["expired"] is False
        exp = datetime.fromisoformat(d["expires_at"])
        delta = exp - before
        assert timedelta(days=days) - timedelta(minutes=2) < delta < timedelta(days=days) + timedelta(minutes=2)
        # persisted
        doc = mdb.users.find_one({"_id": ObjectId(uid)})
        assert doc["status"] == "approved" and doc["expires_at"] == d["expires_at"]
        assert doc.get("status_changed_at")
        # login works
        lr = login(s, cpf).json()
        assert lr["status"] == "approved" and lr["user"]["expires_at"] == d["expires_at"]

    def test_grant_zero_no_limit(self, s, admin_h, created):
        uid, cpf = make_user(created)
        s.patch(f"{API}/admin/users/{uid}", json={"access_days": 7}, headers=admin_h)
        r = s.patch(f"{API}/admin/users/{uid}", json={"access_days": 0}, headers=admin_h)
        assert r.status_code == 200
        assert r.json()["status"] == "approved" and r.json()["expires_at"] is None
        assert mdb.users.find_one({"_id": ObjectId(uid)})["expires_at"] is None

    def test_grant_blocked_user_reapproves(self, s, admin_h, created):
        uid, cpf = make_user(created, status="blocked")
        r = s.patch(f"{API}/admin/users/{uid}", json={"access_days": 15}, headers=admin_h)
        assert r.json()["status"] == "approved" and r.json()["expires_at"]

    @pytest.mark.parametrize("bad", [-1, 3651, "abc"])
    def test_invalid_access_days_422(self, s, admin_h, created, bad):
        uid, _ = make_user(created)
        r = s.patch(f"{API}/admin/users/{uid}", json={"access_days": bad}, headers=admin_h)
        assert r.status_code == 422

    def test_access_days_requires_admin(self, s, created):
        uid, _ = make_user(created)
        r = s.patch(f"{API}/admin/users/{uid}", json={"access_days": 7})
        assert r.status_code == 401


# --- expiry ---
class TestExpiry:
    def test_expired_login_and_token_revoked(self, s, admin_h, created):
        uid, cpf = make_user(created)
        s.patch(f"{API}/admin/users/{uid}", json={"access_days": 7}, headers=admin_h)
        tok = login(s, cpf).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        assert s.get(f"{API}/auth/me", headers=h).status_code == 200
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        mdb.users.update_one({"_id": ObjectId(uid)}, {"$set": {"expires_at": past}})
        r = login(s, cpf)
        assert r.status_code == 200 and r.json() == {"status": "expired"}
        me = s.get(f"{API}/auth/me", headers=h)
        assert me.status_code == 401
        assert "prazo" in me.json()["detail"].lower()
        assert s.get(f"{API}/settings", headers=h).status_code == 401
        # admin view
        lst = s.get(f"{API}/admin/users?status=all", headers=admin_h).json()["users"]
        u = next(x for x in lst if x["id"] == uid)
        assert u["expired"] is True and u["status"] == "approved"
        # renew -> works again
        r2 = s.patch(f"{API}/admin/users/{uid}", json={"access_days": 30}, headers=admin_h)
        assert r2.json()["expired"] is False
        assert login(s, cpf).json()["status"] == "approved"
        assert s.get(f"{API}/auth/me", headers=h).status_code == 200

    def test_block_still_works_and_delete(self, s, admin_h, created):
        uid, cpf = make_user(created)
        s.patch(f"{API}/admin/users/{uid}", json={"access_days": 7}, headers=admin_h)
        r = s.patch(f"{API}/admin/users/{uid}", json={"status": "blocked"}, headers=admin_h)
        assert r.json()["status"] == "blocked"
        assert login(s, cpf).json() == {"status": "blocked"}
        d = s.delete(f"{API}/admin/users/{uid}", headers=admin_h)
        assert d.status_code == 200 and d.json()["deleted"] is True
        assert mdb.users.find_one({"_id": ObjectId(uid)}) is None


# --- today summary ---
class TestSummary:
    def test_summary_counts_since_and_isolation(self, s, admin_h, created):
        ua, cpfa = make_user(created)
        ub, cpfb = make_user(created)
        for u in (ua, ub):
            s.patch(f"{API}/admin/users/{u}", json={"access_days": 0}, headers=admin_h)
        ha = {"Authorization": f"Bearer {login(s, cpfa).json()['access_token']}"}
        hb = {"Authorization": f"Bearer {login(s, cpfb).json()['access_token']}"}
        now = datetime.now(timezone.utc)
        since = (now - timedelta(hours=2)).isoformat()
        old = (now - timedelta(hours=5)).isoformat()
        recent = (now - timedelta(minutes=30)).isoformat()
        rides = [
            {"app": "rapido", "price": 10, "trip_km": 4, "accepted": True, "created_at": recent},
            {"app": "rapido", "price": 15.5, "trip_km": 5, "accepted": True, "created_at": recent},
            {"app": "rapido", "price": 5, "trip_km": 5, "accepted": False, "created_at": recent},
            {"app": "moove", "price": 20, "trip_km": 6, "accepted": True, "source": "moovecar", "created_at": recent},
            {"app": "moove", "price": 3, "trip_km": 6, "accepted": False, "source": "moovecar"},
            {"app": "moove", "price": 4, "trip_km": 6, "accepted": False, "source": "moovecar"},
            {"app": "rapido", "price": 99, "trip_km": 4, "accepted": True, "created_at": old},
            {"app": "moove", "price": 99, "trip_km": 4, "accepted": False, "created_at": old},
        ]
        assert s.post(f"{API}/rides/bulk", json=rides, headers=ha).json()["inserted"] == 8
        s.post(f"{API}/rides/bulk", json=[{"app": "rapido", "price": 50, "trip_km": 4, "accepted": True}], headers=hb)
        r = s.get(f"{API}/rides/summary", params={"since": since}, headers=ha)
        assert r.status_code == 200, r.text
        assert r.json() == {"rapido": {"accepted": 2, "rejected": 1, "earned": 25.5},
                            "moove": {"accepted": 1, "rejected": 2, "earned": 20.0}, "urbano": {"accepted": 0, "rejected": 0, "earned": 0.0},
                            "log": {"accepted": 0, "rejected": 0, "earned": 0.0}}
        # local midnight with offset (e.g. -03:00) is accepted
        local = (now - timedelta(hours=1)).astimezone(timezone(timedelta(hours=-3))).isoformat()
        r2 = s.get(f"{API}/rides/summary", params={"since": local}, headers=ha).json()
        assert r2["rapido"]["accepted"] == 2 and r2["moove"]["rejected"] == 2
        # "Z" suffix form (what JS toISOString sends)
        z = (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        assert s.get(f"{API}/rides/summary", params={"since": z}, headers=ha).json()["rapido"]["accepted"] == 2
        # other user isolated
        rb = s.get(f"{API}/rides/summary", params={"since": since}, headers=hb).json()
        assert rb == {"rapido": {"accepted": 1, "rejected": 0, "earned": 50.0}, "moove": {"accepted": 0, "rejected": 0, "earned": 0.0}, "urbano": {"accepted": 0, "rejected": 0, "earned": 0.0},
                            "log": {"accepted": 0, "rejected": 0, "earned": 0.0}}

    def test_summary_validation_and_auth(self, s, admin_h, created):
        uid, cpf = make_user(created)
        s.patch(f"{API}/admin/users/{uid}", json={"access_days": 0}, headers=admin_h)
        h = {"Authorization": f"Bearer {login(s, cpf).json()['access_token']}"}
        assert s.get(f"{API}/rides/summary", params={"since": "garbage"}, headers=h).status_code == 422
        assert s.get(f"{API}/rides/summary", headers=h).status_code == 422
        assert s.get(f"{API}/rides/summary", params={"since": "2026-01-01T00:00:00Z"}).status_code == 401
        empty = s.get(f"{API}/rides/summary", params={"since": "2026-01-01T00:00:00Z"}, headers=h).json()
        assert empty["rapido"] == {"accepted": 0, "rejected": 0, "earned": 0.0}
