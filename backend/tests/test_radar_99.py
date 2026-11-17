# RapidoChecker: 99 radar settings (radar_enabled / radar_interval_s defaults, save, 1..30 validation)
import requests

from test_blocked_places import API, mdb, gen_cpf, created  # noqa: F401
from test_four_apps import driver


# Settings: radar defaults present (app99 off / 1s)
def test_radar_defaults(created):
    _, h = driver(created, "TEST_radar")
    apps = requests.get(f"{API}/settings", headers=h).json()["apps"]
    assert apps["app99"]["radar_enabled"] is False
    assert apps["app99"]["radar_interval_s"] == 1
    for k in ("rapido", "moove", "urbano"):
        assert "radar_enabled" in apps[k]


# Settings: PUT app99 radar on + 6s persists and does not touch other fields / apps
def test_radar_save_and_persist(created):
    _, h = driver(created, "TEST_radar")
    before = requests.get(f"{API}/settings", headers=h).json()
    r = requests.put(f"{API}/settings", headers=h, json={"apps": {"app99": {"radar_enabled": True, "radar_interval_s": 6}}})
    assert r.status_code == 200, r.text
    assert r.json()["apps"]["app99"]["radar_enabled"] is True
    s = requests.get(f"{API}/settings", headers=h).json()
    assert s["apps"]["app99"]["radar_enabled"] is True and s["apps"]["app99"]["radar_interval_s"] == 6
    assert s["apps"]["app99"]["min_fare"] == before["apps"]["app99"]["min_fare"]
    assert s["apps"]["app99"]["target_package"] == "app99"
    assert s["apps"]["rapido"] == before["apps"]["rapido"]
    # bounds 1 and 30 accepted
    for v in (1, 30):
        r = requests.put(f"{API}/settings", headers=h, json={"apps": {"app99": {"radar_interval_s": v}}})
        assert r.status_code == 200 and r.json()["apps"]["app99"]["radar_interval_s"] == v


# Settings: out-of-range interval -> 422 and nothing saved
def test_radar_interval_validation(created):
    _, h = driver(created, "TEST_radar")
    requests.put(f"{API}/settings", headers=h, json={"apps": {"app99": {"radar_interval_s": 5}}})
    for bad in (0, 31, -3, 100):
        r = requests.put(f"{API}/settings", headers=h, json={"apps": {"app99": {"radar_interval_s": bad}}})
        assert r.status_code == 422, (bad, r.status_code)
    assert requests.get(f"{API}/settings", headers=h).json()["apps"]["app99"]["radar_interval_s"] == 5


# Settings: radar off again persists
def test_radar_toggle_off(created):
    _, h = driver(created, "TEST_radar")
    requests.put(f"{API}/settings", headers=h, json={"apps": {"app99": {"radar_enabled": True}}})
    r = requests.put(f"{API}/settings", headers=h, json={"apps": {"app99": {"radar_enabled": False}}})
    assert r.status_code == 200
    assert requests.get(f"{API}/settings", headers=h).json()["apps"]["app99"]["radar_enabled"] is False


# Settings: unauthenticated PUT rejected
def test_radar_requires_auth():
    r = requests.put(f"{API}/settings", json={"apps": {"app99": {"radar_enabled": True}}})
    assert r.status_code in (401, 403)
