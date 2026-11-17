# RapidoChecker: web admin panel GET /api/painel (headers, content) + trial status rules (iteration 26)
import os
import time
from datetime import datetime, timezone, timedelta

import jwt
import pytest
import requests
from bson import ObjectId

from test_admin_trial import API, JWT_SECRET, mdb, make_user


@pytest.fixture(scope="module")
def admin_h():
    now = int(time.time())
    tok = jwt.encode({"sub": "admin", "role": "admin", "iat": now, "exp": now + 3600}, JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def created():
    ids = []
    yield ids
    for uid in ids:
        mdb.users.delete_one({"_id": ObjectId(uid)})


# Panel page served with security headers
class TestPainelPage:
    def test_painel_html_and_headers(self):
        r = requests.get(f"{API}/painel", timeout=15)
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "Painel do administrador" in r.text and 'id="loginForm"' in r.text
        assert r.headers.get("x-frame-options") == "DENY"
        assert "no-store" in r.headers.get("cache-control", "")
        csp = r.headers.get("content-security-policy", "")
        assert "frame-ancestors 'none'" in csp and "connect-src 'self'" in csp

    def test_painel_no_innerhtml(self):
        # Public response gets a Cloudflare challenge snippet (uses innerHTML) appended at the edge; check app source only
        src = open("/app/backend/admin_web.html", encoding="utf-8").read()
        assert "innerHTML" not in src and "insertAdjacentHTML" not in src

    def test_admin_users_requires_auth(self):
        assert requests.get(f"{API}/admin/users", timeout=15).status_code == 401

    def test_invalid_token_401(self):
        r = requests.get(f"{API}/admin/users", headers={"Authorization": "Bearer abc.def.ghi"}, timeout=15)
        assert r.status_code == 401

    def test_wrong_password_401(self):
        r = requests.post(f"{API}/admin/login", json={"password": "TEST_wrong_pw_xyz"}, timeout=15)
        assert r.status_code == 401


# Backend-side trial guard: trial should not be granted to approved-active or blocked users (UI hides it)
class TestTrialStatusGuard:
    def test_trial_on_active_approved(self, admin_h, created):
        exp = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        uid, _ = make_user(created, status="approved", expires_at=exp)
        r = requests.patch(f"{API}/admin/users/{uid}", json={"trial": True}, headers=admin_h, timeout=15)
        doc = mdb.users.find_one({"_id": ObjectId(uid)})
        print("approved-active trial ->", r.status_code, doc.get("expires_at"))
        assert r.status_code in (409, 422), f"backend granted trial on active 30-day user: {r.status_code}, expires_at now {doc.get('expires_at')}"

    def test_trial_on_blocked(self, admin_h, created):
        uid, _ = make_user(created, status="blocked")
        r = requests.patch(f"{API}/admin/users/{uid}", json={"trial": True}, headers=admin_h, timeout=15)
        doc = mdb.users.find_one({"_id": ObjectId(uid)})
        print("blocked trial ->", r.status_code, doc.get("status"))
        assert r.status_code in (409, 422), f"backend unblocked user via trial: {r.status_code}, status {doc.get('status')}"
