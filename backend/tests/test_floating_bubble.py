# RapidoChecker iteration 30: floating online/offline button — settings.bubble_enabled + "all bots" PUT used by syncManual
import requests

from test_blocked_places import API, mdb, created  # noqa: F401
from test_four_apps import driver, KEYS


# Settings: new driver gets bubble_enabled=True by default (bool type)
def test_new_driver_bubble_default_true(created):
    _, h = driver(created, "TEST_bubble_new")
    s = requests.get(f"{API}/settings", headers=h).json()
    assert s["bubble_enabled"] is True


# Settings: PUT bubble_enabled=false persists (GET + Mongo), other settings untouched
def test_put_bubble_false_persists(created):
    uid, h = driver(created, "TEST_bubble_put")
    before = requests.get(f"{API}/settings", headers=h).json()
    r = requests.put(f"{API}/settings", headers=h, json={"bubble_enabled": False})
    assert r.status_code == 200, r.text
    assert r.json()["bubble_enabled"] is False
    after = requests.get(f"{API}/settings", headers=h).json()
    assert after["bubble_enabled"] is False
    assert mdb.settings.find_one({"user_id": uid})["bubble_enabled"] is False
    for k in ("alert_enabled", "notify_enabled", "exclusive_enabled", "schedule_enabled", "apps"):
        assert after[k] == before[k], k
    # back to true
    r = requests.put(f"{API}/settings", headers=h, json={"bubble_enabled": True})
    assert r.json()["bubble_enabled"] is True
    assert requests.get(f"{API}/settings", headers=h).json()["bubble_enabled"] is True


# Settings: legacy doc without bubble_enabled returns True
def test_legacy_doc_without_field_returns_true(created):
    uid, h = driver(created, "TEST_bubble_legacy")
    requests.get(f"{API}/settings", headers=h)
    mdb.settings.update_one({"user_id": uid}, {"$unset": {"bubble_enabled": ""}})
    assert "bubble_enabled" not in mdb.settings.find_one({"user_id": uid})
    s = requests.get(f"{API}/settings", headers=h).json()
    assert s["bubble_enabled"] is True


# Settings: PUT omitting bubble_enabled does not change it; invalid type rejected
def test_put_other_fields_keeps_bubble_and_validation(created):
    _, h = driver(created, "TEST_bubble_keep")
    requests.put(f"{API}/settings", headers=h, json={"bubble_enabled": False})
    r = requests.put(f"{API}/settings", headers=h, json={"alert_enabled": False})
    assert r.status_code == 200 and r.json()["bubble_enabled"] is False
    r = requests.put(f"{API}/settings", headers=h, json={"bubble_enabled": "maybe"})
    assert r.status_code == 422


# syncManual payload: all apps enabled on/off in one PUT, filters of each app untouched
def test_all_bots_on_off_payload(created):
    _, h = driver(created, "TEST_bubble_all")
    requests.put(f"{API}/settings", headers=h, json={"apps": {"moove": {"min_fare": 12.5}}})
    for on in (True, False):
        r = requests.put(f"{API}/settings", headers=h, json={"apps": {k: {"enabled": on} for k in KEYS}})
        assert r.status_code == 200, r.text
        s = requests.get(f"{API}/settings", headers=h).json()
        assert all(s["apps"][k]["enabled"] is on for k in KEYS)
        assert s["apps"]["moove"]["min_fare"] == 12.5


# Auth: settings require token
def test_settings_requires_auth():
    assert requests.put(f"{API}/settings", json={"bubble_enabled": False}).status_code in (401, 403)
