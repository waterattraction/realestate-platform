"""信托产品主数据 V1 Lite — 查询 / 新增 / 更新."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection

DISPLAY_TZ = ZoneInfo("Asia/Shanghai")

STATUS_ISSUED = "issued"
STATUS_ENDED = "ended"

STATUS_LABELS = {
    STATUS_ISSUED: "已发行",
    STATUS_ENDED: "结束",
}

_LEGACY_TO_CANONICAL = {
    "draft": STATUS_ISSUED,
    "raising": STATUS_ISSUED,
    "active": STATUS_ISSUED,
    "issued": STATUS_ISSUED,
    "completed": STATUS_ENDED,
    "closed": STATUS_ENDED,
    "ended": STATUS_ENDED,
}


def normalize_status(raw: str | None) -> str:
    if not raw:
        return STATUS_ISSUED
    return _LEGACY_TO_CANONICAL.get(str(raw).strip().lower(), STATUS_ISSUED)


def status_label(raw: str | None) -> str:
    return STATUS_LABELS[normalize_status(raw)]


def _fmt_ts(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(DISPLAY_TZ).strftime("%Y-%m-%d %H:%M")
    return str(value)


def _fmt_date(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _row_to_dict(row, *, asset_pool_name: str | None = None) -> dict:
    canonical = normalize_status(row.status)
    return {
        "id": int(row.id),
        "asset_pool_id": int(row.asset_pool_id),
        "asset_pool_name": asset_pool_name or getattr(row, "asset_pool_name", None),
        "code": row.code,
        "name": row.name,
        "status": canonical,
        "status_label": STATUS_LABELS[canonical],
        "trust_end_date": _fmt_date(getattr(row, "trust_end_date", None)),
        "created_at": _fmt_ts(row.created_at),
        "updated_at": _fmt_ts(row.updated_at),
    }


def _parse_write_status(value) -> str:
    if value in (None, ""):
        raise HTTPException(status_code=400, detail="status is required")
    status = str(value).strip().lower()
    if status not in (STATUS_ISSUED, STATUS_ENDED):
        raise HTTPException(status_code=400, detail="status must be issued or ended")
    return status


def _parse_trust_end_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    text_val = str(value).strip()
    if not text_val:
        return None
    try:
        return date.fromisoformat(text_val)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid trust_end_date, expected YYYY-MM-DD",
        ) from exc


def _require_str(value, *, field: str, max_len: int) -> str:
    if value in (None, ""):
        raise HTTPException(status_code=400, detail=f"{field} is required")
    text_val = str(value).strip()
    if not text_val:
        raise HTTPException(status_code=400, detail=f"{field} is required")
    if len(text_val) > max_len:
        raise HTTPException(status_code=400, detail=f"{field} length must be <= {max_len}")
    return text_val


def _require_int(value, *, field: str) -> int:
    if value in (None, ""):
        raise HTTPException(status_code=400, detail=f"{field} is required")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field}") from exc


def _assert_asset_pool_exists(conn: Connection, asset_pool_id: int) -> str:
    row = conn.execute(
        text("SELECT id, name FROM asset_pools WHERE id = :id"),
        {"id": asset_pool_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Asset pool not found")
    return row.name


def _assert_code_unique(conn: Connection, code: str, *, exclude_id: int | None = None) -> None:
    row = conn.execute(
        text("SELECT id FROM trust_products WHERE code = :code"),
        {"code": code},
    ).fetchone()
    if row is not None and (exclude_id is None or int(row.id) != exclude_id):
        raise HTTPException(status_code=409, detail="Product code already exists")


def _assert_name_unique(conn: Connection, name: str, *, exclude_id: int | None = None) -> None:
    row = conn.execute(
        text("SELECT id FROM trust_products WHERE name = :name"),
        {"name": name},
    ).fetchone()
    if row is not None and (exclude_id is None or int(row.id) != exclude_id):
        raise HTTPException(status_code=409, detail="Product name already exists")


def fetch_asset_pools(conn: Connection) -> list[dict]:
    rows = conn.execute(text("""
        SELECT id, code, name
        FROM asset_pools
        ORDER BY id
    """))
    return [{"id": r.id, "code": r.code, "name": r.name} for r in rows]


def fetch_manage_list(conn: Connection) -> list[dict]:
    rows = conn.execute(text("""
        SELECT
            tp.id,
            tp.asset_pool_id,
            tp.code,
            tp.name,
            tp.status,
            tp.trust_end_date,
            tp.created_at,
            tp.updated_at,
            ap.name AS asset_pool_name
        FROM trust_products tp
        INNER JOIN asset_pools ap ON ap.id = tp.asset_pool_id
        ORDER BY tp.id
    """))
    return [_row_to_dict(r, asset_pool_name=r.asset_pool_name) for r in rows]


def fetch_by_id(conn: Connection, product_id: int) -> dict | None:
    row = conn.execute(
        text("""
            SELECT
                tp.id,
                tp.asset_pool_id,
                tp.code,
                tp.name,
                tp.status,
                tp.trust_end_date,
                tp.created_at,
                tp.updated_at,
                ap.name AS asset_pool_name
            FROM trust_products tp
            INNER JOIN asset_pools ap ON ap.id = tp.asset_pool_id
            WHERE tp.id = :id
        """),
        {"id": product_id},
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(row, asset_pool_name=row.asset_pool_name)


def create_trust_product(conn: Connection, body: dict) -> dict:
    asset_pool_id = _require_int(body.get("asset_pool_id"), field="asset_pool_id")
    code = _require_str(body.get("code"), field="code", max_len=32)
    name = _require_str(body.get("name"), field="name", max_len=200)
    status = _parse_write_status(body.get("status"))
    trust_end_date = _parse_trust_end_date(body.get("trust_end_date"))

    pool_name = _assert_asset_pool_exists(conn, asset_pool_id)
    _assert_code_unique(conn, code)
    _assert_name_unique(conn, name)

    row = conn.execute(
        text("""
            INSERT INTO trust_products (
                asset_pool_id, code, name, status, trust_end_date
            ) VALUES (
                :asset_pool_id, :code, :name, :status, :trust_end_date
            )
            RETURNING
                id, asset_pool_id, code, name, status, trust_end_date,
                created_at, updated_at
        """),
        {
            "asset_pool_id": asset_pool_id,
            "code": code,
            "name": name,
            "status": status,
            "trust_end_date": trust_end_date,
        },
    ).fetchone()
    return _row_to_dict(row, asset_pool_name=pool_name)


def update_trust_product(conn: Connection, product_id: int, body: dict) -> dict:
    if "asset_pool_id" in body:
        raise HTTPException(status_code=400, detail="asset_pool_id cannot be updated")
    if "code" in body:
        raise HTTPException(status_code=400, detail="code cannot be updated")

    existing = conn.execute(
        text("SELECT id FROM trust_products WHERE id = :id"),
        {"id": product_id},
    ).fetchone()
    if existing is None:
        raise HTTPException(status_code=404, detail="Trust product not found")

    name = _require_str(body.get("name"), field="name", max_len=200)
    status = _parse_write_status(body.get("status"))
    trust_end_date = _parse_trust_end_date(body.get("trust_end_date"))

    _assert_name_unique(conn, name, exclude_id=product_id)

    row = conn.execute(
        text("""
            UPDATE trust_products
            SET name = :name,
                status = :status,
                trust_end_date = :trust_end_date
            WHERE id = :id
            RETURNING
                id, asset_pool_id, code, name, status, trust_end_date,
                created_at, updated_at
        """),
        {
            "id": product_id,
            "name": name,
            "status": status,
            "trust_end_date": trust_end_date,
        },
    ).fetchone()

    pool_row = conn.execute(
        text("SELECT name FROM asset_pools WHERE id = :id"),
        {"id": row.asset_pool_id},
    ).fetchone()
    pool_name = pool_row.name if pool_row else None
    return _row_to_dict(row, asset_pool_name=pool_name)
