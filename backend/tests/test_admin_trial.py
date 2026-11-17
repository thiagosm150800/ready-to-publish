# RapidoChecker backend: admin free 1-day trial (once per registration/CPF)
import os
import random
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import jwt
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
JWT_SECRET = _env("JWT_SECRET", "/app/backend/.env")
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


def parse(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    ses.headers.update({"Content-Type": "application/json"})
    return ses


@pytest.fixture(scope="module")
def admin_h():
    now = int(time.time())
    tok = jwt.encode({"sub": "admin", "role": "admin", "iat": now, "exp": now + 3600}, JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def created():
    ids = []
    yield ids
    for uid in ids:
        mdb.users.delete_one({"_id": ObjectId(uid)})


def make_user(created, legacy=False, device_id=None, **extra):
    cpf = gen_cpf()
    doc = {"cpf": cpf, "name": "TEST_trial", "status": "pending", "device_id": device_id,
           "device_bound_at": None, "created_at": datetime.now(timezone.utc).isoformat(), "expires_at": None, **extra}
    if not legacy:
        doc["trial_used"] = False
        doc["trial_at"] = None
    uid = str(mdb.users.insert_one(doc).inserted_id)
    created.append(uid)
    return uid, cpf


# Trial grant on pending user
class TestTrialGrant:
    def test_trial_on_pending(self, s, admin_h, created):
        uid, _ = make_user(created)
        before = datetime.now(timezone.utc)
        r = s.patch(f"{API}/admin/users/{uid}", json={"trial": True}, headers=admin_h)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "approved"
        assert d["trial_used"] is True
        assert d["trial_at"]
        assert d["expired"] is False
        exp = parse(d["expires_at"])
        assert abs((exp - before).total_seconds() - 86400) < 120
        doc = mdb.users.find_one({"_id": ObjectId(uid)})
        assert doc["trial_used"] is True and doc["status"] == "approved" and doc["status_changed_at"]
        assert "_id" not in d

    def test_second_trial_409(self, s, admin_h, created):
        uid, _ = make_user(created)
        assert s.patch(f"{API}/admin/users/{uid}", json={"trial": True}, headers=admin_h).status_code == 200
        r = s.patch(f"{API}/admin/users/{uid}", json={"trial": True}, headers=admin_h)
        assert r.status_code == 409
        assert r.json()["detail"] == "Este cadastro já usou o teste de 1 dia."

    def test_trial_with_days_422(self, s, admin_h, created):
        uid, _ = make_user(created)
        r = s.patch(f"{API}/admin/users/{uid}", json={"trial": True, "access_days": 7}, headers=admin_h)
        assert r.status_code == 422
        doc = mdb.users.find_one({"_id": ObjectId(uid)})
        assert doc["status"] == "pending" and not doc.get("trial_used")

    def test_trial_unknown_404(self, s, admin_h):
        r = s.patch(f"{API}/admin/users/{ObjectId()}", json={"trial": True}, headers=admin_h)
        assert r.status_code == 404
        r = s.patch(f"{API}/admin/users/not-an-id", json={"trial": True}, headers=admin_h)
        assert r.status_code == 404

    def test_trial_false_noop(self, s, admin_h, created):
        uid, _ = make_user(created)
        r = s.patch(f"{API}/admin/users/{uid}", json={"trial": False}, headers=admin_h)
        assert r.status_code == 200
        assert r.json()["status"] == "pending" and r.json()["trial_used"] is False

    def test_trial_requires_admin(self, s, created):
        uid, _ = make_user(created)
        assert s.patch(f"{API}/admin/users/{uid}", json={"trial": True}).status_code in (401, 403)


# Listing legacy users and lifecycle with CPF login
class TestTrialLifecycle:
    def test_legacy_user_trial_used_false(self, s, admin_h, created):
        uid, _ = make_user(created, legacy=True)
        r = s.get(f"{API}/admin/users", params={"status": "pending"}, headers=admin_h)
        assert r.status_code == 200
        u = next(x for x in r.json()["users"] if x["id"] == uid)
        assert u["trial_used"] is False and u["trial_at"] is None
        # legacy user can still get the trial
        r = s.patch(f"{API}/admin/users/{uid}", json={"trial": True}, headers=admin_h)
        assert r.status_code == 200 and r.json()["trial_used"] is True

    def test_trial_login_expire_then_grant7(self, s, admin_h, created):
        dev = "TEST_dev_" + uuid.uuid4().hex[:12]
        uid, cpf = make_user(created, device_id=dev)
        assert s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": dev}).json()["status"] == "pending"
        assert s.patch(f"{API}/admin/users/{uid}", json={"trial": True}, headers=admin_h).status_code == 200
        r = s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": dev})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "approved" and body["access_token"]
        tok = {"Authorization": f"Bearer {body['access_token']}"}
        assert s.get(f"{API}/auth/me", headers=tok).status_code == 200
        # appears in Liberados filter
        lst = s.get(f"{API}/admin/users", params={"status": "approved"}, headers=admin_h).json()["users"]
        assert any(x["id"] == uid for x in lst)
        # simulate expiry
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        mdb.users.update_one({"_id": ObjectId(uid)}, {"$set": {"expires_at": past}})
        assert s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": dev}).json()["status"] == "expired"
        me = s.get(f"{API}/auth/me", headers=tok)
        assert me.status_code in (401, 403), me.text
        lst = s.get(f"{API}/admin/users", params={"status": "expired"}, headers=admin_h).json()["users"]
        u = next(x for x in lst if x["id"] == uid)
        assert u["expired"] is True and u["trial_used"] is True
        # second trial still refused after expiry
        assert s.patch(f"{API}/admin/users/{uid}", json={"trial": True}, headers=admin_h).status_code == 409
        # grant 7 days
        r = s.patch(f"{API}/admin/users/{uid}", json={"access_days": 7}, headers=admin_h)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "approved" and d["expired"] is False and d["trial_used"] is True
        assert abs((parse(d["expires_at"]) - datetime.now(timezone.utc)).total_seconds() - 7 * 86400) < 120
        assert s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": dev}).json()["status"] == "approved"

    def test_no_limit_grant_keeps_trial_flag(self, s, admin_h, created):
        uid, _ = make_user(created)
        s.patch(f"{API}/admin/users/{uid}", json={"trial": True}, headers=admin_h)
        r = s.patch(f"{API}/admin/users/{uid}", json={"access_days": 0}, headers=admin_h)
        assert r.status_code == 200
        assert r.json()["expires_at"] is None and r.json()["trial_used"] is True


# Trial atomicity: concurrent PATCH {trial:true} -> exactly one 200 and the rest 409 (iteration 26)
class TestTrialAtomic:
    def test_concurrent_trial_one_wins(self, admin_h, created):
        from concurrent.futures import ThreadPoolExecutor
        for _ in range(3):
            uid, _ = make_user(created)

            def call(_i):
                return requests.patch(f"{API}/admin/users/{uid}", json={"trial": True}, headers=admin_h, timeout=20).status_code
            with ThreadPoolExecutor(max_workers=4) as ex:
                codes = list(ex.map(call, range(4)))
            assert sorted(codes).count(200) == 1, codes
            assert all(c in (200, 409) for c in codes), codes
            doc = mdb.users.find_one({"_id": ObjectId(uid)})
            assert doc["trial_used"] is True and doc["status"] == "approved"
