"""Iteration 3: schedule/alert settings, weekly stats, simulate schedule reason."""
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
TZ = -180
CREATED = []
SCHED_REASON = "Fora do horário de trabalho"


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
    yield sess
    sess.delete(f"{API}/auth/account")
    return
    orig.pop("id", None); orig.pop("key", None)
    orig.update({"auto_accept": False, "sync_99_enabled": False, "schedule_enabled": False, "alert_enabled": True})
    sess.put(f"{API}/settings", json=orig)
    if CREATED:
        from pymongo import MongoClient
        from bson import ObjectId
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env")
        MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]].rides.delete_many(
            {"_id": {"$in": [ObjectId(i) for i in CREATED]}})


def local_now():
    return datetime.now(timezone.utc) + timedelta(minutes=TZ)


def hhmm(m):
    m %= 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def today_idx():
    return (local_now().weekday() + 1) % 7


def sim(s):
    r = s.post(f"{API}/simulate?tz={TZ}")
    assert r.status_code == 200
    d = r.json()
    CREATED.append(d["id"])
    return d


# --- settings: new fields ---
def test_settings_defaults_shape(s):
    d = s.get(f"{API}/settings").json()
    for k in ["schedule_enabled", "schedule_start", "schedule_end", "schedule_days", "alert_enabled"]:
        assert k in d
    assert isinstance(d["schedule_days"], list) and isinstance(d["alert_enabled"], bool)


def test_put_schedule_persists(s):
    body = {"schedule_enabled": True, "schedule_start": "07:30", "schedule_end": "23:15", "schedule_days": [1, 2, 3], "alert_enabled": False}
    r = s.put(f"{API}/settings", json=body)
    assert r.status_code == 200
    g = s.get(f"{API}/settings").json()
    for k, v in body.items():
        assert g[k] == v


@pytest.mark.parametrize("bad", ["24:00", "7:30", "12:60", "ab:cd", "1230", ""])
def test_put_invalid_time_422(s, bad):
    r = s.put(f"{API}/settings", json={"schedule_start": bad})
    assert r.status_code == 422, (bad, r.status_code)
    r = s.put(f"{API}/settings", json={"schedule_end": bad})
    assert r.status_code == 422


@pytest.mark.parametrize("bad", [[7], [-1], [0, 9]])
def test_put_invalid_days_422(s, bad):
    assert s.put(f"{API}/settings", json={"schedule_days": bad}).status_code == 422


# --- simulate with schedule ---
def _set_pass_all(s, **kw):
    body = {"min_price_per_km": 0, "min_fare": 0, "max_pickup_km": 100, "schedule_days": [0, 1, 2, 3, 4, 5, 6]}
    body.update(kw)
    assert s.put(f"{API}/settings", json=body).status_code == 200


def test_simulate_outside_window(s):
    m = local_now().hour * 60 + local_now().minute
    _set_pass_all(s, schedule_enabled=True, schedule_start=hhmm(m + 60), schedule_end=hhmm(m + 120))
    d = sim(s)
    assert SCHED_REASON in d["reasons"] and d["accepted"] is False


def test_simulate_inside_window(s):
    m = local_now().hour * 60 + local_now().minute
    _set_pass_all(s, schedule_enabled=True, schedule_start=hhmm(m - 60), schedule_end=hhmm(m + 60))
    d = sim(s)
    assert SCHED_REASON not in d["reasons"] and d["accepted"] is True


def test_simulate_crossing_midnight_inside(s):
    m = local_now().hour * 60 + local_now().minute
    # start > end (crosses midnight) and contains now
    _set_pass_all(s, schedule_enabled=True, schedule_start=hhmm(m - 30), schedule_end=hhmm(m - 60))
    d = sim(s)
    assert SCHED_REASON not in d["reasons"]


def test_simulate_day_excluded(s):
    m = local_now().hour * 60 + local_now().minute
    days = [i for i in range(7) if i != today_idx()]
    _set_pass_all(s, schedule_enabled=True, schedule_start=hhmm(m - 60), schedule_end=hhmm(m + 60))
    s.put(f"{API}/settings", json={"schedule_days": days})
    d = sim(s)
    assert SCHED_REASON in d["reasons"]


def test_simulate_schedule_disabled(s):
    m = local_now().hour * 60 + local_now().minute
    _set_pass_all(s, schedule_enabled=False, schedule_start=hhmm(m + 60), schedule_end=hhmm(m + 120))
    d = sim(s)
    assert SCHED_REASON not in d["reasons"]


# --- weekly stats ---
def test_weekly_shape(s):
    r = s.get(f"{API}/stats/weekly?tz={TZ}")
    assert r.status_code == 200
    d = r.json()
    assert len(d["days"]) == 7
    labels = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
    assert d["days"][-1]["date"] == local_now().date().isoformat()
    assert d["days"][-1]["label"] == labels[today_idx()]
    for day in d["days"]:
        for k in ["date", "label", "earnings", "accepted", "total", "accept_rate"]:
            assert k in day
    assert round(sum(x["earnings"] for x in d["days"]), 2) == d["week_earnings"]
    assert sum(x["total"] for x in d["days"]) == d["week_total"]
    assert sum(x["accepted"] for x in d["days"]) == d["week_accepted"]


def test_weekly_invalid_tz_422(s):
    assert s.get(f"{API}/stats/weekly?tz=9999").status_code == 422


def test_weekly_consistent_with_simulated(s):
    before = s.get(f"{API}/stats/weekly?tz={TZ}").json()
    _set_pass_all(s, schedule_enabled=False)
    rides = [sim(s) for _ in range(3)]
    s.put(f"{API}/settings", json={"min_price_per_km": 1000})
    rides.append(sim(s))
    after = s.get(f"{API}/stats/weekly?tz={TZ}").json()
    b, a = before["days"][-1], after["days"][-1]
    acc = [r for r in rides if r["accepted"]]
    assert a["total"] - b["total"] == 4
    assert a["accepted"] - b["accepted"] == len(acc) == 3
    assert round(a["earnings"] - b["earnings"], 2) == round(sum(r["price"] for r in acc), 2)
    assert a["accept_rate"] == round(a["accepted"] * 100 / a["total"], 1)


def test_weekly_bucket_past_day_bulk(s):
    # ride 3 local days ago at 01:00 -03:00 (04:00 UTC) should land in days[3]
    d3 = (local_now() - timedelta(days=3)).date()
    before = s.get(f"{API}/stats/weekly?tz={TZ}").json()["days"][3]
    ts = f"{d3.isoformat()}T01:00:00-03:00"
    r = s.post(f"{API}/rides/bulk", json=[{"price": 77.71, "trip_km": 10, "pickup_km": 1, "accepted": True, "reasons": [], "source": "rapidocar", "created_at": ts}])
    assert r.status_code == 200
    mine = [x for x in s.get(f"{API}/rides?limit=500").json() if x["price"] == 77.71]
    CREATED.extend(x["id"] for x in mine)
    after = s.get(f"{API}/stats/weekly?tz={TZ}").json()["days"][3]
    assert after["date"] == d3.isoformat()
    assert after["total"] - before["total"] == 1
    assert round(after["earnings"] - before["earnings"], 2) == 77.71
