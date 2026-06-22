"""JWT 用户认证 — 最小可用登录与鉴权."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production-realestate-platform")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
COOKIE_NAME = "access_token"


class LoginRedirect(Exception):
    """未登录访问 HTML 页面时跳转登录."""

    def __init__(self, next_path: str):
        self.next_path = next_path


DEFAULT_ADMIN_USERNAME = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

USERS_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username        VARCHAR(64)  NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(32)  NOT NULL DEFAULT 'operator',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_users_role CHECK (role IN ('admin', 'operator'))
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);
"""

INGESTION_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS ingestion_pipeline_runs (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id    BIGINT NOT NULL REFERENCES trust_products (id),
    data_date           DATE,
    trust_plan_alias    VARCHAR(200),
    source_file         VARCHAR(500),
    created_by          BIGINT NOT NULL REFERENCES users (id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    inserted_monitor_count INT NOT NULL DEFAULT 0,
    inserted_repayment_count INT NOT NULL DEFAULT 0,
    upsert_asset_count  INT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ingestion_pipeline_runs_created_by
    ON ingestion_pipeline_runs (created_by, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ingestion_pipeline_runs_product_date
    ON ingestion_pipeline_runs (trust_product_id, data_date DESC);
"""


class LoginRequest(BaseModel):
    username: str
    password: str


class UserPublic(BaseModel):
    id: int
    username: str
    role: str
    created_at: str


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def resolve_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        return token
    if credentials is not None and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return None


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
        max_age=JWT_EXPIRE_MINUTES * 60,
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def create_access_token(user_id: int, username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def ensure_auth_schema(conn: Connection) -> None:
    for ddl in (USERS_DDL, INGESTION_RUNS_DDL):
        for statement in ddl.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))
    conn.commit()


def ensure_default_admin(conn: Connection) -> None:
    row = conn.execute(
        text("SELECT id FROM users WHERE username = :username"),
        {"username": DEFAULT_ADMIN_USERNAME},
    ).fetchone()
    if row is not None:
        return
    conn.execute(
        text("""
            INSERT INTO users (username, password_hash, role)
            VALUES (:username, :password_hash, 'admin')
        """),
        {
            "username": DEFAULT_ADMIN_USERNAME,
            "password_hash": hash_password(DEFAULT_ADMIN_PASSWORD),
        },
    )
    conn.commit()


def init_auth(engine: Engine) -> None:
    with engine.connect() as conn:
        ensure_auth_schema(conn)
        ensure_default_admin(conn)


def get_user_by_username(conn: Connection, username: str) -> dict | None:
    row = conn.execute(
        text("""
            SELECT id, username, password_hash, role, created_at
            FROM users WHERE username = :username
        """),
        {"username": username},
    ).fetchone()
    if row is None:
        return None
    return {
        "id": int(row.id),
        "username": row.username,
        "password_hash": row.password_hash,
        "role": row.role,
        "created_at": str(row.created_at),
    }


def get_user_by_id(conn: Connection, user_id: int) -> dict | None:
    row = conn.execute(
        text("""
            SELECT id, username, role, created_at
            FROM users WHERE id = :id
        """),
        {"id": user_id},
    ).fetchone()
    if row is None:
        return None
    return {
        "id": int(row.id),
        "username": row.username,
        "role": row.role,
        "created_at": str(row.created_at),
    }


def authenticate_user(conn: Connection, username: str, password: str) -> dict | None:
    user = get_user_by_username(conn, username)
    if user is None or not verify_password(password, user["password_hash"]):
        return None
    return user


def login(conn: Connection, username: str, password: str) -> dict:
    user = authenticate_user(conn, username, password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user["id"], user["username"], user["role"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRE_MINUTES * 60,
    }


def user_from_token(conn: Connection, token: str) -> dict:
    payload = decode_access_token(token)
    user_id = int(payload["sub"])
    user = get_user_by_id(conn, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def make_current_user_dependency(engine: Engine):
    def get_current_user(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    ) -> dict:
        token = resolve_token(request, credentials)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        with engine.connect() as conn:
            return user_from_token(conn, token)

    return get_current_user


def make_page_user_dependency(engine: Engine):
    def get_page_user(
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    ) -> dict:
        token = resolve_token(request, credentials)
        if not token:
            next_path = request.url.path
            if request.url.query:
                next_path += "?" + request.url.query
            raise LoginRedirect(next_path)
        with engine.connect() as conn:
            return user_from_token(conn, token)

    return get_page_user


def record_ingestion_run(
    conn: Connection,
    *,
    trust_product_id: int,
    data_date,
    trust_plan_alias: str | None,
    source_file: str,
    created_by: int,
    inserted_monitor_count: int,
    inserted_repayment_count: int,
    upsert_asset_count: int,
    skipped_sheet_count: int = 0,
    failed_sheet_count: int = 0,
    error_message: str | None = None,
    trust_product_name: str | None = None,
) -> tuple[int, str]:
    row = conn.execute(
        text("""
            INSERT INTO ingestion_pipeline_runs (
                trust_product_id, trust_product_name, data_date, trust_plan_alias, source_file,
                created_by, inserted_monitor_count, inserted_repayment_count,
                upsert_asset_count, skipped_sheet_count, failed_sheet_count, error_message
            ) VALUES (
                :trust_product_id, :trust_product_name, :data_date, :trust_plan_alias, :source_file,
                :created_by, :inserted_monitor_count, :inserted_repayment_count,
                :upsert_asset_count, :skipped_sheet_count, :failed_sheet_count, :error_message
            )
            RETURNING id, created_at
        """),
        {
            "trust_product_id": trust_product_id,
            "trust_product_name": trust_product_name,
            "data_date": data_date,
            "trust_plan_alias": trust_plan_alias,
            "source_file": source_file,
            "created_by": created_by,
            "inserted_monitor_count": inserted_monitor_count,
            "inserted_repayment_count": inserted_repayment_count,
            "upsert_asset_count": upsert_asset_count,
            "skipped_sheet_count": skipped_sheet_count,
            "failed_sheet_count": failed_sheet_count,
            "error_message": error_message,
        },
    ).fetchone()
    return int(row.id), str(row.created_at)


def record_sheet_run(
    conn: Connection,
    *,
    pipeline_run_id: int,
    source_file_name: str,
    source_sheet_name: str,
    sheet_type: str,
    data_date,
    row_count: int,
    amount_sum: float | None,
    action: str,
    message: str | None,
    trust_product_id: int | None = None,
    trust_product_name: str | None = None,
) -> None:
    parsed_date = None
    if data_date:
        if isinstance(data_date, str):
            parsed_date = date.fromisoformat(data_date[:10])
        else:
            parsed_date = data_date
    conn.execute(
        text("""
            INSERT INTO ingestion_sheet_runs (
                pipeline_run_id, trust_product_id, trust_product_name,
                source_file_name, source_sheet_name, sheet_type,
                data_date, row_count, amount_sum, action, message
            ) VALUES (
                :pipeline_run_id, :trust_product_id, :trust_product_name,
                :source_file_name, :source_sheet_name, :sheet_type,
                :data_date, :row_count, :amount_sum, :action, :message
            )
        """),
        {
            "pipeline_run_id": pipeline_run_id,
            "trust_product_id": trust_product_id,
            "trust_product_name": trust_product_name,
            "source_file_name": source_file_name,
            "source_sheet_name": source_sheet_name,
            "sheet_type": sheet_type,
            "data_date": parsed_date,
            "row_count": row_count,
            "amount_sum": amount_sum,
            "action": action,
            "message": message,
        },
    )
