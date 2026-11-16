"""Iteration 5 helper: verify motorista settings + leftover test accounts (read-only)."""
import os
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
API = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"

r = requests.post(f"{API}/auth/login", json={"email": "motorista@teste.com", "password": "teste1234"})
tok = r.json()["access_token"]
s = requests.get(f"{API}/settings", headers={"Authorization": f"Bearer {tok}"}).json()
print("motorista settings:", {k: s.get(k) for k in ("auto_accept", "sync_99_enabled", "schedule_enabled", "alert_enabled")})
print("leftover test users:", list(db.users.find({"email": {"$regex": "^test_(ui|rl)_"}}, {"email": 1, "_id": 0})))
print("login_attempts docs:", db.login_attempts.count_documents({}),
      "motorista attempts:", db.login_attempts.count_documents({"email": "motorista@teste.com"}))
print("indexes login_attempts:", list(db.login_attempts.index_information().keys()))
