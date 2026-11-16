# Iteration 11 helper: set main driver state (usage: python ui_seed_iter11.py expired|blocked|soon|restore)
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from pymongo import MongoClient

env = dict(l.split("=", 1) for l in Path("/app/backend/.env").read_text().splitlines() if "=" in l)
db = MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]
CPF = "52998224725"
cmd = sys.argv[1]
now = datetime.now(timezone.utc)
if cmd == "expired":
    upd = {"status": "approved", "expires_at": "2020-01-01T00:00:00+00:00"}
elif cmd == "blocked":
    upd = {"status": "blocked", "expires_at": None}
elif cmd == "soon":
    upd = {"status": "approved", "expires_at": (now + timedelta(hours=20)).isoformat()}
else:
    upd = {"status": "approved", "expires_at": None}
db.users.update_one({"cpf": CPF}, {"$set": upd})
print("driver", upd)
