"""手工结算：独立账本写入 + 读路径 overlay（不改还款/监控事实表）。"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from app import query_utils
from app.service.followup_upload import (
    ALLOWED_EXTENSIONS_ATTR,
    FILE_EXTENSIONS,
    IMAGE_EXTENSIONS,
    MAX_FILE_SIZE,
    MAX_FILES_PER_ENTRY,
    _ext_from_content_type,
    _resolve_original_name,
    attachment_content_disposition,
    upload_root,
)

_DISPLAY_TZ = ZoneInfo("Asia/Shanghai")
_ATTACHMENT_LIMIT_MSG = "附件最多 10 个，请先删除已有附件或减少本次上传数量。"

SOURCE_MANUAL_SETTLEMENT = "manual_settlement"

# 还款方下拉（可扩展）
REPAYER_OPTIONS: tuple[str, ...] = (
    "中国对外经济贸易信托有限公司",
)
DEFAULT_REPAYER = REPAYER_OPTIONS[0]


def settlement_dir(settlement_id: int) -> Path:
    dest = upload_root() / "manual_settlements" / str(settlement_id)
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _jsonable(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def _row_dict(row: Any) -> dict[str, Any]:
    return {k: _jsonable(v) for k, v in dict(row._mapping).items()}


def apply_amount_overlay(
    repaid: float | None,
    remaining: float | None,
    settlement_sum: float,
) -> tuple[float, float]:
    repaid_f = float(repaid or 0) + float(settlement_sum or 0)
    remaining_f = max(0.0, float(remaining or 0) - float(settlement_sum or 0))
    return repaid_f, remaining_f


def settlement_sums_by_asset_code(
    conn: Connection,
    product_ids: list[int] | None = None,
    asset_codes: list[str] | None = None,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[tuple[int, str], float]:
    """未作废结算按 (trust_product_id, asset_code) 汇总金额。

    可选 ``date_from`` / ``date_to`` 按 ``settlement_date`` 闭区间过滤；均省略则汇总全部历史。
    """
    params: dict[str, Any] = {}
    prod_sql = ""
    if product_ids:
        prod_sql, prod_params = query_utils.sql_in_int_column(
            "s.trust_product_id", product_ids, param_prefix="msp"
        )
        params.update(prod_params)
    code_sql = ""
    if asset_codes:
        codes = [c for c in (str(x).strip() for x in asset_codes) if c]
        if codes:
            code_sql, code_params = query_utils.sql_in_str_column(
                "s.asset_code", codes, param_prefix="msac"
            )
            params.update(code_params)
    date_sql = ""
    if date_from is not None:
        date_sql += " AND s.settlement_date >= :ms_date_from"
        params["ms_date_from"] = date_from
    if date_to is not None:
        date_sql += " AND s.settlement_date <= :ms_date_to"
        params["ms_date_to"] = date_to
    rows = conn.execute(
        text(
            f"""
            SELECT s.trust_product_id, s.asset_code, COALESCE(SUM(s.amount), 0) AS total
            FROM trust_asset_manual_settlements s
            WHERE s.voided_at IS NULL
              {prod_sql}
              {code_sql}
              {date_sql}
            GROUP BY s.trust_product_id, s.asset_code
            """
        ),
        params,
    ).fetchall()
    return {
        (int(r.trust_product_id), str(r.asset_code).strip()): float(r.total)
        for r in rows
        if r.trust_product_id is not None and r.asset_code
    }


def list_settlements_for_asset(
    conn: Connection,
    trust_product_id: int,
    asset_code: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            SELECT s.*
            FROM trust_asset_manual_settlements s
            WHERE s.trust_product_id = :tp
              AND s.asset_code = :ac
              AND s.voided_at IS NULL
            ORDER BY s.settlement_date DESC, s.id DESC
            """
        ),
        {"tp": trust_product_id, "ac": asset_code},
    ).fetchall()
    out = [_row_dict(r) for r in rows]
    if not out:
        return out
    ids = [int(r["id"]) for r in out]
    att_rows = conn.execute(
        text(
            """
            SELECT *
            FROM trust_asset_manual_settlement_attachments
            WHERE settlement_id = ANY(CAST(:ids AS bigint[]))
            ORDER BY id
            """
        ),
        {"ids": "{" + ",".join(str(i) for i in ids) + "}"},
    ).fetchall()
    by_sid: dict[int, list[dict]] = {i: [] for i in ids}
    for a in att_rows:
        d = _row_dict(a)
        by_sid.setdefault(int(d["settlement_id"]), []).append(d)
    for r in out:
        r["attachments"] = by_sid.get(int(r["id"]), [])
    return out


def virtual_repayment_rows_from_settlements(
    settlements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """映射为还款情况 / 披露还款可用的虚拟行。"""
    rows: list[dict[str, Any]] = []
    for s in settlements:
        if s.get("voided_at"):
            continue
        amount = float(s.get("amount") or 0)
        if amount <= 0:
            continue
        rows.append(
            {
                "id": None,
                "trust_product_id": s.get("trust_product_id"),
                "trust_asset_id": None,
                "asset_code": s.get("asset_code"),
                "custody_asset_code": s.get("custody_asset_code") or s.get("asset_code"),
                "source_asset_code": None,
                "data_date": s.get("settlement_date"),
                "repayment_date": s.get("settlement_date"),
                "period_no": None,
                "actual_repayment_amount": amount,
                # 披露/还款情况：当前还款方 = 手工结算.还款方(repayer)
                "current_payer": (str(s.get("repayer") or "").strip() or None),
                # 当期计划还款金额 = 当期实际还款金额
                "planned_repayment_amount": amount,
                "initial_renovation_amount": None,
                "cumulative_repaid_amount": None,
                "remaining_balance": None,
                "synced_at": s.get("created_at"),
                "source": SOURCE_MANUAL_SETTLEMENT,
                "manual_settlement_id": s.get("id"),
                "description": s.get("description"),
            }
        )
    return rows


def merge_repayment_items_with_settlements(
    fact_items: list[dict[str, Any]],
    settlements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    virtual = virtual_repayment_rows_from_settlements(settlements)
    merged = list(fact_items) + virtual

    def _sort_key(item: dict) -> tuple:
        rd = item.get("repayment_date") or ""
        return (str(rd), int(item.get("id") or 0))

    merged.sort(key=_sort_key, reverse=True)
    return merged


def overlay_monitor_amounts(
    row: dict[str, Any],
    settlement_sum: float,
) -> dict[str, Any]:
    out = dict(row)
    repaid, remaining = apply_amount_overlay(
        out.get("repaid_amount"), out.get("remaining_amount"), settlement_sum
    )
    out["repaid_amount"] = repaid
    out["remaining_amount"] = remaining
    return out


def overlay_repayment_detail_amounts(
    row: dict[str, Any],
    settlement_sum: float,
) -> dict[str, Any]:
    """还款明细：累计已还 / 剩余应还叠加手工结算。"""
    out = dict(row)
    repaid, remaining = apply_amount_overlay(
        out.get("cumulative_repaid_amount"),
        out.get("remaining_balance"),
        settlement_sum,
    )
    out["cumulative_repaid_amount"] = repaid
    out["remaining_balance"] = remaining
    return out


def overlay_portfolio_items(
    items: list[dict[str, Any]],
    sums: dict[tuple[int, str], float],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        pid = item.get("trust_product_id")
        ac = str(item.get("asset_code") or "").strip()
        if pid is None or not ac:
            out.append(item)
            continue
        total = float(sums.get((int(pid), ac), 0) or 0)
        if total == 0:
            out.append(item)
            continue
        patched = overlay_monitor_amounts(item, total)
        # ES / bucket 可能随 remaining 变化：留给调用方按需重算；此处只改金额
        out.append(patched)
    return out


def resolve_custody_asset_code(
    conn: Connection,
    trust_product_id: int,
    asset_code: str,
) -> Optional[str]:
    row = conn.execute(
        text(
            """
            SELECT COALESCE(
                (
                    SELECT m.custody_asset_code
                    FROM trust_asset_monitor_records m
                    WHERE m.trust_product_id = :tp
                      AND m.asset_code = :ac
                      AND m.custody_asset_code IS NOT NULL
                    ORDER BY m.data_date DESC NULLS LAST, m.id DESC
                    LIMIT 1
                ),
                (
                    SELECT ta.custody_asset_code
                    FROM trust_assets ta
                    WHERE ta.trust_product_id = :tp
                      AND ta.asset_code = :ac
                    LIMIT 1
                ),
                :ac
            ) AS custody_asset_code
            """
        ),
        {"tp": trust_product_id, "ac": asset_code},
    ).fetchone()
    if not row or not row.custody_asset_code:
        return asset_code
    return str(row.custody_asset_code)


async def save_settlement_files(
    settlement_id: int,
    files: list[UploadFile],
    *,
    existing_attachment_count: int = 0,
) -> list[dict]:
    pending = [f for f in files if f is not None]
    if not pending:
        return []
    remaining_slots = max(0, MAX_FILES_PER_ENTRY - int(existing_attachment_count or 0))
    if len(pending) > remaining_slots:
        raise HTTPException(status_code=400, detail=_ATTACHMENT_LIMIT_MSG)

    saved: list[dict] = []
    dest = settlement_dir(settlement_id)
    for uf in pending:
        original_name = _resolve_original_name(uf)
        ext = Path(original_name).suffix.lower()
        if not ext:
            ext = _ext_from_content_type(uf.content_type)
            if ext:
                original_name = f"{Path(original_name).stem}{ext}"
        if ext not in FILE_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持该文件类型: {original_name}",
            )
        content = await uf.read()
        if not content:
            continue
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"单文件不能超过 10MB: {original_name}",
            )
        stored_name = f"{uuid.uuid4().hex}{ext}"
        path = dest / stored_name
        path.write_bytes(content)
        rel_path = str(path.relative_to(upload_root()))
        attachment_type = "image" if ext in IMAGE_EXTENSIONS else "file"
        saved.append(
            {
                "file_name": original_name,
                "stored_path": rel_path,
                "content_type": uf.content_type,
                "file_size": len(content),
                "attachment_type": attachment_type,
            }
        )
    if int(existing_attachment_count or 0) + len(saved) > MAX_FILES_PER_ENTRY:
        raise HTTPException(status_code=400, detail=_ATTACHMENT_LIMIT_MSG)
    return saved


def create_settlement(
    conn: Connection,
    *,
    trust_product_id: int,
    asset_code: str,
    settlement_date: date,
    settled_by: str,
    payer: str,
    amount: float,
    description: Optional[str],
    created_by: Optional[str],
    custody_asset_code: Optional[str] = None,
    repayer: Optional[str] = None,
) -> dict[str, Any]:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="结算金额必须大于 0")
    ac = (asset_code or "").strip()
    if not ac:
        raise HTTPException(status_code=400, detail="资产主编号不能为空")
    settled_by_s = (settled_by or "").strip()
    payer_s = (payer or "").strip()
    repayer_s = (repayer or "").strip() or DEFAULT_REPAYER
    if not settled_by_s:
        raise HTTPException(status_code=400, detail="请填写结算人")
    if not payer_s:
        raise HTTPException(status_code=400, detail="请填写结算主体")
    if repayer_s not in REPAYER_OPTIONS:
        raise HTTPException(status_code=400, detail="请选择有效的还款方")
    custody = (custody_asset_code or "").strip() or resolve_custody_asset_code(
        conn, trust_product_id, ac
    )
    row = conn.execute(
        text(
            """
            INSERT INTO trust_asset_manual_settlements (
                trust_product_id, asset_code, custody_asset_code,
                settlement_date, settled_by, payer, repayer, amount, description, created_by
            ) VALUES (
                :tp, :ac, :cac, :sd, :by, :payer, :repayer, :amt, :desc, :cb
            )
            RETURNING *
            """
        ),
        {
            "tp": trust_product_id,
            "ac": ac,
            "cac": custody,
            "sd": settlement_date,
            "by": settled_by_s,
            "payer": payer_s,
            "repayer": repayer_s,
            "amt": amount,
            "desc": (description or "").strip() or None,
            "cb": created_by,
        },
    ).fetchone()
    return _row_dict(row)


def get_settlement(
    conn: Connection, settlement_id: int
) -> Optional[dict[str, Any]]:
    row = conn.execute(
        text(
            """
            SELECT * FROM trust_asset_manual_settlements
            WHERE id = :id
            """
        ),
        {"id": settlement_id},
    ).fetchone()
    if not row:
        return None
    out = _row_dict(row)
    att_rows = conn.execute(
        text(
            """
            SELECT * FROM trust_asset_manual_settlement_attachments
            WHERE settlement_id = :sid
            ORDER BY id
            """
        ),
        {"sid": settlement_id},
    ).fetchall()
    out["attachments"] = [_row_dict(a) for a in att_rows]
    return out


def update_settlement(
    conn: Connection,
    settlement_id: int,
    *,
    trust_product_id: int,
    asset_code: str,
    settlement_date: date,
    settled_by: str,
    payer: str,
    amount: float,
    description: Optional[str],
    repayer: Optional[str] = None,
) -> dict[str, Any]:
    if amount <= 0:
        raise HTTPException(status_code=400, detail="结算金额必须大于 0")
    ac = (asset_code or "").strip()
    if not ac:
        raise HTTPException(status_code=400, detail="资产主编号不能为空")
    settled_by_s = (settled_by or "").strip()
    payer_s = (payer or "").strip()
    repayer_s = (repayer or "").strip() or DEFAULT_REPAYER
    if not settled_by_s:
        raise HTTPException(status_code=400, detail="请填写结算人")
    if not payer_s:
        raise HTTPException(status_code=400, detail="请填写结算主体")
    if repayer_s not in REPAYER_OPTIONS:
        raise HTTPException(status_code=400, detail="请选择有效的还款方")
    row = conn.execute(
        text(
            """
            UPDATE trust_asset_manual_settlements
            SET settlement_date = :sd,
                settled_by = :by,
                payer = :payer,
                repayer = :repayer,
                amount = :amt,
                description = :desc,
                updated_at = NOW()
            WHERE id = :id
              AND trust_product_id = :tp
              AND asset_code = :ac
              AND voided_at IS NULL
            RETURNING *
            """
        ),
        {
            "id": settlement_id,
            "tp": trust_product_id,
            "ac": ac,
            "sd": settlement_date,
            "by": settled_by_s,
            "payer": payer_s,
            "repayer": repayer_s,
            "amt": amount,
            "desc": (description or "").strip() or None,
        },
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="结算记录不存在或已作废")
    return _row_dict(row)


def void_settlement(
    conn: Connection,
    settlement_id: int,
    *,
    trust_product_id: int,
    asset_code: str,
    voided_by: Optional[str],
) -> dict[str, Any]:
    ac = (asset_code or "").strip()
    row = conn.execute(
        text(
            """
            UPDATE trust_asset_manual_settlements
            SET voided_at = NOW(),
                voided_by = :vb,
                updated_at = NOW()
            WHERE id = :id
              AND trust_product_id = :tp
              AND asset_code = :ac
              AND voided_at IS NULL
            RETURNING *
            """
        ),
        {
            "id": settlement_id,
            "tp": trust_product_id,
            "ac": ac,
            "vb": voided_by,
        },
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="结算记录不存在或已作废")
    return _row_dict(row)


def count_attachments(conn: Connection, settlement_id: int) -> int:
    row = conn.execute(
        text(
            """
            SELECT COUNT(*) AS n
            FROM trust_asset_manual_settlement_attachments
            WHERE settlement_id = :sid
            """
        ),
        {"sid": settlement_id},
    ).fetchone()
    return int(row.n) if row else 0


def delete_attachments(
    conn: Connection,
    *,
    settlement_id: int,
    attachment_ids: list[int],
) -> None:
    ids = [int(x) for x in attachment_ids if x is not None]
    if not ids:
        return
    rows = conn.execute(
        text(
            """
            SELECT id, stored_path
            FROM trust_asset_manual_settlement_attachments
            WHERE settlement_id = :sid
              AND id = ANY(CAST(:ids AS bigint[]))
            """
        ),
        {
            "sid": settlement_id,
            "ids": "{" + ",".join(str(i) for i in ids) + "}",
        },
    ).fetchall()
    for r in rows:
        rel = r.stored_path
        if rel:
            path = upload_root() / str(rel)
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass
    conn.execute(
        text(
            """
            DELETE FROM trust_asset_manual_settlement_attachments
            WHERE settlement_id = :sid
              AND id = ANY(CAST(:ids AS bigint[]))
            """
        ),
        {
            "sid": settlement_id,
            "ids": "{" + ",".join(str(i) for i in ids) + "}",
        },
    )


def insert_attachments(
    conn: Connection, settlement_id: int, files_meta: list[dict]
) -> None:
    for meta in files_meta:
        conn.execute(
            text(
                """
                INSERT INTO trust_asset_manual_settlement_attachments (
                    settlement_id, file_name, stored_path, content_type,
                    file_size, attachment_type
                ) VALUES (
                    :sid, :fn, :sp, :ct, :fs, :at
                )
                """
            ),
            {
                "sid": settlement_id,
                "fn": meta["file_name"],
                "sp": meta["stored_path"],
                "ct": meta.get("content_type"),
                "fs": meta.get("file_size"),
                "at": meta.get("attachment_type") or "file",
            },
        )


def get_attachment(conn: Connection, attachment_id: int) -> Optional[dict[str, Any]]:
    row = conn.execute(
        text(
            """
            SELECT * FROM trust_asset_manual_settlement_attachments
            WHERE id = :id
            """
        ),
        {"id": attachment_id},
    ).fetchone()
    return _row_dict(row) if row else None


def fetch_settlements_for_disclosure(
    conn: Connection,
    product_ids: list[int],
    *,
    as_of: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    """披露用：按结算日过滤。

    - ``date_from`` / ``date_to``：闭区间（还款披露日期范围）
    - 仅 ``as_of``：``settlement_date = as_of``（兼容旧调用）
    - 均省略：返回全部未作废结算
    """
    if not product_ids:
        return []
    prod_sql, prod_params = query_utils.sql_in_int_column(
        "s.trust_product_id", product_ids, param_prefix="dsp"
    )
    params: dict[str, Any] = {**prod_params}
    date_sql = ""
    if date_from is not None or date_to is not None:
        if date_from is not None:
            date_sql += " AND s.settlement_date >= :date_from"
            params["date_from"] = date_from
        if date_to is not None:
            date_sql += " AND s.settlement_date <= :date_to"
            params["date_to"] = date_to
    elif as_of is not None:
        date_sql = " AND s.settlement_date = :as_of"
        params["as_of"] = as_of
    rows = conn.execute(
        text(
            f"""
            SELECT s.*, tp.name AS trust_product_name
            FROM trust_asset_manual_settlements s
            JOIN trust_products tp ON tp.id = s.trust_product_id
            WHERE s.voided_at IS NULL
              {prod_sql}
              {date_sql}
            ORDER BY s.trust_product_id, s.settlement_date, s.id
            """
        ),
        params,
    ).fetchall()
    return [_row_dict(r) for r in rows]


__all__ = [
    "ALLOWED_EXTENSIONS_ATTR",
    "DEFAULT_REPAYER",
    "REPAYER_OPTIONS",
    "SOURCE_MANUAL_SETTLEMENT",
    "apply_amount_overlay",
    "attachment_content_disposition",
    "count_attachments",
    "create_settlement",
    "delete_attachments",
    "fetch_settlements_for_disclosure",
    "get_attachment",
    "get_settlement",
    "insert_attachments",
    "list_settlements_for_asset",
    "merge_repayment_items_with_settlements",
    "overlay_monitor_amounts",
    "overlay_portfolio_items",
    "overlay_repayment_detail_amounts",
    "resolve_custody_asset_code",
    "save_settlement_files",
    "settlement_sums_by_asset_code",
    "update_settlement",
    "upload_root",
    "virtual_repayment_rows_from_settlements",
    "void_settlement",
]
