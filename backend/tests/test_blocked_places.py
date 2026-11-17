# RapidoChecker: global "Local recusado" filter (blocked_places) — API + Kotlin matching-logic simulation
import os
import random
import re
import unicodedata
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
    res = mdb.users.insert_one({"cpf": cpf, "name": "TEST_blocked", "status": "approved", "device_id": None,
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
def test_default_blocked_places_empty(driver):
    _, h = driver
    r = requests.get(f"{API}/settings", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["blocked_places"] == []
    assert "_id" not in d


def test_legacy_doc_without_blocked_places(created):
    uid, h = make_driver(created)
    requests.get(f"{API}/settings", headers=h)  # creates doc
    mdb.settings.update_one({"user_id": uid}, {"$unset": {"blocked_places": ""}})
    assert "blocked_places" not in mdb.settings.find_one({"user_id": uid})
    r = requests.get(f"{API}/settings", headers=h)
    assert r.status_code == 200
    assert r.json()["blocked_places"] == []


def test_legacy_single_app_doc(created):
    uid, h = make_driver(created)
    mdb.settings.insert_one({"user_id": uid, "min_price_per_km": 2.5, "auto_accept": True})
    r = requests.get(f"{API}/settings", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["blocked_places"] == []


# --- Normalisation on save ---
def test_put_normalizes_and_persists(driver):
    _, h = driver
    before = requests.get(f"{API}/settings", headers=h).json()
    r = requests.put(f"{API}/settings", headers=h,
                     json={"blocked_places": ["  Jardim   Petrópolis ", "jardim petrópolis", "", "   ", "Centro"]})
    assert r.status_code == 200, r.text
    assert r.json()["blocked_places"] == ["Jardim Petrópolis", "Centro"]
    g = requests.get(f"{API}/settings", headers=h).json()
    assert g["blocked_places"] == ["Jardim Petrópolis", "Centro"]
    # other fields untouched
    for k in ("apps", "schedule_enabled", "alert_enabled", "notify_enabled", "exclusive_enabled", "schedule_days"):
        assert g[k] == before[k], k


def test_put_other_field_keeps_places(driver):
    _, h = driver
    r = requests.put(f"{API}/settings", headers=h, json={"alert_enabled": False})
    assert r.status_code == 200
    assert r.json()["blocked_places"] == ["Jardim Petrópolis", "Centro"]
    assert r.json()["alert_enabled"] is False


def test_put_empty_list_clears(driver):
    _, h = driver
    r = requests.put(f"{API}/settings", headers=h, json={"blocked_places": []})
    assert r.status_code == 200
    assert requests.get(f"{API}/settings", headers=h).json()["blocked_places"] == []


# --- Validation ---
def test_entry_too_long_422(driver):
    _, h = driver
    requests.put(f"{API}/settings", headers=h, json={"blocked_places": ["Centro"]})
    r = requests.put(f"{API}/settings", headers=h, json={"blocked_places": ["x" * 81], "alert_enabled": True})
    assert r.status_code == 422
    g = requests.get(f"{API}/settings", headers=h).json()
    assert g["blocked_places"] == ["Centro"]
    assert g["alert_enabled"] is False  # untouched by the rejected request


def test_entry_80_ok(driver):
    _, h = driver
    r = requests.put(f"{API}/settings", headers=h, json={"blocked_places": ["y" * 80]})
    assert r.status_code == 200
    assert r.json()["blocked_places"] == ["y" * 80]


def test_too_many_items_422(driver):
    _, h = driver
    r = requests.put(f"{API}/settings", headers=h, json={"blocked_places": [f"P{i}" for i in range(201)]})
    assert r.status_code == 422
    r2 = requests.put(f"{API}/settings", headers=h, json={"blocked_places": [f"P{i}" for i in range(200)]})
    assert r2.status_code == 200
    assert len(r2.json()["blocked_places"]) == 200


def test_non_string_422(driver):
    _, h = driver
    r = requests.put(f"{API}/settings", headers=h, json={"blocked_places": "Centro"})
    assert r.status_code == 422


def test_requires_auth():
    r = requests.put(f"{API}/settings", json={"blocked_places": ["Centro"]})
    assert r.status_code in (401, 403)


# --- Python port of RideAccessibilityService.blockedPlace()/fold() ---
def fold(s):
    s = unicodedata.normalize("NFD", s)
    s = re.sub(r"[\u0300-\u036f]+", "", s)  # \p{Mn} for latin accents
    return re.sub(r"\s+", " ", s.lower())


def blocked_place(places, offer):
    text = fold(offer)
    for p in places:
        p = p.strip()
        f = fold(p)
        if f and re.search(r"(^|[^\w]|_)" + re.escape(f) + r"($|[^\w]|_)", text):
            return p
    return None


@pytest.mark.parametrize("places,offer,expected", [
    (["Jardim Petropolis"], "R$ 12,50 | 2,1 km | R. José Roberto Janeiro, 4556 - Jardim Petrópolis, Umuarama | 5 km", "Jardim Petropolis"),
    (["centro"], "Av. Brasil - CENTRO | 3 km", "centro"),
    (["Centro"], "Rua X - Centronorte | 3 km", None),
    (["Parque"], "Parque Industrial | 4 km", "Parque"),
    (["Zona 7"], "Zona 70 | 4 km", None),
    (["São Cristóvão"], "Rua A - sao cristovao", "São Cristóvão"),
    ([], "Centro", None),
])
def test_matching_simulation(places, offer, expected):
    assert blocked_place(places, offer) == expected
