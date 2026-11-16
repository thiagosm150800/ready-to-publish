# Seed/cleanup TEST_ users for iteration 10 UI test (usage: python ui_seed_iter10.py seed|cleanup|driver <hours|none>)
import json
import random
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from bson import ObjectId
from pymongo import MongoClient

env = dict(l.split("=", 1) for l in Path("/app/backend/.env").read_text().splitlines() if "=" in l)
db = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
STATE = "/tmp/ui_seed_iter10.json"


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


now = datetime.now(timezone.utc)
cmd = sys.argv[1]
if cmd == "seed":
    out = {
        "expired": mk("TEST_ui10_expired", "approved", (now - timedelta(days=1)).isoformat()),
        "expired2": mk("TEST_ui10_expired2", "approved", (now - timedelta(hours=2)).isoformat()),
        "approved": mk("TEST_ui10_approved", "approved", (now + timedelta(days=10)).isoformat()),
    }
    json.dump(out, open(STATE, "w"))
    print(json.dumps(out))
elif cmd == "driver":
    # set expiry of the main test driver; 'none' restores to no limit
    v = sys.argv[2]
    exp = None if v == "none" else (now + timedelta(hours=float(v))).isoformat()
    db.users.update_one({"cpf": "52998224725"}, {"$set": {"status": "approved", "expires_at": exp}})
    print("driver expires_at", exp)
else:
    st = json.load(open(STATE))
    for v in st.values():
        db.users.delete_one({"_id": ObjectId(v["id"])})
        db.rides.delete_many({"user_id": v["id"]})
        db.settings.delete_many({"user_id": v["id"]})
    print("cleaned")
