# Seed/cleanup TEST_ users for iteration 9 UI test (usage: python ui_seed_iter9.py seed|cleanup)
import json
import random
import sys
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from pymongo import MongoClient

db = MongoClient("mongodb://localhost:27017")["test_database"]
STATE = "/tmp/ui_seed_iter9.json"


def gen_cpf():
    d = [random.randint(0, 9) for _ in range(9)]
    for n in (9, 10):
        s = sum(d[i] * (n + 1 - i) for i in range(n))
        d.append((s * 10) % 11 % 10)
    c = "".join(map(str, d))
    return gen_cpf() if c == c[0] * 11 or db.users.find_one({"cpf": c}) else c


def mk(name, status, expires_at):
    cpf = gen_cpf()
    now = datetime.now(timezone.utc)
    r = db.users.insert_one({"cpf": cpf, "name": name, "status": status, "created_at": now.isoformat(),
                             "status_changed_at": None, "last_login_at": None, "expires_at": expires_at})
    return {"id": str(r.inserted_id), "cpf": cpf}


if sys.argv[1] == "seed":
    now = datetime.now(timezone.utc)
    out = {
        "pending": mk("TEST_ui_pending", "pending", None),
        "approved": mk("TEST_ui_approved", "approved", (now + timedelta(days=7)).isoformat()),
        "expired": mk("TEST_ui_expired", "approved", (now - timedelta(days=1)).isoformat()),
        "driver": mk("TEST_ui_driver", "approved", None),
    }
    json.dump(out, open(STATE, "w"))
    print(json.dumps(out))
else:
    st = json.load(open(STATE))
    for v in st.values():
        db.users.delete_one({"_id": ObjectId(v["id"])})
        db.rides.delete_many({"user_id": v["id"]})
        db.settings.delete_many({"user_id": v["id"]})
    print("cleaned")
