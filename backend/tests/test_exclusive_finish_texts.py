# RapidoChecker: "Uma corrida por vez" -> exclusive_enabled + apps.*.finish_texts (defaults, legacy docs, PUT validation)
from datetime import datetime, timezone

import pytest
import requests

from test_reject_notify_master import API, created, gen_cpf, make_driver, mdb  # noqa: F401

DEFAULT_FINISH = ["Finalizar", "Encerrar", "Concluir", "Cancelar corrida"]


@pytest.fixture(scope="module")
def driver(created):  # noqa: F811
    return make_driver(created)


# --- Defaults for new settings ---
def test_defaults_new_settings(driver):
    _, h = driver
    r = requests.get(f"{API}/settings", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "_id" not in d
    assert d["exclusive_enabled"] is True
    for k in ("rapido", "moove"):
        assert d["apps"][k]["finish_texts"] == DEFAULT_FINISH


# --- Settings docs created before these fields existed ---
def test_defaults_for_old_settings_doc(created):  # noqa: F811
    uid, h = make_driver(created)
    requests.get(f"{API}/settings", headers=h)  # create doc
    mdb.settings.update_one({"user_id": uid}, {"$unset": {"exclusive_enabled": "", "apps.rapido.finish_texts": "",
                                                           "apps.moove.finish_texts": ""}})
    raw = mdb.settings.find_one({"user_id": uid})
    assert "exclusive_enabled" not in raw and "finish_texts" not in raw["apps"]["rapido"]
    d = requests.get(f"{API}/settings", headers=h).json()
    assert d["exclusive_enabled"] is True
    assert d["apps"]["rapido"]["finish_texts"] == DEFAULT_FINISH
    assert d["apps"]["moove"]["finish_texts"] == DEFAULT_FINISH
    # A partial PUT on an old doc must also work
    r = requests.put(f"{API}/settings", headers=h, json={"apps": {"moove": {"min_fare": 9}}})
    assert r.status_code == 200, r.text
    assert r.json()["apps"]["moove"]["finish_texts"] == DEFAULT_FINISH


# --- Legacy single-app settings (no 'apps' key) ---
def test_legacy_single_app_doc(created):  # noqa: F811
    uid, h = make_driver(created)
    mdb.settings.insert_one({"user_id": uid, "min_fare": 11, "auto_accept": True,
                             "created_at": datetime.now(timezone.utc).isoformat()})
    r = requests.get(f"{API}/settings", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["exclusive_enabled"] is True
    assert d["apps"]["rapido"]["finish_texts"] == DEFAULT_FINISH


def test_put_exclusive_false_persists(driver):
    _, h = driver
    r = requests.put(f"{API}/settings", headers=h, json={"exclusive_enabled": False})
    assert r.status_code == 200, r.text
    assert r.json()["exclusive_enabled"] is False
    assert requests.get(f"{API}/settings", headers=h).json()["exclusive_enabled"] is False
    r = requests.put(f"{API}/settings", headers=h, json={"exclusive_enabled": True})
    assert r.json()["exclusive_enabled"] is True


@pytest.mark.parametrize("bad", [["  "], [], ["", " "]])
def test_put_finish_texts_blank_422(driver, bad):
    _, h = driver
    r = requests.put(f"{API}/settings", headers=h, json={"apps": {"rapido": {"finish_texts": bad}}})
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "Informe o texto do botão Finalizar."
    assert requests.get(f"{API}/settings", headers=h).json()["apps"]["rapido"]["finish_texts"] == DEFAULT_FINISH


def test_put_finish_texts_trimmed_saved_per_app(driver):
    _, h = driver
    r = requests.put(f"{API}/settings", headers=h,
                     json={"apps": {"rapido": {"finish_texts": ["  TEST_Fim ", "", " Encerrar"]},
                                    "moove": {"finish_texts": ["TEST_Concluir viagem"]}}})
    assert r.status_code == 200, r.text
    d = requests.get(f"{API}/settings", headers=h).json()
    assert d["apps"]["rapido"]["finish_texts"] == ["TEST_Fim", "Encerrar"]
    assert d["apps"]["moove"]["finish_texts"] == ["TEST_Concluir viagem"]
    # Other fields untouched
    assert d["apps"]["rapido"]["reject_texts"] == ["Recusar"]


def test_finish_texts_wrong_type_422(driver):
    _, h = driver
    r = requests.put(f"{API}/settings", headers=h, json={"apps": {"rapido": {"finish_texts": "Finalizar"}}})
    assert r.status_code == 422


def test_exclusive_requires_auth():
    assert requests.put(f"{API}/settings", json={"exclusive_enabled": False}).status_code in (401, 403)
