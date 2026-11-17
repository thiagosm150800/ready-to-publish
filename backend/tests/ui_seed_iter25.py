# Seed 2 pending TEST_ drivers for iteration 25 (1-day trial) UI test; prints ids; delete them by id afterwards
import sys
sys.path.insert(0, "/app/backend/tests")
from datetime import datetime, timezone
from test_blocked_places import mdb, gen_cpf
for n in ("TEST_ui25_trial", "TEST_ui25_grant"):
    r = mdb.users.insert_one({"cpf": gen_cpf(), "name": n, "status": "pending", "device_id": None,
                              "created_at": datetime.now(timezone.utc).isoformat(), "expires_at": None})
    print(r.inserted_id)
