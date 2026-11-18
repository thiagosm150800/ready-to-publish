# RapidoChecker: 99 app (app99/99app) + radar removed -> only rapido/moove/urbano remain
from datetime import datetime, timezone, timedelta

import requests

from test_blocked_places import API, mdb, gen_cpf, created  # noqa: F401
from test_four_apps import driver, DEFAULTS

KEYS = {"rapido", "moove", "urbano", "log"}


def _ride(uid, app, source, accepted=True, price=10.0, minutes=1):
    return {"user_id": uid, "app": app, "source": source, "price": price, "trip_km": 5.0, "pickup_km": 1.0,
            "price_per_km": round(price / 5.0, 2), "accepted": accepted, "reasons": [],
            "created_at": (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()}


# Settings: new driver -> exactly 3 apps, no radar fields anywhere
def test_settings_three_apps_no_radar(created):
    _, h = driver(created, "TEST_no99")
    r = requests.get(f"{API}/settings", headers=h)
    assert r.status_code == 200
    s = r.json()
    assert set(s["apps"]) == KEYS
    assert "radar_enabled" not in s and "radar_interval_s" not in s
    for k in KEYS:
        assert not any("radar" in f for f in s["apps"][k])


# Settings: legacy doc with apps.app99 + radar fields is cleaned on read ($unset) without 500
def test_legacy_app99_doc_cleaned(created):
    uid, h = driver(created, "TEST_no99_legacy")
    requests.get(f"{API}/settings", headers=h)
    custom_r = {**DEFAULTS, "enabled": True, "min_fare": 12.5, "target_package": "rapido"}
    app99 = {**DEFAULTS, "enabled": True, "target_package": "com.app99.driver"}
    mdb.settings.update_one({"user_id": uid}, {"$set": {"apps.app99": app99, "apps.rapido": custom_r,
                                                        "radar_enabled": True, "radar_interval_s": 5}})
    assert "app99" in mdb.settings.find_one({"user_id": uid})["apps"]
    r = requests.get(f"{API}/settings", headers=h)
    assert r.status_code == 200, r.text
    s = r.json()
    assert set(s["apps"]) == KEYS
    assert s["apps"]["rapido"]["min_fare"] == 12.5 and s["apps"]["rapido"]["enabled"] is True
    assert "radar_enabled" not in s and "radar_interval_s" not in s
    doc = mdb.settings.find_one({"user_id": uid})
    assert "app99" not in doc["apps"]  # persisted $unset
    assert set(doc["apps"]) == KEYS


# Settings: legacy doc with ONLY rapido/moove/app99 (urbano missing) -> $unset + $set in same update
def test_legacy_app99_and_missing_urbano(created):
    uid, h = driver(created, "TEST_no99_mix")
    requests.get(f"{API}/settings", headers=h)
    apps = {k: {**DEFAULTS, "target_package": k} for k in ("rapido", "moove", "app99")}
    mdb.settings.update_one({"user_id": uid}, {"$set": {"apps": apps}})
    r = requests.get(f"{API}/settings", headers=h)
    assert r.status_code == 200, r.text
    assert set(r.json()["apps"]) == KEYS
    assert set(mdb.settings.find_one({"user_id": uid})["apps"]) == KEYS


# Settings: PUT apps.app99 -> 422 and nothing persisted
def test_put_app99_rejected(created):
    uid, h = driver(created, "TEST_no99_put")
    requests.get(f"{API}/settings", headers=h)
    r = requests.put(f"{API}/settings", headers=h, json={"apps": {"app99": {"enabled": True}}})
    assert r.status_code == 422
    r = requests.put(f"{API}/settings", headers=h, json={"apps": {"urbano": {"enabled": True}, "app99": {"enabled": True}}})
    assert r.status_code == 422
    doc = mdb.settings.find_one({"user_id": uid})
    assert "app99" not in doc["apps"] and doc["apps"]["urbano"]["enabled"] is False
    # valid apps still work
    r = requests.put(f"{API}/settings", headers=h, json={"apps": {"urbano": {"enabled": True}}})
    assert r.status_code == 200 and r.json()["apps"]["urbano"]["enabled"] is True


# Rides: app=app99 filter and bulk app99 / source 99app -> 422
def test_rides_app99_validation(created):
    _, h = driver(created, "TEST_no99_rides")
    assert requests.get(f"{API}/rides", headers=h, params={"app": "app99"}).status_code == 422
    for body in ({"app": "app99", "source": "urbanonorte"}, {"app": "urbano", "source": "99app"}):
        r = requests.post(f"{API}/rides/bulk", headers=h,
                          json=[{**body, "price": 10, "trip_km": 5, "accepted": True}])
        assert r.status_code == 422, body


# Rides: legacy app99 rides in Mongo are excluded from list and summary (no 500)
def test_legacy_app99_rides_excluded(created):
    uid, h = driver(created, "TEST_no99_old")
    mdb.rides.insert_many([_ride(uid, "app99", "99app", True, 30.0), _ride(uid, "app99", "99app", False, 7.0),
                           _ride(uid, "urbano", "urbanonorte", True, 15.0, 2)])
    r = requests.get(f"{API}/rides", headers=h)
    assert r.status_code == 200, r.text
    rides = r.json()
    assert len(rides) == 1 and rides[0]["app"] == "urbano"
    for st in ("accepted", "rejected"):
        r = requests.get(f"{API}/rides", headers=h, params={"status": st})
        assert r.status_code == 200 and all(x["app"] != "app99" for x in r.json())
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    r = requests.get(f"{API}/rides/summary", headers=h, params={"since": since})
    assert r.status_code == 200, r.text
    s = r.json()
    assert set(s) == KEYS
    assert s["urbano"] == {"accepted": 1, "rejected": 0, "earned": 15.0}
    assert s["rapido"]["accepted"] == 0 and s["moove"]["accepted"] == 0
    mdb.rides.delete_many({"user_id": uid})


# Rides: a mixed batch (valid + legacy app99) is rejected entirely -> frontend must filter queued app99 events
def test_mixed_bulk_with_app99_rejected_whole_batch(created):
    uid, h = driver(created, "TEST_no99_mixbulk")
    r = requests.post(f"{API}/rides/bulk", headers=h, json=[
        {"app": "urbano", "source": "urbanonorte", "price": 10, "trip_km": 5, "accepted": True},
        {"app": "app99", "source": "99app", "price": 10, "trip_km": 5, "accepted": True}])
    assert r.status_code == 422
    assert mdb.rides.count_documents({"user_id": uid}) == 0
