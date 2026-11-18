# UI seed for iteration 30 (floating bubble). Usage: python ui_seed_iter30.py seed|clean
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient

env = dict(l.split("=", 1) for l in Path("/app/backend/.env").read_text().splitlines() if "=" in l)
mdb = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
IDS = Path("/tmp/iter30_ids.json")


def cpf():
    while True:
        d = [random.randint(0, 9) for _ in range(9)]
        for n in (9, 10):
            d.append((sum(d[i] * (n + 1 - i) for i in range(n)) * 10) % 11 % 10)
        c = "".join(map(str, d))
        if c != c[0] * 11 and not mdb.users.find_one({"cpf": c}):
            return c


def seed():
    c = cpf()
    uid = str(mdb.users.insert_one({"cpf": c, "name": "TEST_bubble_ui", "status": "approved", "device_id": None,
                                    "created_at": datetime.now(timezone.utc).isoformat(), "expires_at": None}).inserted_id)
    IDS.write_text(json.dumps({"id": uid, "cpf": c}))
    print(json.dumps({"id": uid, "cpf": c}))


def clean():
    v = json.loads(IDS.read_text())
    mdb.users.delete_one({"_id": ObjectId(v["id"])})
    mdb.settings.delete_many({"user_id": v["id"]})
    mdb.rides.delete_many({"user_id": v["id"]})
    print("cleaned", v["id"])


if __name__ == "__main__":
    seed() if sys.argv[1] == "seed" else clean()
