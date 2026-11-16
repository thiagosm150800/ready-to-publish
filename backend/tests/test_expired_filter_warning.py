# AutoCorrida backend iteration 10: admin 'expired' filter/count, approved excludes expired, /auth/me expires_at
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


def iso(delta):
    return (datetime.now(timezone.utc) + delta).isoformat()


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
def users():
    """Seed TEST_ users of each kind; delete by id afterwards."""
    specs = {
        "pending": ("pending", None, True),
        "blocked": ("blocked", None, True),
        "nolimit": ("approved", None, True),
        "nofield": ("approved", None, False),  # expires_at key missing entirely
        "future": ("approved", iso(timedelta(days=10)), True),
        "soon": ("approved", iso(timedelta(days=2)), True),
        "expired": ("approved", iso(-timedelta(hours=5)), True),
        "expired_old": ("approved", iso(-timedelta(days=20)), True),
        "blocked_past": ("blocked", iso(-timedelta(days=3)), True),
    }
    out = {}
    for k, (status, exp, with_field) in specs.items():
        cpf = gen_cpf()
        doc = {"cpf": cpf, "name": f"TEST_it10_{k}", "status": status,
               "created_at": datetime.now(timezone.utc).isoformat()}
        if with_field:
            doc["expires_at"] = exp
        out[k] = {"id": str(mdb.users.insert_one(doc).inserted_id), "cpf": cpf}
    yield out
    for v in out.values():
        mdb.users.delete_one({"_id": ObjectId(v["id"])})
        mdb.rides.delete_many({"user_id": v["id"]})
        mdb.settings.delete_many({"user_id": v["id"]})


def ids_for(s, h, status):
    r = s.get(f"{API}/admin/users", params={"status": status}, headers=h)
    assert r.status_code == 200, r.text
    return r.json(), {u["id"] for u in r.json()["users"]}


class TestExpiredFilter:
    def test_counts_keys(self, s, admin_h, users):
        data, _ = ids_for(s, admin_h, "all")
        assert set(data["counts"].keys()) == {"pending", "approved", "expired", "blocked"}
        assert all(isinstance(v, int) for v in data["counts"].values())

    def test_expired_filter_only_expired(self, s, admin_h, users):
        data, got = ids_for(s, admin_h, "expired")
        assert users["expired"]["id"] in got and users["expired_old"]["id"] in got
        for k in ("pending", "blocked", "nolimit", "nofield", "future", "soon", "blocked_past"):
            assert users[k]["id"] not in got, k
        now = datetime.now(timezone.utc).isoformat()
        for u in data["users"]:
            assert u["status"] == "approved" and u["expired"] is True and u["expires_at"] <= now
        assert data["counts"]["expired"] == len(data["users"])

    def test_expired_sorted_desc(self, s, admin_h, users):
        data, _ = ids_for(s, admin_h, "expired")
        exps = [u["expires_at"] for u in data["users"]]
        assert exps == sorted(exps, reverse=True)

    def test_approved_excludes_expired(self, s, admin_h, users):
        data, got = ids_for(s, admin_h, "approved")
        for k in ("nolimit", "nofield", "future", "soon"):
            assert users[k]["id"] in got, k
        for k in ("expired", "expired_old", "pending", "blocked", "blocked_past"):
            assert users[k]["id"] not in got, k
        assert all(u["expired"] is False and u["status"] == "approved" for u in data["users"])
        assert data["counts"]["approved"] == len(data["users"])

    def test_pending_blocked_counts_match(self, s, admin_h, users):
        for st in ("pending", "blocked"):
            data, got = ids_for(s, admin_h, st)
            assert data["counts"][st] == len(data["users"])
            assert all(u["status"] == st for u in data["users"])
        _, blocked = ids_for(s, admin_h, "blocked")
        assert users["blocked_past"]["id"] in blocked

    def test_all_sum_equals_counts(self, s, admin_h, users):
        data, got = ids_for(s, admin_h, "all")
        assert sum(data["counts"].values()) == len(data["users"])
        assert all(v["id"] in got for v in users.values())

    def test_invalid_status_422(self, s, admin_h):
        r = s.get(f"{API}/admin/users", params={"status": "foo"}, headers=admin_h)
        assert r.status_code == 422

    def test_no_auth_401(self, s):
        r = s.get(f"{API}/admin/users", params={"status": "expired"})
        assert r.status_code == 401

    def test_renew_expired_moves_to_approved(self, s, admin_h, users):
        uid = users["expired"]["id"]
        r = s.patch(f"{API}/admin/users/{uid}", json={"access_days": 7}, headers=admin_h)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "approved" and body["expired"] is False
        exp = datetime.fromisoformat(body["expires_at"])
        assert timedelta(days=6, hours=23) < exp - datetime.now(timezone.utc) <= timedelta(days=7)
        _, exp_ids = ids_for(s, admin_h, "expired")
        _, app_ids = ids_for(s, admin_h, "approved")
        assert uid not in exp_ids and uid in app_ids

    def test_renew_no_limit_from_expired(self, s, admin_h, users):
        uid = users["expired_old"]["id"]
        r = s.patch(f"{API}/admin/users/{uid}", json={"access_days": 0}, headers=admin_h)
        assert r.status_code == 200 and r.json()["expires_at"] is None and r.json()["expired"] is False
        _, app_ids = ids_for(s, admin_h, "approved")
        assert uid in app_ids


class TestMeExpiresAt:
    def test_me_returns_future_expires_at(self, s, users):
        r = s.post(f"{API}/auth/cpf", json={"cpf": users["soon"]["cpf"], "device_id": "test-device-1"})
        assert r.status_code == 200 and r.json()["status"] == "approved"
        tok = r.json()["access_token"]
        me = s.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert me.status_code == 200
        exp = datetime.fromisoformat(me.json()["expires_at"])
        left = exp - datetime.now(timezone.utc)
        assert timedelta(days=1) < left < timedelta(days=3)

    def test_me_nolimit_null(self, s, users):
        r = s.post(f"{API}/auth/cpf", json={"cpf": users["nolimit"]["cpf"], "device_id": "test-device-1"})
        tok = r.json()["access_token"]
        me = s.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"})
        assert me.status_code == 200 and me.json()["expires_at"] is None

    def test_expired_login_status(self, s, users):
        # expired_old was renewed above; use a fresh expired user
        cpf = gen_cpf()
        uid = str(mdb.users.insert_one({"cpf": cpf, "name": "TEST_it10_exp2", "status": "approved",
                                        "created_at": iso(timedelta()), "expires_at": iso(-timedelta(minutes=1))}).inserted_id)
        users["exp2"] = {"id": uid, "cpf": cpf}
        r = s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": "test-device-1"})
        assert r.status_code == 200 and r.json() == {"status": "expired"}
