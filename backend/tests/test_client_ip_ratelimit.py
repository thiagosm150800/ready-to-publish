# AutoCorrida: client_ip() real-client keying for per-IP rate limits (CF-Connecting-IP / XFF[-3]) - iteration 8
# Public-URL tests verify the real ingress chain; internal (localhost:8001) tests simulate distinct clients,
# because Cloudflare overwrites CF-Connecting-IP / appends XFF so distinct clients can't be faked through the public URL.
import random
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

from test_cpf_admin_apps import API, ADMIN_PASSWORD, APPROVED_CPF, _env, gen_cpf, find_user

INTERNAL = "http://localhost:8001/api"  # only used to simulate headers that Cloudflare would otherwise rewrite
LB_IP = "35.244.139.18"
_mdb = MongoClient(_env("MONGO_URL", "/app/backend/.env"))[_env("DB_NAME", "/app/backend/.env")]
BAD = "12345678900"

A = f"198.51.100.{random.randint(1, 254)}"
B = f"203.0.113.{random.randint(1, 254)}"


def cnt(key):
    since = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    return _mdb.login_attempts.count_documents({"key": key, "at": {"$gte": since}})


def fill(key, n):
    now = datetime.now(timezone.utc)
    _mdb.login_attempts.insert_many([{"key": key, "at": now.isoformat(), "expires_at": now + timedelta(minutes=15), "TEST_": True} for _ in range(n)])


@pytest.fixture(scope="module")
def s():
    ses = requests.Session()
    ses.headers.update({"Content-Type": "application/json"})
    return ses


@pytest.fixture(scope="module")
def keys():
    ks = set()
    yield ks
    for k in ks:
        _mdb.login_attempts.delete_many({"key": k})


@pytest.fixture(scope="module")
def admin_h(s):
    r = s.post(f"{API}/admin/login", json={"password": ADMIN_PASSWORD})
    if r.status_code != 200:
        pytest.skip("admin login failed")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def created(s, admin_h):
    ids = []
    yield ids
    for i in ids:
        s.delete(f"{API}/admin/users/{i}", headers=admin_h)


def _new_key_after_public_malformed(s, headers=None):
    t0 = datetime.now(timezone.utc).isoformat()
    r = s.post(f"{API}/auth/cpf", json={"cpf": BAD}, headers=headers or {})
    assert r.status_code == 422
    d = list(_mdb.login_attempts.find({"key": {"$regex": "^ip:"}, "at": {"$gte": t0}}).sort("at", -1).limit(1))
    assert d, "no ip: attempt recorded"
    return d[0]["key"]


class TestPublicIngressKey:
    def test_key_is_real_client_not_lb(self, s, keys):
        k = _new_key_after_public_malformed(s)
        keys.add(k)
        print("public key:", k)
        assert k != f"ip:{LB_IP}"
        assert not k.startswith("ip:35.244.")

    def test_prepended_xff_and_spoofed_cf_dont_change_key(self, s, keys):
        base = _new_key_after_public_malformed(s)
        keys.add(base)
        k1 = _new_key_after_public_malformed(s, {"X-Forwarded-For": "1.2.3.4, 5.6.7.8, 9.9.9.9"})
        # Cloudflare itself rejects caller-supplied CF-Connecting-IP with 403 (spoof impossible through the edge)
        r = s.post(f"{API}/auth/cpf", json={"cpf": BAD}, headers={"CF-Connecting-IP": "8.8.4.4"})
        assert r.status_code in (403, 422)
        k2 = base if r.status_code == 403 else _new_key_after_public_malformed(s, {"CF-Connecting-IP": "8.8.4.4"})
        assert cnt("ip:8.8.4.4") == 0
        k3 = _new_key_after_public_malformed(s, {"X-Real-IP": "7.7.7.7", "X-Forwarded-For": "6.6.6.6"})
        keys.update({k1, k2, k3})
        print("keys:", base, k1, k2, k3)
        assert k1 == base and k2 == base and k3 == base


class TestSimulatedClients:
    def test_cf_header_separate_malformed_counters(self, s, keys):
        ka, kb = f"ip:{A}", f"ip:{B}"
        keys.update({ka, kb})
        a0, b0 = cnt(ka), cnt(kb)
        r = s.post(f"{INTERNAL}/auth/cpf", json={"cpf": BAD}, headers={"CF-Connecting-IP": A, "X-Forwarded-For": f"{B}, 1.1.1.1, {LB_IP}"})
        assert r.status_code == 422
        assert cnt(ka) == a0 + 1 and cnt(kb) == b0  # CF wins over XFF

    def test_xff_minus3_and_prepended_entries(self, s, keys):
        kb = f"ip:{B}"
        keys.add(kb)
        b0 = cnt(kb)
        for xff in (f"{B}, 172.68.1.1, {LB_IP}", f"6.6.6.6, 7.7.7.7, {B}, 172.68.1.1, {LB_IP}"):
            assert s.post(f"{INTERNAL}/auth/cpf", json={"cpf": BAD}, headers={"X-Forwarded-For": xff}).status_code == 422
        assert cnt(kb) == b0 + 2
        assert cnt("ip:6.6.6.6") == 0 and cnt(f"ip:{LB_IP}") == 0

    def test_malformed_limit_20_is_per_client(self, s, keys):
        ka, kb = f"ip:{A}", f"ip:{B}"
        keys.update({ka, kb})
        fill(ka, max(0, 20 - cnt(ka)))
        assert s.post(f"{INTERNAL}/auth/cpf", json={"cpf": BAD}, headers={"CF-Connecting-IP": A}).status_code == 429
        assert s.post(f"{INTERNAL}/auth/cpf", json={"cpf": BAD}, headers={"CF-Connecting-IP": B}).status_code == 422
        # approved CPF from blocked client A still logs in
        r = s.post(f"{INTERNAL}/auth/cpf", json={"cpf": APPROVED_CPF, "device_id": "test-device-1"}, headers={"CF-Connecting-IP": A})
        assert r.status_code == 200 and r.json()["status"] == "approved"
        # public user (real IP) is not affected by A's lockout
        pub = _new_key_after_public_malformed(s)
        keys.add(pub)

    def test_new_cpf_limit_10_is_per_client(self, s, keys, admin_h, created):
        na, nb = f"new:{A}", f"new:{B}"
        keys.update({na, nb})
        fill(na, max(0, 10 - cnt(na)))
        cpf_a = gen_cpf()
        r = s.post(f"{INTERNAL}/auth/cpf", json={"cpf": cpf_a, "device_id": "test-device-1"}, headers={"X-Forwarded-For": f"9.9.9.9, {A}, 172.68.1.1, {LB_IP}"})
        assert r.status_code == 429
        assert find_user(s, admin_h, cpf_a) is None
        cpf_b = gen_cpf()
        b0 = cnt(nb)
        r = s.post(f"{INTERNAL}/auth/cpf", json={"cpf": cpf_b, "device_id": "test-device-1"}, headers={"X-Forwarded-For": f"{B}, 172.68.1.1, {LB_IP}"})
        assert r.status_code == 200 and r.json() == {"status": "pending"}
        u = find_user(s, admin_h, cpf_b)
        assert u is not None
        created.append(u["id"])
        assert cnt(nb) == b0 + 1
        # public sign-up still works (real IP, not shared LB counter)
        cpf_p = gen_cpf()
        t0 = datetime.now(timezone.utc).isoformat()
        r = s.post(f"{API}/auth/cpf", json={"cpf": cpf_p, "device_id": "test-device-1"})
        assert r.status_code == 200 and r.json() == {"status": "pending"}
        created.append(find_user(s, admin_h, cpf_p)["id"])
        pk = list(_mdb.login_attempts.find({"key": {"$regex": "^new:"}, "at": {"$gte": t0}}).sort("at", -1).limit(1))[0]["key"]
        print("public new key:", pk)
        keys.add(pk)
        assert pk != f"new:{LB_IP}"
