# RapidoChecker iteration 18: PUT /api/settings apps.{key}.target_package validation (empty/whitespace -> 422)
import pytest
import requests

from test_reject_notify_master import API, make_driver, created  # noqa: F401 (created = fixture)


@pytest.fixture(scope="module")
def driver(created):  # noqa: F811
    return make_driver(created)


def _pkg(headers, key):
    r = requests.get(f"{API}/settings", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["apps"][key]["target_package"]


@pytest.mark.parametrize("key", ["moove", "rapido"])
@pytest.mark.parametrize("value", ["", "   ", "\t \n"])
def test_empty_or_whitespace_target_package_rejected(driver, key, value):
    _, h = driver
    before = _pkg(h, key)
    r = requests.put(f"{API}/settings", headers=h, json={"apps": {key: {"target_package": value}}})
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "Informe o pacote do app."
    assert _pkg(h, key) == before  # nothing persisted


def test_valid_target_package_trimmed_and_saved(driver):
    _, h = driver
    r = requests.put(f"{API}/settings", headers=h, json={"apps": {"moove": {"target_package": "  com.moove.motorista  "}}})
    assert r.status_code == 200, r.text
    assert r.json()["apps"]["moove"]["target_package"] == "com.moove.motorista"
    assert _pkg(h, "moove") == "com.moove.motorista"
    # restore default
    r = requests.put(f"{API}/settings", headers=h, json={"apps": {"moove": {"target_package": "moove"}}})
    assert r.status_code == 200 and _pkg(h, "moove") == "moove"


def test_invalid_in_one_field_blocks_whole_update(driver):
    _, h = driver
    r = requests.put(f"{API}/settings", headers=h,
                     json={"alert_enabled": False, "apps": {"moove": {"min_fare": 99, "target_package": " "}}})
    assert r.status_code == 422
    s = requests.get(f"{API}/settings", headers=h).json()
    assert s["apps"]["moove"]["min_fare"] != 99
    assert s["alert_enabled"] is True


def test_omitted_target_package_keeps_value(driver):
    _, h = driver
    r = requests.put(f"{API}/settings", headers=h, json={"apps": {"rapido": {"min_fare": 7.5}}})
    assert r.status_code == 200
    assert r.json()["apps"]["rapido"]["target_package"] == "rapido"
    assert r.json()["apps"]["rapido"]["min_fare"] == 7.5


def test_null_target_package_ignored(driver):
    _, h = driver
    r = requests.put(f"{API}/settings", headers=h, json={"apps": {"moove": {"target_package": None}}})
    assert r.status_code == 200
    assert r.json()["apps"]["moove"]["target_package"] == "moove"
