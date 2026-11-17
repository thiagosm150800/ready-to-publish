import asyncio
import hmac
from contextlib import suppress
from fastapi import FastAPI, APIRouter, Query, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from jwt.exceptions import InvalidTokenError
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, IndexModel
from bson import ObjectId
import os
import re
import logging
from pathlib import Path
from pydantic import BaseModel, Field, BeforeValidator, ConfigDict, field_validator
from typing import List, Optional, Annotated, Literal, Dict
from datetime import datetime, timezone, timedelta


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]
JWT_SECRET = os.environ['JWT_SECRET']
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')  # empty = admin area disabled, API still boots
JWT_ALGORITHM = "HS256"
TOKEN_DAYS = 30  # drivers stay signed in; admin can block at any time (checked on every request)
ADMIN_TOKEN_HOURS = 12
bearer = HTTPBearer(auto_error=False)

INDEXES: dict[str, list[IndexModel]] = {
    "rides": [
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"),
        IndexModel([("user_id", ASCENDING), ("accepted", ASCENDING), ("created_at", DESCENDING)], name="user_accepted_created"),
    ],
    "settings": [IndexModel([("user_id", ASCENDING)], name="user_id", unique=True)],
    "users": [
        IndexModel([("cpf", ASCENDING)], name="cpf", unique=True, partialFilterExpression={"cpf": {"$type": "string"}}),
        IndexModel([("status", ASCENDING), ("created_at", DESCENDING)], name="status_created"),
    ],
    "login_attempts": [
        IndexModel([("key", ASCENDING), ("at", DESCENDING)], name="key_at"),
        IndexModel([("expires_at", ASCENDING)], name="ttl", expireAfterSeconds=0),
    ],
}


async def ensure_indexes() -> None:
    # Legacy indexes from earlier versions (single-user / email login)
    for coll, name in (("settings", "key"), ("rides", "created_at_desc"), ("rides", "accepted_created"),
                       ("users", "email"), ("login_attempts", "email_at")):
        with suppress(Exception):
            await db[coll].drop_index(name)
    for collection, models in INDEXES.items():
        for model in models:
            try:
                await db[collection].create_indexes([model])
            except Exception as exc:
                logging.getLogger(__name__).error("ensure_indexes(%s.%s): %s", collection, model.document["name"], exc)


app = FastAPI()


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


api_router = APIRouter(prefix="/api")

# ---------- Mongo helpers ----------
PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: dict):
        return cls.model_validate(doc)

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True, exclude={"id"})
        data.pop("_id", None)
        return data

    def to_api(self) -> dict:
        return self.model_dump(by_alias=False)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- CPF ----------
def clean_cpf(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def valid_cpf(cpf: str) -> bool:
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for n in (9, 10):
        s = sum(int(cpf[i]) * (n + 1 - i) for i in range(n))
        d = (s * 10) % 11 % 10
        if d != int(cpf[n]):
            return False
    return True


def mask_cpf(cpf: str) -> str:
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}" if len(cpf) == 11 else cpf


# ---------- Models ----------
AppKey = Literal["rapido", "moove"]
TEXT_LIST_FIELDS = ["accept_texts", "reject_texts", "finish_texts"]


class AppFilters(BaseModel):
    enabled: bool = False
    min_price_per_km: float = 2.0
    min_fare: float = 8.0
    max_pickup_km: float = 4.0
    accept_texts: List[str] = ["Aceitar", "Aceitar corrida", "Accept"]
    # Auto-reject: tap the reject button when the offer fails the filters
    reject_enabled: bool = False
    reject_texts: List[str] = ["Recusar"]
    # Ride end: a tap on one of these buttons puts both bots back online
    finish_texts: List[str] = ["Finalizar", "Encerrar", "Concluir", "Cancelar corrida"]
    target_package: str


def default_apps() -> Dict[str, AppFilters]:
    return {"rapido": AppFilters(target_package="rapido"), "moove": AppFilters(target_package="moove")}


class Settings(BaseDocument):
    user_id: str
    apps: Dict[str, AppFilters] = Field(default_factory=default_apps)
    # Working hours (days: 0=Sunday..6=Saturday; times HH:MM, may cross midnight)
    schedule_enabled: bool = False
    schedule_start: str = "06:00"
    schedule_end: str = "22:00"
    schedule_days: List[int] = [0, 1, 2, 3, 4, 5, 6]
    alert_enabled: bool = True
    notify_enabled: bool = True  # phone notification with price/km on every auto-accept
    exclusive_enabled: bool = True  # after an accept, the other app's bot goes off-line until the ride ends


class AppFiltersUpdate(BaseModel):
    enabled: Optional[bool] = None
    min_price_per_km: Optional[float] = Field(default=None, ge=0)
    min_fare: Optional[float] = Field(default=None, ge=0)
    max_pickup_km: Optional[float] = Field(default=None, ge=0)
    accept_texts: Optional[List[str]] = None
    reject_enabled: Optional[bool] = None
    reject_texts: Optional[List[str]] = None
    finish_texts: Optional[List[str]] = None
    target_package: Optional[str] = None


TIME_RE = r"^([01]\d|2[0-3]):[0-5]\d$"


class SettingsUpdate(BaseModel):
    apps: Optional[Dict[AppKey, AppFiltersUpdate]] = None
    schedule_enabled: Optional[bool] = None
    schedule_start: Optional[str] = Field(default=None, pattern=TIME_RE)
    schedule_end: Optional[str] = Field(default=None, pattern=TIME_RE)
    schedule_days: Optional[List[Annotated[int, Field(ge=0, le=6)]]] = None
    alert_enabled: Optional[bool] = None
    notify_enabled: Optional[bool] = None
    exclusive_enabled: Optional[bool] = None


class Ride(BaseDocument):
    user_id: Optional[str] = None
    app: str = "rapido"
    price: float
    trip_km: float
    pickup_km: float = 0
    price_per_km: float
    accepted: bool
    reasons: List[str] = []
    source: str = "rapidocar"
    created_at: str = Field(default_factory=now_iso)


class RideIn(BaseModel):
    app: AppKey = "rapido"
    price: float
    trip_km: float
    pickup_km: float = 0
    price_per_km: Optional[float] = None
    accepted: bool
    reasons: List[str] = []
    source: Literal["rapidocar", "moovecar"] = "rapidocar"
    created_at: Optional[str] = None

    @field_validator("created_at")
    @classmethod
    def _valid_date(cls, v):
        if v is not None:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v


UserStatus = Literal["pending", "approved", "blocked"]


class User(BaseDocument):
    cpf: str
    name: str = ""
    status: UserStatus = "pending"
    created_at: str = Field(default_factory=now_iso)
    status_changed_at: Optional[str] = None
    last_login_at: Optional[str] = None
    expires_at: Optional[str] = None  # None = no time limit
    device_id: Optional[str] = None  # the only phone allowed to use this CPF
    device_bound_at: Optional[str] = None

    @property
    def expired(self) -> bool:
        return bool(self.expires_at) and self.expires_at <= now_iso()

    def public(self) -> dict:
        return {"id": self.id, "cpf": mask_cpf(self.cpf), "name": self.name, "status": self.status,
                "expires_at": self.expires_at}

    def admin_view(self) -> dict:
        return {**self.public(), "created_at": self.created_at, "status_changed_at": self.status_changed_at,
                "last_login_at": self.last_login_at, "expired": self.expired,
                "has_device": bool(self.device_id), "device_bound_at": self.device_bound_at}


class CpfLoginIn(BaseModel):
    cpf: str = Field(min_length=11, max_length=14)
    device_id: Optional[str] = Field(default=None, min_length=8, max_length=128)


class AdminLoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class AdminUserUpdate(BaseModel):
    status: Optional[UserStatus] = None
    name: Optional[str] = Field(default=None, max_length=80)
    # Approve/renew for N days from now; 0 = no time limit.
    access_days: Optional[int] = Field(default=None, ge=0, le=3650)
    # True = unlink the current phone so the driver can sign in on a new one.
    reset_device: Optional[bool] = None


# ---------- Rate limiting (stored in Mongo, auto-expires) ----------
WINDOW = timedelta(minutes=15)


async def check_limit(key: str, max_fails: int, msg: str):
    since = (datetime.now(timezone.utc) - WINDOW).isoformat()
    if await db.login_attempts.count_documents({"key": key, "at": {"$gte": since}}) >= max_fails:
        raise HTTPException(status_code=429, detail=msg)


async def record_fail(key: str):
    now = datetime.now(timezone.utc)
    await db.login_attempts.insert_one({"key": key, "at": now.isoformat(), "expires_at": now + WINDOW})


def client_ip(request: Request) -> str:
    # Cloudflare sets CF-Connecting-IP to the real client (callers can't spoof it through CF).
    cf = request.headers.get("cf-connecting-ip", "").strip()
    if cf:
        return cf
    # Chain: <caller-supplied...>, <real client>, <cloudflare>, <load balancer> -> skip our 2 proxy hops.
    fwd = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if len(fwd) >= 3:
        return fwd[-3]
    return fwd[0] if fwd else (request.client.host if request.client else "unknown")


# ---------- Tokens ----------
def issue_token(sub: str, role: str, ttl: timedelta, **extra) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": sub, "role": role, "iat": now, "exp": now + ttl, **extra}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(credentials: Optional[HTTPAuthorizationCredentials], role: str) -> dict:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Faça login para continuar")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Sessão expirada. Entre novamente.")
    if payload.get("role") != role or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Sessão inválida")
    return payload


async def current_user(credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer)]) -> User:
    payload = decode_token(credentials, "driver")
    uid = payload["sub"]
    if not ObjectId.is_valid(uid):
        raise HTTPException(status_code=401, detail="Sessão inválida")
    doc = await db.users.find_one({"_id": ObjectId(uid)})
    if not doc or "cpf" not in doc:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    user = User.from_mongo(doc)
    if user.status != "approved":
        # Admin revoked access -> app signs out
        raise HTTPException(status_code=401, detail="Seu acesso não está liberado")
    if user.expired:
        raise HTTPException(status_code=401, detail="Seu prazo de acesso venceu. Fale com o responsável.")
    if not user.device_id or payload.get("dev") != user.device_id:
        raise HTTPException(status_code=401, detail="Este CPF está liberado em outro aparelho")
    return user


async def current_admin(credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer)]) -> str:
    return decode_token(credentials, "admin")["sub"]


CurrentUser = Annotated[User, Depends(current_user)]
CurrentAdmin = Annotated[str, Depends(current_admin)]


# ---------- Settings ----------
async def get_settings(uid: str) -> Settings:
    doc = await db.settings.find_one({"user_id": uid})
    if doc and "apps" not in doc:
        # Legacy single-app settings -> RapidoCar filters
        apps = default_apps()
        for f in ("min_price_per_km", "min_fare", "max_pickup_km", "accept_texts", "target_package"):
            if f in doc:
                setattr(apps["rapido"], f, doc[f])
        apps["rapido"].enabled = bool(doc.get("auto_accept", False))
        await db.settings.update_one({"_id": doc["_id"]}, {"$set": {"apps": {k: v.model_dump() for k, v in apps.items()}}})
        doc = await db.settings.find_one({"user_id": uid})
    if doc:
        return Settings.from_mongo(doc)
    s = Settings(user_id=uid)
    await db.settings.update_one({"user_id": uid}, {"$setOnInsert": s.to_mongo()}, upsert=True)
    return Settings.from_mongo(await db.settings.find_one({"user_id": uid}))


def settings_api(s: Settings) -> dict:
    data = s.to_api()
    data.pop("user_id", None)
    return data


# ---------- Routes: driver auth ----------
@api_router.get("/")
async def root():
    return {"message": "RapidoChecker API"}


@api_router.post("/auth/cpf")
async def login_cpf(body: CpfLoginIn, request: Request):
    """CPF-only login. New CPFs are created as 'pending' and need admin approval."""
    ip_key = f"ip:{client_ip(request)}"
    cpf = clean_cpf(body.cpf)
    if not valid_cpf(cpf):
        # Only malformed CPFs count as failures (pending drivers re-checking never lock others out).
        await check_limit(ip_key, 20, "Muitas tentativas. Aguarde 15 minutos.")
        await record_fail(ip_key)
        raise HTTPException(status_code=422, detail="CPF inválido")
    if not body.device_id:
        raise HTTPException(status_code=426, detail="Atualize o app para a versão mais recente.")
    doc = await db.users.find_one({"cpf": cpf})
    if not doc:
        # Creating new access requests is limited per IP to avoid spam.
        await check_limit(f"new:{client_ip(request)}", 10, "Muitos cadastros. Aguarde 15 minutos.")
        # The phone that asks for access is the one that gets approved.
        user = User(cpf=cpf, device_id=body.device_id, device_bound_at=now_iso())
        with suppress(DuplicateKeyError):
            await db.users.insert_one(user.to_mongo())
        await record_fail(f"new:{client_ip(request)}")
        return {"status": "pending"}
    user = User.from_mongo(doc)
    if user.status != "approved":
        return {"status": user.status}
    if user.expired:
        return {"status": "expired"}
    if not user.device_id:
        # No phone linked yet (older account or admin unlinked it): bind this one atomically.
        res = await db.users.update_one({"_id": doc["_id"], "device_id": None},
                                        {"$set": {"device_id": body.device_id, "device_bound_at": now_iso()}})
        if not res.modified_count:
            user = User.from_mongo(await db.users.find_one({"_id": doc["_id"]}))
        else:
            user.device_id = body.device_id
    if user.device_id != body.device_id:
        return {"status": "other_device"}
    await db.users.update_one({"_id": doc["_id"]}, {"$set": {"last_login_at": now_iso()}})
    return {"status": "approved",
            "access_token": issue_token(user.id, "driver", timedelta(days=TOKEN_DAYS), dev=user.device_id),
            "token_type": "bearer", "user": user.public()}


@api_router.get("/auth/me")
async def me(user: CurrentUser):
    return user.public()


@api_router.delete("/auth/account")
async def delete_account(user: CurrentUser):
    await db.rides.delete_many({"user_id": user.id})
    await db.settings.delete_many({"user_id": user.id})
    await db.users.delete_one({"_id": ObjectId(user.id)})
    return {"deleted": True}


# ---------- Routes: settings & rides ----------
@api_router.get("/settings")
async def read_settings(user: CurrentUser):
    return settings_api(await get_settings(user.id))


@api_router.put("/settings")
async def update_settings(body: SettingsUpdate, user: CurrentUser):
    await get_settings(user.id)
    changes = body.model_dump(exclude_none=True, exclude={"apps"})
    for key, upd in (body.apps or {}).items():
        for f, v in upd.model_dump(exclude_none=True).items():
            if f in TEXT_LIST_FIELDS:
                v = [t.strip() for t in v if t.strip()]
                if f == "reject_texts" and not v:
                    raise HTTPException(status_code=422, detail="Informe o texto do botão Recusar.")
                if f == "finish_texts" and not v:
                    raise HTTPException(status_code=422, detail="Informe o texto do botão Finalizar.")
            if f == "target_package":
                v = v.strip()
                if not v:
                    raise HTTPException(status_code=422, detail="Informe o pacote do app.")
            changes[f"apps.{key}.{f}"] = v
    if changes:
        await db.settings.update_one({"user_id": user.id}, {"$set": changes})
    return settings_api(await get_settings(user.id))


def to_utc_iso(value: str) -> str:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


@api_router.post("/rides/bulk")
async def add_rides(items: List[RideIn], user: CurrentUser):
    docs = []
    for r in items:
        ppk = r.price_per_km if r.price_per_km is not None else (round(r.price / r.trip_km, 2) if r.trip_km > 0 else 0)
        ride = Ride(user_id=user.id, app=r.app, price=r.price, trip_km=r.trip_km, pickup_km=r.pickup_km,
                    price_per_km=ppk, accepted=r.accepted, reasons=r.reasons, source=r.source,
                    created_at=to_utc_iso(r.created_at) if r.created_at else now_iso())
        docs.append(ride.to_mongo())
    if docs:
        await db.rides.insert_many(docs)
    return {"inserted": len(docs)}


@api_router.get("/rides")
async def list_rides(user: CurrentUser, status: Literal["all", "accepted", "rejected"] = "all",
                     app_key: Literal["all", "rapido", "moove"] = Query("all", alias="app"),
                     limit: int = Query(100, ge=1, le=500)):
    q: dict = {"user_id": user.id, "source": {"$ne": "simulador"}}
    if status != "all":
        q["accepted"] = status == "accepted"
    if app_key != "all":
        q["app"] = app_key
    docs = await db.rides.find(q).sort("created_at", -1).limit(limit).to_list(limit)
    return [Ride.from_mongo(d).to_api() for d in docs]


@api_router.get("/rides/summary")
async def rides_summary(user: CurrentUser, since: str = Query(..., description="Start of the driver's local day (ISO)")):
    """Accepted/rejected counts per app since the given moment (the app sends local midnight)."""
    try:
        start = to_utc_iso(since)
    except ValueError:
        raise HTTPException(status_code=422, detail="Data inválida")
    out = {k: {"accepted": 0, "rejected": 0, "earned": 0.0} for k in ("rapido", "moove")}
    pipeline = [
        {"$match": {"user_id": user.id, "created_at": {"$gte": start}, "app": {"$in": list(out)}}},
        {"$group": {"_id": {"app": "$app", "accepted": "$accepted"}, "n": {"$sum": 1}, "earned": {"$sum": "$price"}}},
    ]
    async for g in db.rides.aggregate(pipeline):
        o = out[g["_id"]["app"]]
        if g["_id"]["accepted"]:
            o["accepted"] = g["n"]
            o["earned"] = round(g["earned"], 2)
        else:
            o["rejected"] = g["n"]
    return out


@api_router.delete("/rides")
async def clear_rides(user: CurrentUser):
    res = await db.rides.delete_many({"user_id": user.id})
    return {"deleted": res.deleted_count}


# ---------- Routes: admin (only the owner, protected by ADMIN_PASSWORD) ----------
@api_router.post("/admin/login")
async def admin_login(body: AdminLoginIn, request: Request):
    # Global limit (not per IP, so spoofed/rotated IPs can't brute-force the password).
    key = "admin:global"
    await check_limit(key, 10, "Muitas tentativas. Aguarde 15 minutos.")
    if not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Área do administrador não configurada")
    if not hmac.compare_digest(body.password.encode(), ADMIN_PASSWORD.encode()):
        await record_fail(key)
        raise HTTPException(status_code=401, detail="Senha de administrador incorreta")
    await db.login_attempts.delete_many({"key": key})
    return {"access_token": issue_token("admin", "admin", timedelta(hours=ADMIN_TOKEN_HOURS)), "token_type": "bearer"}


@api_router.get("/admin/users")
async def admin_users(_: CurrentAdmin, status: Literal["all", "pending", "approved", "expired", "blocked"] = "all"):
    now = now_iso()
    base: dict = {"cpf": {"$type": "string"}}
    queries = {
        "pending": {**base, "status": "pending"},
        "blocked": {**base, "status": "blocked"},
        "approved": {**base, "status": "approved", "$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}]},
        "expired": {**base, "status": "approved", "expires_at": {"$ne": None, "$lte": now}},
    }
    q = queries.get(status, base)
    sort = [("expires_at", -1)] if status == "expired" else [("created_at", -1)]
    docs = await db.users.find(q).sort(sort).to_list(1000)
    counts = {s: await db.users.count_documents(cq) for s, cq in queries.items()}
    return {"users": [User.from_mongo(d).admin_view() for d in docs], "counts": counts}


@api_router.patch("/admin/users/{user_id}")
async def admin_update_user(user_id: str, body: AdminUserUpdate, _: CurrentAdmin):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=404, detail="Motorista não encontrado")
    changes = body.model_dump(exclude_none=True)
    days = changes.pop("access_days", None)
    if changes.pop("reset_device", False):
        changes["device_id"] = None
        changes["device_bound_at"] = None
    if days is not None:
        changes["status"] = "approved"
        changes["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat() if days else None
    if "status" in changes:
        changes["status_changed_at"] = now_iso()
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    if changes:
        res = await db.users.update_one({"_id": ObjectId(user_id), "cpf": {"$type": "string"}}, {"$set": changes})
        if not res.matched_count:
            raise HTTPException(status_code=404, detail="Motorista não encontrado")
    doc = await db.users.find_one({"_id": ObjectId(user_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Motorista não encontrado")
    return User.from_mongo(doc).admin_view()


@api_router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, _: CurrentAdmin):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=404, detail="Motorista não encontrado")
    res = await db.users.delete_one({"_id": ObjectId(user_id), "cpf": {"$type": "string"}})
    if not res.deleted_count:
        raise HTTPException(status_code=404, detail="Motorista não encontrado")
    await db.rides.delete_many({"user_id": user_id})
    await db.settings.delete_many({"user_id": user_id})
    return {"deleted": True}


# ---------- Privacy policy (public) ----------
PRIVACY_HTML = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>RapidoChecker - Política de Privacidade</title>
<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:0 auto;padding:24px;line-height:1.6;color:#111}
h1{font-size:26px}h2{font-size:18px;margin-top:28px}</style></head><body>
<h1>Política de Privacidade - RapidoChecker</h1><p>Última atualização: junho de 2026</p>
<h2>1. O que o app faz</h2><p>O RapidoChecker ajuda motoristas a aceitar automaticamente ofertas de corrida do RapidoCar e do
MooveCar que atendem aos filtros definidos pelo próprio motorista (preço por km, valor mínimo, distância e horário).</p>
<h2>2. Uso do Serviço de Acessibilidade (Android)</h2><p>Com a sua permissão, o app usa a API de Acessibilidade do Android
para <b>ler os textos exibidos</b> nas telas do RapidoCar e do MooveCar (valor da corrida, distâncias e nomes de botões)
e para <b>tocar no botão "Aceitar"</b> em seu nome. O serviço só atua nesses apps, só quando você ativa, e pode ser desligado
a qualquer momento em Configurações &gt; Acessibilidade. O app não lê senhas, mensagens, conteúdo de outros apps nem o que você digita.</p>
<h2>3. Dados coletados</h2><ul><li>Conta: CPF (usado para identificar e liberar o acesso do motorista).</li>
<li>Configurações: seus filtros, horários e textos de botões.</li>
<li>Histórico de ofertas: app, valor, distâncias, preço por km, decisão (aceita/recusada), motivo e horário.</li></ul>
<p>Não coletamos localização, contatos, fotos, dados do passageiro nem dados de pagamento.</p>
<h2>4. Como usamos</h2><p>Somente para liberar seu acesso e aplicar seus filtros. Não vendemos nem compartilhamos
seus dados com terceiros e não usamos os dados para publicidade.</p>
<h2>5. Armazenamento e segurança</h2><p>Os dados ficam em servidor protegido e são transmitidos por conexão criptografada (HTTPS).
Cada motorista só acessa os próprios dados.</p>
<h2>6. Seus direitos (LGPD)</h2><p>Você pode apagar seu histórico ou excluir sua conta e todos os dados pelo próprio app
(Conta &gt; Excluir conta).</p>
<h2>7. Aviso</h2><p>O RapidoChecker não é afiliado ao RapidoCar nem ao MooveCar. O uso de automação pode estar sujeito aos termos
desses apps; o motorista é responsável pelo uso.</p>
</body></html>"""


@api_router.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
async def privacy():
    return PRIVACY_HTML


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def start_index_build():
    app.state.index_task = asyncio.create_task(ensure_indexes())


@app.on_event("shutdown")
async def shutdown_db_client():
    app.state.index_task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.index_task
    client.close()
