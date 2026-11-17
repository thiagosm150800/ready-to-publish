# Seed an approved TEST_ driver for iteration 23 UI test (prints cpf and id)
import sys
sys.path.insert(0, "/app/backend/tests")
from datetime import datetime, timezone
from test_blocked_places import mdb, gen_cpf
cpf = gen_cpf()
r = mdb.users.insert_one({"cpf": cpf, "name": "TEST_ui23", "status": "approved", "device_id": None,
                          "created_at": datetime.now(timezone.utc).isoformat(), "expires_at": None})
print(cpf, r.inserted_id)
