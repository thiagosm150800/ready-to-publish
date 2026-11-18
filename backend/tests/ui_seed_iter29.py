# UI seed for iteration 29 (LOG Urbano). Usage: python ui_seed_iter28.py seed|clean
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient

import random


def cpf():
    while True:
        d = [random.randint(0, 9) for _ in range(9)]
        for n in (9, 10):
            d.append((sum(d[i] * (n + 1 - i) for i in range(n)) * 10) % 11 % 10)
        c = "".join(map(str, d))
        if not mdb.users.find_one({"cpf": c}):
            return c

env = dict(l.split("=", 1) for l in Path("/app/backend/.env").read_text().splitlines() if "=" in l)
mdb = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
IDS = Path("/tmp/iter29_ids.json")
DEF = {"enabled": False, "min_price_per_km": 2.0, "min_fare": 8.0, "max_pickup_km": 4.0,
       "accept_texts": ["Aceitar"], "reject_enabled": False, "reject_texts": ["Recusar"], "finish_texts": ["Finalizar"]}


def seed():
    now = datetime.now(timezone.utc)
    c = cpf()
    uid = str(mdb.users.insert_one({"cpf": c, "name": "TEST_log_ui", "status": "approved", "device_id": None,
                                    "created_at": now.isoformat(), "expires_at": None}).inserted_id)
    # legacy settings doc that still has app99 + radar fields
    mdb.settings.insert_one({"user_id": uid, "apps": {"rapido": {**DEF, "enabled": True, "target_package": "rapido"},
                                                      "moove": {**DEF, "target_package": "moove"},
                                                      "urbano": {**DEF, "target_package": "urbanonorte"},
                                                      },
                             "radar_enabled": True, "radar_interval_s": 3})
    rides = [("rapido", "rapidocar", True, 20.0), ("moove", "moovecar", False, 6.0),
             ("urbano", "urbanonorte", True, 14.0), ("log", "logurbano", True, 31.0)]
    mdb.rides.insert_many([{"user_id": uid, "app": a, "source": s, "price": p, "trip_km": 5.0, "pickup_km": 1.0,
                            "price_per_km": round(p / 5, 2), "accepted": acc, "reasons": [] if acc else ["Valor abaixo do mínimo"],
                            "created_at": (now - timedelta(minutes=i + 1)).isoformat()} for i, (a, s, acc, p) in enumerate(rides)])
    IDS.write_text(json.dumps({"id": uid, "cpf": c}))
    print(json.dumps({"id": uid, "cpf": c}))


def clean():
    v = json.loads(IDS.read_text())
    mdb.users.delete_one({"_id": ObjectId(v["id"])})
    mdb.rides.delete_many({"user_id": v["id"]})
    mdb.settings.delete_many({"user_id": v["id"]})
    print("cleaned")


{"seed": seed, "clean": clean}[sys.argv[1]]()
