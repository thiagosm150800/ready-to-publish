# RapidoChecker: auto-reject settings (reject_enabled/reject_texts), notify_enabled, master toggle (both apps)
import os
import random
import uuid
from datetime import datetime, timezone
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
def created():
    ids = []
    yield ids
    for uid in ids:
        mdb.users.delete_one({"_id": ObjectId(uid)})
        mdb.rides.delete_many({"user_id": uid})
        mdb.settings.delete_many({"user_id": uid})


def make_driver(created):
    cpf = gen_cpf()
    dev = f"TEST_dev_{uuid.uuid4().hex[:8]}"
    res = mdb.users.insert_one({"cpf": cpf, "name": "TEST_reject", "status": "approved", "device_id": None,
                                "created_at": datetime.now(timezone.utc).isoformat(), "expires_at": None})
    uid = str(res.inserted_id)
    created.append(uid)
    r = requests.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": dev})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved", body
    return uid, {"Authorization": f"Bearer {body['access_token']}"}


@pytest.fixture(scope="module")
def driver(created):
    return make_driver(created)


# --- Defaults ---
def test_defaults_new_settings(driver):
    _, h = driver
    r = requests.get(f"{API}/settings", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert "_id" not in d
    assert d["notify_enabled"] is True
    for k in ("rapido", "moove"):
        assert d["apps"][k]["reject_enabled"] is False
        assert d["apps"][k]["reject_texts"] == ["Recusar"]


def test_defaults_legacy_doc_without_new_fields(created):
    uid, h = make_driver(created)
    legacy_app = {"enabled": True, "min_price_per_km": 3.0, "min_fare": 9.0, "max_pickup_km": 2.0,
                  "accept_texts": ["Aceitar"], "target_package": "x"}
    mdb.settings.insert_one({"user_id": uid, "apps": {"rapido": dict(legacy_app), "moove": dict(legacy_app)},
                             "schedule_enabled": False, "alert_enabled": True})
    d = requests.get(f"{API}/settings", headers=h).json()
    assert d["notify_enabled"] is True
    for k in ("rapido", "moove"):
        assert d["apps"][k]["reject_enabled"] is False
        assert d["apps"][k]["reject_texts"] == ["Recusar"]
        assert d["apps"][k]["min_price_per_km"] == 3.0
    # Old pre-multiapp schema (no "apps")
    uid2, h2 = make_driver(created)
    mdb.settings.insert_one({"user_id": uid2, "min_fare": 11.0, "auto_accept": True})
    d2 = requests.get(f"{API}/settings", headers=h2).json()
    assert d2["apps"]["rapido"]["reject_texts"] == ["Recusar"]
    assert d2["apps"]["rapido"]["min_fare"] == 11.0
    assert d2["notify_enabled"] is True


# --- Reject + notify persistence ---
def test_put_reject_trims_and_persists(driver):
    _, h = driver
    before = requests.get(f"{API}/settings", headers=h).json()
    r = requests.put(f"{API}/settings", headers=h, json={
        "apps": {"moove": {"reject_enabled": True, "reject_texts": [" Recusar ", " ", "Ignorar  "]}},
        "notify_enabled": False})
    assert r.status_code == 200, r.text
    g = requests.get(f"{API}/settings", headers=h).json()
    assert g["apps"]["moove"]["reject_enabled"] is True
    assert g["apps"]["moove"]["reject_texts"] == ["Recusar", "Ignorar"]
    assert g["notify_enabled"] is False
    # untouched fields
    assert g["apps"]["rapido"] == before["apps"]["rapido"]
    for f in ("min_price_per_km", "min_fare", "max_pickup_km", "accept_texts", "enabled", "target_package"):
        assert g["apps"]["moove"][f] == before["apps"]["moove"][f]
    assert g["alert_enabled"] == before["alert_enabled"]
    assert g["schedule_days"] == before["schedule_days"]
    # restore notify
    r = requests.put(f"{API}/settings", headers=h, json={"notify_enabled": True})
    assert r.json()["notify_enabled"] is True


def test_put_reject_invalid_types(driver):
    _, h = driver
    r = requests.put(f"{API}/settings", headers=h, json={"apps": {"moove": {"reject_texts": "Recusar"}}})
    assert r.status_code == 422
    r = requests.put(f"{API}/settings", headers=h, json={"notify_enabled": "maybe"})
    assert r.status_code == 422


# --- Master toggle (both apps in one call) ---
def test_master_toggle_both_on_off(driver):
    _, h = driver
    r = requests.put(f"{API}/settings", headers=h,
                     json={"apps": {"rapido": {"enabled": True}, "moove": {"enabled": True}}})
    assert r.status_code == 200
    g = requests.get(f"{API}/settings", headers=h).json()
    assert g["apps"]["rapido"]["enabled"] is True and g["apps"]["moove"]["enabled"] is True
    assert g["apps"]["moove"]["reject_enabled"] is True  # previous change kept
    r = requests.put(f"{API}/settings", headers=h,
                     json={"apps": {"rapido": {"enabled": False}, "moove": {"enabled": False}}})
    g = requests.get(f"{API}/settings", headers=h).json()
    assert g["apps"]["rapido"]["enabled"] is False and g["apps"]["moove"]["enabled"] is False


def test_settings_requires_auth():
    assert requests.get(f"{API}/settings").status_code in (401, 403)
    assert requests.put(f"{API}/settings", json={"notify_enabled": False}).status_code in (401, 403)
