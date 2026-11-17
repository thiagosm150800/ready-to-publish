# RapidoChecker: Urbano Norte + 99 apps (settings defaults, legacy merge, PUT partial, rides filter/summary)
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests

from test_blocked_places import API, mdb, gen_cpf, created  # noqa: F401

KEYS = {"rapido", "moove", "urbano"}
DEFAULTS = {"enabled": False, "min_price_per_km": 2.0, "min_fare": 8.0, "max_pickup_km": 4.0,
            "accept_texts": ["Aceitar", "Aceitar corrida", "Accept"], "reject_enabled": False,
            "reject_texts": ["Recusar"], "finish_texts": ["Finalizar", "Encerrar", "Concluir", "Cancelar corrida"]}


def driver(created, name="TEST_4apps"):
    cpf = gen_cpf()
    res = mdb.users.insert_one({"cpf": cpf, "name": name, "status": "approved", "device_id": None,
                                "created_at": datetime.now(timezone.utc).isoformat(), "expires_at": None})
    uid = str(res.inserted_id)
    created.append(uid)
    r = requests.post(f"{API}/auth/cpf", json={"cpf": cpf, "device_id": f"TEST_dev_{uuid.uuid4().hex[:8]}"})
    assert r.status_code == 200, r.text
    return uid, {"Authorization": f"Bearer {r.json()['access_token']}"}


# Settings: new driver gets 4 apps with full defaults
def test_new_driver_has_four_apps(created):
    _, h = driver(created)
    apps = requests.get(f"{API}/settings", headers=h).json()["apps"]
    assert set(apps) == KEYS
    for k in KEYS:
        for f, v in DEFAULTS.items():
            assert apps[k][f] == v, (k, f)
    assert apps["urbano"]["target_package"] == "urbanonorte"
    assert apps["rapido"]["target_package"] == "rapido"
    assert apps["moove"]["target_package"] == "moove"


# Settings: an old doc with only rapido/moove is merged and keeps the driver's values
def test_legacy_two_app_doc_merged(created):
    uid, h = driver(created)
    requests.get(f"{API}/settings", headers=h)
    custom_r = {**DEFAULTS, "enabled": True, "min_fare": 15.5, "target_package": "com.rapido.custom"}
    custom_m = {**DEFAULTS, "reject_enabled": True, "max_pickup_km": 2.5, "target_package": "moove"}
    mdb.settings.update_one({"user_id": uid}, {"$set": {"apps": {"rapido": custom_r, "moove": custom_m},
                                                        "blocked_places": ["Centro"]}})
    s = requests.get(f"{API}/settings", headers=h).json()
    assert set(s["apps"]) == KEYS
    assert s["apps"]["rapido"]["enabled"] is True and s["apps"]["rapido"]["min_fare"] == 15.5
    assert s["apps"]["rapido"]["target_package"] == "com.rapido.custom"
    assert s["apps"]["moove"]["reject_enabled"] is True and s["apps"]["moove"]["max_pickup_km"] == 2.5
    assert s["apps"]["urbano"]["target_package"] == "urbanonorte" and s["apps"]["urbano"]["enabled"] is False
    assert s["blocked_places"] == ["Centro"]
    doc = mdb.settings.find_one({"user_id": uid})
    assert set(doc["apps"]) == KEYS  # persisted


# Settings: very old single-app doc (no "apps") also migrates to 4 keys
def test_legacy_single_app_doc(created):
    uid, h = driver(created)
    mdb.settings.insert_one({"user_id": uid, "auto_accept": True, "min_fare": 11.0})
    s = requests.get(f"{API}/settings", headers=h).json()
    assert set(s["apps"]) == KEYS
    assert s["apps"]["rapido"]["enabled"] is True and s["apps"]["rapido"]["min_fare"] == 11.0


# Settings: PUT for urbano/app99 only changes those fields
def test_put_partial_new_apps(created):
    _, h = driver(created)
    before = requests.get(f"{API}/settings", headers=h).json()
    r = requests.put(f"{API}/settings", headers=h,
                     json={"apps": {"urbano": {"enabled": True, "min_fare": 12}}})
    assert r.status_code == 200, r.text
    after = requests.get(f"{API}/settings", headers=h).json()
    assert after["apps"]["urbano"]["enabled"] is True and after["apps"]["urbano"]["min_fare"] == 12
    assert after["apps"]["urbano"]["min_price_per_km"] == 2.0
    assert after["apps"]["rapido"] == before["apps"]["rapido"]
    assert after["apps"]["moove"] == before["apps"]["moove"]


# Settings: unknown app key rejected; empty target_package rejected for new apps
def test_put_validation(created):
    _, h = driver(created)
    assert requests.put(f"{API}/settings", headers=h, json={"apps": {"uber": {"enabled": True}}}).status_code == 422
    assert requests.put(f"{API}/settings", headers=h,
                        json={"apps": {"urbano": {"target_package": "  "}}}).status_code == 422
    assert requests.put(f"{API}/settings", headers=h,
                        json={"apps": {"urbano": {"reject_texts": [" "]}}}).status_code == 422


# Rides: bulk accepts new apps/sources, filter + summary
def test_rides_new_apps(created):
    _, h = driver(created)
    now = datetime.now(timezone.utc)
    items = [
        {"app": "urbano", "source": "urbanonorte", "price": 20, "trip_km": 5, "accepted": True},
        {"app": "urbano", "source": "urbanonorte", "price": 6, "trip_km": 5, "accepted": False, "reasons": ["x"]},
        {"app": "rapido", "source": "rapidocar", "price": 10, "trip_km": 4, "accepted": True},
    ]
    r = requests.post(f"{API}/rides/bulk", headers=h, json=items)
    assert r.status_code == 200 and r.json()["inserted"] == 3
    u = requests.get(f"{API}/rides", headers=h, params={"app": "urbano"}).json()
    assert len(u) == 2 and all(x["app"] == "urbano" and x["source"] == "urbanonorte" for x in u)
    assert requests.get(f"{API}/rides", headers=h, params={"app": "app99"}).status_code == 422
    acc = requests.get(f"{API}/rides", headers=h, params={"app": "urbano", "status": "accepted"}).json()
    assert len(acc) == 1
    since = (now - timedelta(hours=1)).isoformat()
    s = requests.get(f"{API}/rides/summary", headers=h, params={"since": since}).json()
    assert set(s) == KEYS
    assert s["urbano"] == {"accepted": 1, "rejected": 1, "earned": 20.0}
    assert s["moove"] == {"accepted": 0, "rejected": 0, "earned": 0.0}
    assert requests.get(f"{API}/rides", headers=h, params={"app": "uber"}).status_code == 422
    bad = requests.post(f"{API}/rides/bulk", headers=h,
                        json=[{"app": "app99", "source": "99app", "price": 1, "trip_km": 1, "accepted": True}])
    assert bad.status_code == 422
