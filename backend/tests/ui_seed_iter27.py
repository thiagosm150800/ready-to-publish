# UI seed for iteration 27 (Filtros 99 radar interval 1..30 + /aprender diag). Usage: python ui_seed_iter27.py seed|clean
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient

env = dict(l.split("=", 1) for l in Path("/app/backend/.env").read_text().splitlines() if "=" in l)
mdb = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
IDS = Path("/tmp/iter27_ids.json")


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
    c = cpf()
    doc = {"cpf": c, "name": "TEST_radar_ui", "status": "approved", "device_id": None, "device_bound_at": None,
           "created_at": now.isoformat(), "expires_at": None, "trial_used": False, "trial_at": None}
    uid = str(mdb.users.insert_one(doc).inserted_id)
    IDS.write_text(json.dumps({"id": uid, "cpf": c}))
    print(json.dumps({"id": uid, "cpf": c}))


def clean():
    v = json.loads(IDS.read_text())
    mdb.users.delete_one({"_id": ObjectId(v["id"])})
    for col in ("settings", "sessions", "rides"):
        if col in mdb.list_collection_names():
            mdb[col].delete_many({"user_id": v["id"]})
    print("cleaned")


{"seed": seed, "clean": clean}[sys.argv[1]]()
