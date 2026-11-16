# AutoCorrida backend: CPF auth, admin approval, per-app settings (rapido/moove), rides, removed endpoints
import os
import random
import uuid
import pytest
import requests
from pathlib import Path


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
APPROVED_CPF = "529.982.247-25"


def gen_cpf():
    d = [random.randint(0, 9) for _ in range(9)]
    for n in (9, 10):
        s = sum(d[i] * (n + 1 - i) for i in range(n))
        d.append((s * 10) % 11 % 10)
    c = "".join(map(str, d))
    return c if c != c[0] * 11 else gen_cpf()


def fake_ip():
    return f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


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
def driver_h(s):
    r = s.post(f"{API}/auth/cpf", json={"cpf": APPROVED_CPF, "device_id": "test-device-1"})
    if r.status_code != 200 or r.json().get("status") != "approved":
        pytest.skip(f"driver login failed {r.status_code} {r.text}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def created_ids():
    ids = []
    yield ids
    ses = requests.Session()
    r = ses.post(f"{API}/admin/login", json={"password": ADMIN_PASSWORD})
    if r.status_code == 200:
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        for i in ids:
            ses.delete(f"{API}/admin/users/{i}", headers=h)


@pytest.fixture(scope="module")
def temp_driver(s, admin_h, created_ids):
    cpf = gen_cpf()
    s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": "test-device-1"})
    u = find_user(s, admin_h, cpf)
    created_ids.append(u["id"])
    s.patch(f"{API}/admin/users/{u['id']}", json={"status": "approved", "name": "TEST_temp"}, headers=admin_h)
    tok = s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": "test-device-1"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def find_user(s, admin_h, cpf_digits):
    masked = f"{cpf_digits[:3]}.{cpf_digits[3:6]}.{cpf_digits[6:9]}-{cpf_digits[9:]}"
    users = s.get(f"{API}/admin/users?status=all", headers=admin_h).json()["users"]
    return next((u for u in users if u["cpf"] == masked), None)


# ---- CPF auth ----
class TestCpfAuth:
    def test_invalid_cpf_422(self, s):
        r = s.post(f"{API}/auth/cpf", json={"cpf": "123.456.789-00"}, headers={"X-Forwarded-For": fake_ip()})
        assert r.status_code == 422

    def test_repeated_digits_422(self, s):
        r = s.post(f"{API}/auth/cpf", json={"cpf": "11111111111"}, headers={"X-Forwarded-For": fake_ip()})
        assert r.status_code == 422

    def test_new_cpf_pending_then_approve_block_delete(self, s, admin_h, created_ids):
        cpf = gen_cpf()
        r = s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": "test-device-1"})
        assert r.status_code == 200 and r.json() == {"status": "pending"}
        u = find_user(s, admin_h, cpf)
        assert u and u["status"] == "pending"
        created_ids.append(u["id"])
        # pending list contains it
        pend = s.get(f"{API}/admin/users?status=pending", headers=admin_h).json()
        assert any(x["id"] == u["id"] for x in pend["users"])
        assert set(pend["counts"]) == {"pending", "approved", "expired", "blocked"}
        assert all(x["status"] == "pending" for x in pend["users"])
        # second login still pending, no token
        r = s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": "test-device-1"})
        assert r.json() == {"status": "pending"}
        # approve + name
        r = s.patch(f"{API}/admin/users/{u['id']}", json={"status": "approved", "name": " TEST_Motorista "}, headers=admin_h)
        assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["name"] == "TEST_Motorista"
        r = s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": "test-device-1"})
        d = r.json()
        assert d["status"] == "approved" and d["access_token"]
        assert d["user"]["cpf"].count(".") == 2 and "-" in d["user"]["cpf"] and d["user"]["name"] == "TEST_Motorista"
        h = {"Authorization": f"Bearer {d['access_token']}"}
        assert s.get(f"{API}/settings", headers=h).status_code == 200
        # driver token rejected on admin routes
        assert s.get(f"{API}/admin/users", headers=h).status_code == 401
        # block -> existing token 401
        assert s.patch(f"{API}/admin/users/{u['id']}", json={"status": "blocked"}, headers=admin_h).status_code == 200
        assert s.get(f"{API}/settings", headers=h).status_code == 401
        r = s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": "test-device-1"})
        assert r.json() == {"status": "blocked"}
        # delete -> 404 afterwards
        assert s.delete(f"{API}/admin/users/{u['id']}", headers=admin_h).json() == {"deleted": True}
        assert find_user(s, admin_h, cpf) is None
        assert s.delete(f"{API}/admin/users/{u['id']}", headers=admin_h).status_code == 404
        created_ids.remove(u["id"])


# ---- Admin ----
class TestAdmin:
    def test_wrong_password_401(self, s):
        r = s.post(f"{API}/admin/login", json={"password": "wrong"}, headers={"X-Forwarded-For": fake_ip()})
        assert r.status_code == 401

    def test_admin_requires_token(self, s):
        assert s.get(f"{API}/admin/users").status_code == 401

    def test_admin_token_rejected_on_driver_routes(self, s, admin_h):
        assert s.get(f"{API}/settings", headers=admin_h).status_code == 401
        assert s.get(f"{API}/rides", headers=admin_h).status_code == 401

    def test_list_filters(self, s, admin_h):
        for st in ("pending", "approved", "expired", "blocked", "all"):
            r = s.get(f"{API}/admin/users?status={st}", headers=admin_h)
            assert r.status_code == 200 and "users" in r.json() and "counts" in r.json()
        assert s.get(f"{API}/admin/users?status=xx", headers=admin_h).status_code == 422

    def test_patch_unknown_404(self, s, admin_h):
        assert s.patch(f"{API}/admin/users/507f1f77bcf86cd799439011", json={"status": "approved"}, headers=admin_h).status_code == 404
        assert s.patch(f"{API}/admin/users/bad", json={"status": "approved"}, headers=admin_h).status_code == 404
        assert s.patch(f"{API}/admin/users/507f1f77bcf86cd799439011", json={"status": "foo"}, headers=admin_h).status_code == 422


# ---- Settings per app & rides ----
class TestSettingsRides:
    def test_settings_shape(self, s, driver_h):
        d = s.get(f"{API}/settings", headers=driver_h).json()
        for app in ("rapido", "moove"):
            for k in ("enabled", "min_price_per_km", "min_fare", "max_pickup_km", "accept_texts", "target_package"):
                assert k in d["apps"][app]
        for k in ("schedule_enabled", "schedule_start", "schedule_end", "schedule_days", "alert_enabled"):
            assert k in d
        assert "_id" not in d and "user_id" not in d

    def test_put_only_moove(self, s, driver_h):
        before = s.get(f"{API}/settings", headers=driver_h).json()
        r = s.put(f"{API}/settings", json={"apps": {"moove": {"min_fare": 12}}}, headers=driver_h)
        assert r.status_code == 200
        after = s.get(f"{API}/settings", headers=driver_h).json()
        assert after["apps"]["moove"]["min_fare"] == 12
        assert after["apps"]["rapido"] == before["apps"]["rapido"]
        # restore
        s.put(f"{API}/settings", json={"apps": {"moove": {"min_fare": before["apps"]["moove"]["min_fare"]}}}, headers=driver_h)

    def test_put_validation(self, s, driver_h):
        assert s.put(f"{API}/settings", json={"apps": {"uber": {"min_fare": 1}}}, headers=driver_h).status_code == 422
        assert s.put(f"{API}/settings", json={"apps": {"moove": {"min_fare": -1}}}, headers=driver_h).status_code == 422
        assert s.put(f"{API}/settings", json={"schedule_start": "25:00"}, headers=driver_h).status_code == 422

    def test_rides_bulk_and_filter(self, s, temp_driver):
        driver_h = temp_driver
        tag = f"TEST_{uuid.uuid4().hex[:6]}"
        items = [{"app": "moove", "price": 33.3, "trip_km": 10, "accepted": True, "reasons": [tag], "source": "moovecar"},
                 {"app": "rapido", "price": 11.1, "trip_km": 5, "accepted": False, "reasons": [tag]}]
        r = s.post(f"{API}/rides/bulk", json=items, headers=driver_h)
        assert r.json() == {"inserted": 2}
        mv = s.get(f"{API}/rides?app=moove", headers=driver_h).json()
        assert all(x["app"] == "moove" for x in mv)
        m = next(x for x in mv if tag in x["reasons"])
        assert m["price_per_km"] == 3.33
        rj = s.get(f"{API}/rides?app=rapido&status=rejected", headers=driver_h).json()
        assert any(tag in x["reasons"] for x in rj) and all(x["app"] == "rapido" and not x["accepted"] for x in rj)
        assert s.get(f"{API}/rides?app=99", headers=driver_h).status_code == 422
        assert s.post(f"{API}/rides/bulk", json=[{"app": "99", "price": 1, "trip_km": 1, "accepted": True}], headers=driver_h).status_code == 422


# ---- Removed endpoints ----
@pytest.mark.parametrize("method,path", [("post", "/simulate"), ("get", "/stats"), ("get", "/stats/weekly"),
                                         ("get", "/stats/monthly"), ("post", "/auth/login"), ("post", "/auth/register")])
def test_removed_endpoints(s, method, path):
    r = getattr(s, method)(f"{API}{path}", json={})
    assert r.status_code in (404, 405)


# ---- Rate limits (run LAST; they share the real client-IP key and the global admin key) ----
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient

_mdb = MongoClient(_env("MONGO_URL", "/app/backend/.env"))[_env("DB_NAME", "/app/backend/.env")]


def _window_count(key):
    since = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    return _mdb.login_attempts.count_documents({"key": key, "at": {"$gte": since}})


def _latest_key(prefix):
    d = _mdb.login_attempts.find({"key": {"$regex": f"^{prefix}"}}).sort("at", -1).limit(1)
    return next(iter(d))["key"]


@pytest.fixture(scope="module")
def rl_keys():
    keys = set()
    yield keys
    for k in keys:  # clean every key we touched so the preview is not locked
        _mdb.login_attempts.delete_many({"key": k})


class TestZRateLimits:
    def test_spoofed_xff_same_counter(self, s, rl_keys):
        s.post(f"{API}/auth/cpf", json={"cpf": "12345678900"})
        key = _latest_key("ip:")
        rl_keys.add(key)
        before = _window_count(key)
        for _ in range(3):
            r = s.post(f"{API}/auth/cpf", json={"cpf": "12345678900"},
                       headers={"X-Forwarded-For": fake_ip(), "X-Real-IP": fake_ip()})
            assert r.status_code == 422
        assert _window_count(key) == before + 3
        assert not _mdb.login_attempts.find_one({"key": {"$regex": r"^ip:10\."}, "at": {"$gte": datetime.now(timezone.utc).isoformat()[:16]}})

    def test_pending_rechecks_not_counted(self, s, admin_h, created_ids, rl_keys):
        cpf = gen_cpf()
        assert s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": "test-device-1"}).json() == {"status": "pending"}
        rl_keys.add(_latest_key("new:"))
        u = find_user(s, admin_h, cpf)
        created_ids.append(u["id"])
        ip_key = next(k for k in rl_keys if k.startswith("ip:"))
        before = _window_count(ip_key)
        res = [s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": "test-device-1"}).json() for _ in range(25)]
        assert all(x == {"status": "pending"} for x in res)
        assert _window_count(ip_key) == before
        r = s.post(f"{API}/auth/cpf", json={"cpf": APPROVED_CPF, "device_id": "test-device-1"})
        assert r.status_code == 200 and r.json()["status"] == "approved"

    def test_malformed_limit_20_then_429_approved_still_ok(self, s, rl_keys):
        ip_key = next(k for k in rl_keys if k.startswith("ip:"))
        remaining = max(0, 20 - _window_count(ip_key))
        codes = [s.post(f"{API}/auth/cpf", json={"cpf": "12345678900"}, headers={"X-Forwarded-For": fake_ip()}).status_code
                 for _ in range(remaining)]
        assert codes == [422] * remaining
        assert s.post(f"{API}/auth/cpf", json={"cpf": "12345678900"}, headers={"X-Forwarded-For": fake_ip()}).status_code == 429
        r = s.post(f"{API}/auth/cpf", json={"cpf": APPROVED_CPF, "device_id": "test-device-1"})
        assert r.status_code == 200 and r.json()["status"] == "approved"

    def test_new_cpf_limit_10(self, s, admin_h, created_ids, rl_keys):
        new_key = next(k for k in rl_keys if k.startswith("new:"))
        remaining = max(0, 10 - _window_count(new_key))
        for _ in range(remaining):
            cpf = gen_cpf()
            r = s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": "test-device-1"}, headers={"X-Forwarded-For": fake_ip()})
            assert r.status_code == 200 and r.json() == {"status": "pending"}
            created_ids.append(find_user(s, admin_h, cpf)["id"])
        cpf = gen_cpf()
        r = s.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": "test-device-1"}, headers={"X-Forwarded-For": fake_ip()})
        assert r.status_code == 429
        assert find_user(s, admin_h, cpf) is None
        # existing approved CPF unaffected
        assert s.post(f"{API}/auth/cpf", json={"cpf": APPROVED_CPF, "device_id": "test-device-1"}).json()["status"] == "approved"

    def test_admin_global_limit_10(self, s, created_ids):
        # ensure teardown of created_ids can still log in: obtain token first by touching fixture order
        try:
            _mdb.login_attempts.delete_many({"key": "admin:global"})
            codes = [s.post(f"{API}/admin/login", json={"password": "bad"},
                            headers={"X-Forwarded-For": fake_ip(), "X-Real-IP": fake_ip()}).status_code for _ in range(11)]
            assert codes[:10] == [401] * 10 and codes[10] == 429
            # even the correct password is locked out while the global counter is full
            assert s.post(f"{API}/admin/login", json={"password": ADMIN_PASSWORD}).status_code == 429
        finally:
            _mdb.login_attempts.delete_many({"key": "admin:global"})
        assert s.post(f"{API}/admin/login", json={"password": ADMIN_PASSWORD}).status_code == 200
