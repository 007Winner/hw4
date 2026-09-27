from pathlib import Path
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

try:
    from .agent import run_chat
    from .models import AgentDeps, ChatReply, CustomerContext, PageContext
except ImportError:  # Supports `uvicorn main:app` from inside backend/.
    from agent import run_chat
    from models import AgentDeps, ChatReply, CustomerContext, PageContext

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "campus_customs.db"
PRODUCT_IMAGES = ROOT / "data" / "products"

app = FastAPI(title="Campus Customs API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/images", StaticFiles(directory=PRODUCT_IMAGES), name="product-images")
bearer = HTTPBearer(auto_error=False)


def connection() -> sqlite3.Connection:
    if not DATABASE.exists():
        raise HTTPException(status_code=500, detail="Product database is missing.")
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


def product_from_row(db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    inventory = db.execute(
        "SELECT size, quantity FROM inventory WHERE product_id = ? ORDER BY id",
        (row["product_id"],),
    ).fetchall()
    image_name = Path(row["image_file_path"]).name
    return {
        "product_id": row["product_id"],
        "name": row["name"],
        "garment_type": row["garment_type"],
        "description": row["description"],
        "colors": json.loads(row["colors"]),
        "search_tags": json.loads(row["search_tags"]),
        "image_url": f"/images/{image_name}",
        "price": row["price"],
        "inventory": [dict(item) for item in inventory],
        "total_stock": sum(item["quantity"] for item in inventory),
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/products")
def list_products(search: str = Query(default="")) -> list[dict[str, Any]]:
    db = connection()
    try:
        rows = db.execute(
            "SELECT * FROM catalogue WHERE name LIKE ? OR garment_type LIKE ? OR description LIKE ? ORDER BY name",
            tuple(f"%{search}%" for _ in range(3)),
        ).fetchall()
        return [product_from_row(db, row) for row in rows]
    finally:
        db.close()


@app.get("/api/products/{product_id}")
def get_product(product_id: str) -> dict[str, Any]:
    db = connection()
    try:
        row = db.execute("SELECT * FROM catalogue WHERE product_id = ?", (product_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Product not found.")
        return product_from_row(db, row)
    finally:
        db.close()


class CreateAccountRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    page_context: PageContext | None = None


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> sqlite3.Row | None:
    if credentials is None:
        return None
    try:
        encoded = base64.urlsafe_b64decode(credentials.credentials.encode())
        payload, signature = encoded.rsplit(b".", 1)
        secret = os.environ.get("CAMPUS_CUSTOMS_AUTH_SECRET", "development-only-change-me").encode()
        expected = hmac.new(secret, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return None
        user_id, email = payload.decode().split(":", 1)
    except (ValueError, UnicodeDecodeError, TypeError):
        return None
    db = connection()
    try:
        return db.execute("SELECT id, name, email, first_name, last_name FROM users WHERE id = ? AND lower(email) = lower(?)", (int(user_id), email)).fetchone()
    finally:
        db.close()


def require_user(user: sqlite3.Row | None = Depends(current_user)) -> sqlite3.Row:
    if user is None:
        raise HTTPException(status_code=401, detail="Log in to access chat history.")
    return user


def save_message(user_id: int, role: str, content: str, products: list[dict[str, Any]] | None = None) -> None:
    db = connection()
    try:
        products_json = json.dumps(products) if products is not None else None
        db.execute("INSERT INTO chat_messages (user_id, role, content, products_json) VALUES (?, ?, ?, ?)", (user_id, role, content, products_json))
        db.commit()
    finally:
        db.close()


def hash_password(password: str) -> str:
    """Create a salted, deliberately expensive password hash.

    The salt and parameters are stored with the digest; plaintext passwords
    never enter SQLite or application logs.
    """
    salt = secrets.token_bytes(16)
    n, r, p = 2**15, 8, 1
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=64, maxmem=64 * 1024 * 1024)
    return f"scrypt${n}${r}${p}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        parts = stored.split("$")
        if parts[0] == "scrypt" and len(parts) == 6:
            _, n, r, p, salt_hex, digest_hex = parts
            digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p), dklen=64, maxmem=64 * 1024 * 1024)
            return hmac.compare_digest(digest.hex(), digest_hex)
        # The supplied seed user uses the older three-part PBKDF2-SHA256 format.
        # Keep this compatibility path so the known test account can log in;
        # every newly created account uses the stronger scrypt format above.
        if parts[0] == "pbkdf2_sha256" and len(parts) == 3:
            _, salt, digest_hex = parts
            digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000, 32)
            return hmac.compare_digest(digest.hex(), digest_hex)
        return False
    except (ValueError, TypeError):
        return False


def session_token(user_id: int, email: str) -> str:
    """Return a signed, opaque session token; the signing key stays server-side."""
    secret = os.environ.get("CAMPUS_CUSTOMS_AUTH_SECRET", "development-only-change-me").encode()
    payload = f"{user_id}:{email}".encode()
    signature = hmac.new(secret, payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + b"." + signature).decode()


@app.post("/api/auth/register")
def register(payload: CreateAccountRequest) -> dict[str, str]:
    db = connection()
    try:
        existing = db.execute("SELECT id FROM users WHERE lower(email) = lower(?)", (str(payload.email),)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="An account with that email already exists.")
        full_name = f"{payload.first_name.strip()} {payload.last_name.strip()}"
        cursor = db.execute(
            "INSERT INTO users (name, email, password_hash, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
            (full_name, str(payload.email).lower(), hash_password(payload.password), payload.first_name.strip(), payload.last_name.strip()),
        )
        db.commit()
        return {"token": session_token(cursor.lastrowid, str(payload.email).lower()), "first_name": payload.first_name.strip(), "email": str(payload.email).lower()}
    finally:
        db.close()


@app.post("/api/auth/login")
def login(payload: LoginRequest) -> dict[str, str]:
    db = connection()
    try:
        user = db.execute("SELECT id, email, first_name, password_hash FROM users WHERE lower(email) = lower(?)", (str(payload.email),)).fetchone()
        if user is None or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Email or password is incorrect.")
        return {"token": session_token(user["id"], user["email"]), "first_name": user["first_name"] or user["email"].split("@")[0], "email": user["email"]}
    finally:
        db.close()


@app.post("/api/chat")
def chat(payload: ChatRequest, user: sqlite3.Row | None = Depends(current_user)):
    customer = CustomerContext(user_id=user["id"], name=user["name"], email=user["email"]) if user else CustomerContext()
    result: ChatReply = run_chat(payload.message, AgentDeps(customer=customer, page_context=payload.page_context))
    if user:
        save_message(user["id"], "user", payload.message)
        save_message(user["id"], "assistant", result.reply, [product.model_dump() for product in result.products])
    return result.model_dump()


@app.get("/api/chat/history")
def chat_history(user: sqlite3.Row = Depends(require_user)) -> list[dict[str, Any]]:
    db = connection()
    try:
        messages = db.execute("SELECT role, content, products_json, created_at FROM chat_messages WHERE user_id = ? ORDER BY id", (user["id"],)).fetchall()
        result = []
        for row in messages:
            products = json.loads(row["products_json"]) if row["products_json"] else []
            for product in products:
                if product.get("image_file_path"):
                    product["image_url"] = f"/images/{Path(product['image_file_path']).name}"
            result.append({"role": row["role"], "content": row["content"], "products": products, "created_at": row["created_at"]})
        return result
    finally:
        db.close()
