# UI seed for iteration 26 (web admin panel). Usage: python ui_seed_iter26.py seed|clean
import json
import random
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient

env = dict(l.split("=", 1) for l in Path("/app/backend/.env").read_text().splitlines() if "=" in l)
mdb = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
IDS = Path("/tmp/iter26_ids.json")


def cpf():
    while True:
        d = [random.randint(0, 9) for _ in range(9)]
        for n in (9, 10):
            d.append((sum(d[i] * (n + 1 - i) for i in range(n)) * 10) % 11 % 10)
        c = "".join(map(str, d))
        if not mdb.users.find_one({"cpf": c}):
            return c


def seed():
    now = datetime.now(timezone.utc)
    base = {"device_id": None, "device_bound_at": None, "created_at": now.isoformat(), "expires_at": None,
            "trial_used": False, "trial_at": None}
    users = {
        "pending": {"name": "TEST_web_pending", "status": "pending"},
        "xss": {"name": "<img src=x onerror=alert(1)>", "status": "pending"},
        "expired": {"name": "TEST_web_expired", "status": "approved", "expires_at": (now - timedelta(days=1)).isoformat()},
        "active": {"name": "TEST_web_active", "status": "approved", "expires_at": (now + timedelta(days=20)).isoformat(),
                   "device_id": "TEST_dev_1", "device_bound_at": now.isoformat()},
        "blocked": {"name": "TEST_web_blocked", "status": "blocked"},
        "todelete": {"name": "TEST_web_delete", "status": "pending"},
    }
    out = {}
    for k, v in users.items():
        c = cpf()
        out[k] = {"id": str(mdb.users.insert_one({**base, "cpf": c, **v}).inserted_id), "cpf": c}
    IDS.write_text(json.dumps(out))
    print(json.dumps(out))


def clean():
    for v in json.loads(IDS.read_text()).values():
        mdb.users.delete_one({"_id": ObjectId(v["id"])})
    print("cleaned")


{"seed": seed, "clean": clean}[sys.argv[1]]()
