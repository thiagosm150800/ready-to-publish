"""Delete only test-created rides by explicit id list (file of python list) passed as argv[1]."""
import ast
import os
import sys
from pathlib import Path

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).parent.parent / ".env")
ids = ast.literal_eval(Path(sys.argv[1]).read_text().strip())
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
res = db.rides.delete_many({"_id": {"$in": [ObjectId(i) for i in ids]}})
print("deleted", res.deleted_count, "remaining", db.rides.count_documents({}))
