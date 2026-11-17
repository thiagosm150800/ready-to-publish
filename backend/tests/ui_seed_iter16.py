# Seed an approved TEST_ driver (device unbound) for the iteration 16 UI test; prints cpf and user id.
# Usage: python ui_seed_iter16.py            -> create
#        python ui_seed_iter16.py cleanup ID -> delete that user + their settings/rides
import sys
from datetime import datetime, timezone

from bson import ObjectId

from test_reject_notify_master import gen_cpf, mdb

if len(sys.argv) > 2 and sys.argv[1] == "cleanup":
    uid = sys.argv[2]
    mdb.users.delete_one({"_id": ObjectId(uid)})
    mdb.settings.delete_many({"user_id": uid})
    mdb.rides.delete_many({"user_id": uid})
    print("cleaned", uid)
else:
    cpf = gen_cpf()
    res = mdb.users.insert_one({"cpf": cpf, "name": "TEST_ui16 Motorista", "status": "approved", "device_id": None,
                                "created_at": datetime.now(timezone.utc).isoformat(), "expires_at": None})
    print(cpf, res.inserted_id)
