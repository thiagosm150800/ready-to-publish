# RapidoChecker iteration 29: LOG Urbano ('log') app — settings defaults/legacy merge, PUT, rides bulk/filter/summary
from datetime import datetime, timezone, timedelta

import requests

from test_blocked_places import API, mdb, created  # noqa: F401
from test_four_apps import driver, DEFAULTS, KEYS


# Settings: new driver gets 'log' with full RapidoCar-identical defaults and target 'logurbano'
def test_new_driver_log_defaults(created):
    _, h = driver(created, "TEST_log_new")
    s = requests.get(f"{API}/settings", headers=h).json()
    log, rap = s["apps"]["log"], s["apps"]["rapido"]
    assert log["target_package"] == "logurbano"
    assert set(log) == set(rap)  # exactly the same fields as RapidoCar
    for f, v in DEFAULTS.items():
        assert log[f] == v, f


# Settings: legacy 3-app doc (rapido/moove/urbano) gets 'log' auto-added and persisted; others untouched
def test_legacy_three_app_doc_gets_log(created):
    uid, h = driver(created, "TEST_log_legacy")
    requests.get(f"{API}/settings", headers=h)
    doc = mdb.settings.find_one({"user_id": uid})
    apps = doc["apps"]
    apps.pop("log")
    apps["urbano"]["min_fare"] = 33.0
    mdb.settings.update_one({"user_id": uid}, {"$set": {"apps": apps}})
    s = requests.get(f"{API}/settings", headers=h).json()
    assert set(s["apps"]) == KEYS
    assert s["apps"]["log"]["target_package"] == "logurbano" and s["apps"]["log"]["enabled"] is False
    assert s["apps"]["urbano"]["min_fare"] == 33.0
    assert "log" in mdb.settings.find_one({"user_id": uid})["apps"]


# Settings: legacy doc with app99 AND missing log -> app99 removed + log added in one go
def test_legacy_app99_and_missing_log(created):
    uid, h = driver(created, "TEST_log_mixed")
    requests.get(f"{API}/settings", headers=h)
    mdb.settings.update_one({"user_id": uid}, {"$unset": {"apps.log": ""},
                                               "$set": {"apps.app99": {**DEFAULTS, "target_package": "99app"}}})
    s = requests.get(f"{API}/settings", headers=h).json()
    assert set(s["apps"]) == KEYS
    d = mdb.settings.find_one({"user_id": uid})["apps"]
    assert "app99" not in d and "log" in d


# Settings: PUT apps.log updates every field, persists, leaves other apps intact
def test_put_log_all_fields(created):
    _, h = driver(created, "TEST_log_put")
    before = requests.get(f"{API}/settings", headers=h).json()
    payload = {"enabled": True, "min_price_per_km": 2.75, "min_fare": 9.5, "max_pickup_km": 3.0,
               "accept_texts": ["Aceitar", "Pegar"], "reject_enabled": True, "reject_texts": ["Recusar", "Ignorar"],
               "finish_texts": ["Finalizar"], "target_package": "br.com.logurbano"}
    r = requests.put(f"{API}/settings", headers=h, json={"apps": {"log": payload}})
    assert r.status_code == 200, r.text
    assert r.json()["apps"]["log"]["min_fare"] == 9.5
    after = requests.get(f"{API}/settings", headers=h).json()
    for f, v in payload.items():
        assert after["apps"]["log"][f] == v, f
    for k in ("rapido", "moove", "urbano"):
        assert after["apps"][k] == before["apps"][k]


# Settings: log validation identical to other apps
def test_put_log_validation(created):
    _, h = driver(created, "TEST_log_val")
    for bad in ({"target_package": "  "}, {"reject_texts": [" "]}, {"min_fare": "abc"}):
        r = requests.put(f"{API}/settings", headers=h, json={"apps": {"log": bad}})
        assert r.status_code == 422, (bad, r.status_code)


# Rides: bulk with app log/source logurbano, filter by app=log, summary has 'log'
def test_rides_log(created):
    _, h = driver(created, "TEST_log_rides")
    now = datetime.now(timezone.utc)
    items = [
        {"app": "log", "source": "logurbano", "price": 18.5, "trip_km": 6, "pickup_km": 1.2, "accepted": True},
        {"app": "log", "source": "logurbano", "price": 5, "trip_km": 4, "accepted": False, "reasons": ["Valor abaixo do mínimo"]},
        {"app": "moove", "source": "moovecar", "price": 12, "trip_km": 4, "accepted": True},
    ]
    r = requests.post(f"{API}/rides/bulk", headers=h, json=items)
    assert r.status_code == 200 and r.json()["inserted"] == 3
    lst = requests.get(f"{API}/rides", headers=h, params={"app": "log"}).json()
    assert len(lst) == 2 and all(x["app"] == "log" and x["source"] == "logurbano" for x in lst)
    acc = [x for x in lst if x["accepted"]][0]
    assert acc["price_per_km"] == round(18.5 / 6, 2) and acc["pickup_km"] == 1.2
    rej = requests.get(f"{API}/rides", headers=h, params={"app": "log", "status": "rejected"}).json()
    assert len(rej) == 1 and rej[0]["reasons"] == ["Valor abaixo do mínimo"]
    assert len(requests.get(f"{API}/rides", headers=h).json()) == 3
    s = requests.get(f"{API}/rides/summary", headers=h, params={"since": (now - timedelta(hours=1)).isoformat()}).json()
    assert set(s) == KEYS
    assert s["log"] == {"accepted": 1, "rejected": 1, "earned": 18.5}
    assert s["moove"]["accepted"] == 1


# Rides: bad source rejected; app99 still removed
def test_rides_log_bad_values(created):
    _, h = driver(created, "TEST_log_bad")
    assert requests.post(f"{API}/rides/bulk", headers=h,
                         json=[{"app": "log", "source": "log", "price": 1, "trip_km": 1, "accepted": True}]).status_code == 422
    assert requests.get(f"{API}/rides", headers=h, params={"app": "app99"}).status_code == 422
    assert requests.put(f"{API}/settings", headers=h, json={"apps": {"app99": {"enabled": True}}}).status_code == 422
