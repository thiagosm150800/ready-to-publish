"""AutoCorrida API regression tests: settings, simulate, rides bulk/list, stats."""
import os
from datetime import datetime, timezone, timedelta

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    # auth: each run uses a throwaway TEST_ driver (deleted at teardown with all its data)
    import uuid
    reg = sess.post(f"{API}/auth/register", json={"name": "TEST_Reg", "email": f"test_{uuid.uuid4().hex[:10]}@example.com", "password": "testpass123"})
    assert reg.status_code == 201, reg.text
    sess.headers["Authorization"] = f"Bearer {reg.json()['access_token']}"
    orig = sess.get(f"{API}/settings").json()
    before_ids = {x["id"] for x in sess.get(f"{API}/rides?status=all&limit=500").json()}
    yield sess
    sess.delete(f"{API}/auth/account")
    return
    # restore original settings (incl. 99 fields), force auto_accept/sync off
    orig.pop("id", None); orig.pop("key", None)
    orig.update({"auto_accept": False, "sync_99_enabled": False})
    sess.put(f"{API}/settings", json=orig)
    # cleanup only rides created by this run (by id)
    from pymongo import MongoClient
    from bson import ObjectId
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).parent.parent / ".env")
    after = sess.get(f"{API}/rides?status=all&limit=500").json()
    mine = [x["id"] for x in after if x["id"] not in before_ids and (x["id"] in CREATED or x["source"] == "rapidocar" and x["price"] in (30.0, 5.0))]
    if mine:
        MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]].rides.delete_many({"_id": {"$in": [ObjectId(i) for i in mine]}})


CREATED = set()


# --- health ---
def test_root(s):
    r = s.get(f"{API}/")
    assert r.status_code == 200 and r.json()["message"] == "AutoCorrida API"


# --- settings ---
def test_get_settings_shape(s):
    d = s.get(f"{API}/settings").json()
    for k in ["auto_accept", "min_price_per_km", "min_fare", "max_pickup_km", "accept_texts", "target_package"]:
        assert k in d
    assert "_id" not in d
    assert isinstance(d["accept_texts"], list)


def test_put_settings_partial_and_persist(s):
    before = s.get(f"{API}/settings").json()
    r = s.put(f"{API}/settings", json={"min_fare": 9.5})
    assert r.status_code == 200
    d = r.json()
    assert d["min_fare"] == 9.5
    assert d["min_price_per_km"] == before["min_price_per_km"]
    assert s.get(f"{API}/settings").json()["min_fare"] == 9.5


def test_put_settings_accept_texts_trimmed(s):
    d = s.put(f"{API}/settings", json={"accept_texts": ["  Aceitar ", "", "  ", "Accept"]}).json()
    assert d["accept_texts"] == ["Aceitar", "Accept"]


def test_put_settings_negative_rejected(s):
    r = s.put(f"{API}/settings", json={"min_price_per_km": -1})
    assert r.status_code == 422


def test_put_settings_toggle_auto_accept(s):
    d = s.put(f"{API}/settings", json={"auto_accept": True}).json()
    assert d["auto_accept"] is True
    d = s.put(f"{API}/settings", json={"auto_accept": False}).json()
    assert d["auto_accept"] is False


# --- simulate ---
def _check_reasons(ride, st):
    exp = []
    if ride["price_per_km"] < st["min_price_per_km"]:
        exp.append("R$/km abaixo do mínimo")
    if ride["price"] < st["min_fare"]:
        exp.append("Valor abaixo do mínimo")
    if ride["pickup_km"] > st["max_pickup_km"]:
        exp.append("Busca muito longe")
    assert ride["reasons"] == exp, (ride, st)
    assert ride["accepted"] == (not exp)


def test_simulate_evaluation_default_filters(s):
    st = s.put(f"{API}/settings", json={"min_price_per_km": 2.0, "min_fare": 8.0, "max_pickup_km": 4.0}).json()
    for _ in range(8):
        r = s.post(f"{API}/simulate")
        assert r.status_code == 200
        ride = r.json()
        CREATED.add(ride["id"])
        assert ride["id"] and ride["source"] == "simulador"
        assert ride["pickup"] and ride["dropoff"]
        assert ride["price_per_km"] == round(ride["price"] / ride["trip_km"], 2)
        _check_reasons(ride, st)


def test_simulate_always_accept_when_filters_zero(s):
    s.put(f"{API}/settings", json={"min_price_per_km": 0, "min_fare": 0, "max_pickup_km": 100})
    ride = s.post(f"{API}/simulate").json()
    CREATED.add(ride["id"])
    assert ride["accepted"] is True and ride["reasons"] == []


def test_simulate_always_reject_with_high_filters(s):
    s.put(f"{API}/settings", json={"min_price_per_km": 100, "min_fare": 1000, "max_pickup_km": 0})
    ride = s.post(f"{API}/simulate").json()
    CREATED.add(ride["id"])
    assert ride["accepted"] is False
    assert ride["reasons"] == ["R$/km abaixo do mínimo", "Valor abaixo do mínimo", "Busca muito longe"]
    s.put(f"{API}/settings", json={"min_price_per_km": 2.0, "min_fare": 8.0, "max_pickup_km": 4.0})


# --- rides bulk / list ---
def test_bulk_insert_and_list(s):
    now = datetime.now(timezone.utc).isoformat()
    items = [
        {"price": 30.0, "trip_km": 10.0, "pickup_km": 1.0, "accepted": True, "reasons": [], "created_at": now},
        {"price": 5.0, "trip_km": 10.0, "pickup_km": 6.0, "accepted": False,
         "reasons": ["R$/km abaixo do mínimo"], "created_at": now},
    ]
    r = s.post(f"{API}/rides/bulk", json=items)
    assert r.status_code == 200 and r.json()["inserted"] == 2
    all_r = s.get(f"{API}/rides?status=all").json()
    assert any(x["source"] == "rapidocar" and x["price"] == 30.0 and x["price_per_km"] == 3.0 for x in all_r)
    assert all("_id" not in x for x in all_r)


def test_bulk_empty(s):
    r = s.post(f"{API}/rides/bulk", json=[])
    assert r.status_code == 200 and r.json()["inserted"] == 0


def test_list_status_filters(s):
    acc = s.get(f"{API}/rides?status=accepted").json()
    rej = s.get(f"{API}/rides?status=rejected").json()
    assert all(x["accepted"] for x in acc)
    assert all(not x["accepted"] for x in rej)
    assert s.get(f"{API}/rides?status=bogus").status_code == 422


def test_list_sorted_desc(s):
    rows = s.get(f"{API}/rides?status=all&limit=50").json()
    ts = [x["created_at"] for x in rows]
    assert ts == sorted(ts, reverse=True)


# --- stats ---
def test_stats_since_today(s):
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    st = s.get(f"{API}/stats", params={"since": since}).json()
    rows = s.get(f"{API}/rides?status=all&limit=500").json()
    rows = [x for x in rows if datetime.fromisoformat(x["created_at"].replace("Z", "+00:00")) >= datetime.fromisoformat(since.replace("Z", "+00:00"))]
    exp_earn = round(sum(x["price"] for x in rows if x["accepted"]), 2)
    assert st["today_total"] == len(rows)
    assert st["today_accepted"] == sum(1 for x in rows if x["accepted"])
    assert abs(st["today_earnings"] - exp_earn) < 0.01
    if rows:
        assert st["accept_rate"] == round(st["today_accepted"] * 100 / st["today_total"], 1)


def test_stats_future_since_zero(s):
    st = s.get(f"{API}/stats", params={"since": "2099-01-01T00:00:00Z"}).json()
    assert st == {"today_earnings": 0, "today_total": 0, "today_accepted": 0, "accept_rate": 0}


def test_stats_invalid_since(s):
    r = s.get(f"{API}/stats", params={"since": "not-a-date"})
    assert r.status_code in (400, 422), f"got {r.status_code}"


# --- 99 sync settings ---
def test_settings_has_99_fields(s):
    d = s.get(f"{API}/settings").json()
    assert isinstance(d["sync_99_enabled"], bool)
    assert isinstance(d["ninety_nine_package"], str)
    for k in ["ride_active_texts", "ride_end_texts", "offline_texts", "online_texts"]:
        assert isinstance(d[k], list) and all(isinstance(x, str) for x in d[k])


def test_put_99_toggle_persist(s):
    before = s.get(f"{API}/settings").json()
    d = s.put(f"{API}/settings", json={"sync_99_enabled": True}).json()
    assert d["sync_99_enabled"] is True and d["min_fare"] == before["min_fare"]
    assert s.get(f"{API}/settings").json()["sync_99_enabled"] is True
    assert s.put(f"{API}/settings", json={"sync_99_enabled": False}).json()["sync_99_enabled"] is False


def test_put_99_text_lists_trimmed(s):
    orig = s.get(f"{API}/settings").json()
    body = {"ride_active_texts": [" Iniciar corrida ", "", "  "], "ride_end_texts": ["  Corrida finalizada"],
            "offline_texts": ["Ficar offline  ", " "], "online_texts": ["\tFicar online\n"],
            "ninety_nine_package": "TEST_pkg"}
    d = s.put(f"{API}/settings", json=body).json()
    assert d["ride_active_texts"] == ["Iniciar corrida"]
    assert d["ride_end_texts"] == ["Corrida finalizada"]
    assert d["offline_texts"] == ["Ficar offline"]
    assert d["online_texts"] == ["Ficar online"]
    g = s.get(f"{API}/settings").json()
    assert g["ninety_nine_package"] == "TEST_pkg" and g["offline_texts"] == ["Ficar offline"]
    s.put(f"{API}/settings", json={k: orig[k] for k in body})


def test_put_settings_invalid_type(s):
    assert s.put(f"{API}/settings", json={"sync_99_enabled": "maybe"}).status_code == 422
    assert s.put(f"{API}/settings", json={"offline_texts": "notalist"}).status_code == 422


# --- iteration 2: created_at UTC normalization on bulk ---
def test_bulk_created_at_offset_normalized(s):
    items = [
        {"price": 30.0, "trip_km": 10.0, "accepted": True, "created_at": "2025-01-15T10:00:00-03:00"},
        {"price": 5.0, "trip_km": 10.0, "accepted": False, "created_at": "2025-01-15T09:00:00Z"},
        {"price": 30.0, "trip_km": 10.0, "accepted": True, "created_at": "2025-01-15T08:00:00"},
    ]
    r = s.post(f"{API}/rides/bulk", json=items)
    assert r.status_code == 200 and r.json()["inserted"] == 3
    # verify directly in DB (rows are old, may not be in top 500 list)
    from pymongo import MongoClient
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).parent.parent / ".env")
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    docs = list(db.rides.find({"user_id": s.get(f"{API}/auth/me").json()["id"], "source": "rapidocar", "created_at": {"$regex": "^2025-01-15T"}}))
    for d in docs:
        CREATED.add(str(d["_id"]))
    stamps = sorted(d["created_at"] for d in docs)
    assert "2025-01-15T13:00:00+00:00" in stamps
    assert "2025-01-15T09:00:00+00:00" in stamps
    assert "2025-01-15T08:00:00+00:00" in stamps
    assert all(x.endswith("+00:00") for x in stamps)
    db.rides.delete_many({"_id": {"$in": [d["_id"] for d in docs]}})


def test_bulk_invalid_created_at(s):
    r = s.post(f"{API}/rides/bulk", json=[{"price": 1.0, "trip_km": 1.0, "accepted": False, "created_at": "garbage"}])
    print("bulk invalid created_at ->", r.status_code)
    assert r.status_code in (400, 422), f"got {r.status_code}"
