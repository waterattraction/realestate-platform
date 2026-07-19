"""数据披露：活数据预览、多快照冻结、模版导出。"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import assetinfo_templates as templates
from app import assetinfo_upload
from app import query_utils

EXPORT_MAX = assetinfo_upload.MONITOR_EXPORT_MAX
PREVIEW_DEFAULT_LIMIT = 200

DETAIL_COLS = templates.template_field_keys(templates.REPAYMENT_DETAIL_TEMPLATE_COLUMNS)
PLAN_COLS = templates.template_field_keys(templates.REPAYMENT_PLAN_TEMPLATE_COLUMNS)
MONITOR_COLS = templates.template_field_keys(templates.MONITOR_TEMPLATE_COLUMNS)


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


def parse_as_of_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = query_utils.parse_optional_date(value)
    if not parsed:
        raise HTTPException(status_code=400, detail="请提供有效日期")
    try:
        return date.fromisoformat(parsed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="日期格式无效，请用 YYYY-MM-DD") from exc


def _pg_bigint_array_literal(ids: list[int]) -> str:
    return "{" + ",".join(str(int(i)) for i in ids) + "}"


def _product_names_label(conn: Connection, product_ids: list[int]) -> str:
    rows = conn.execute(
        text("SELECT id, name FROM trust_products WHERE id = ANY(CAST(:pids AS bigint[]))"),
        {"pids": _pg_bigint_array_literal(product_ids)},
    ).fetchall()
    name_by_id = {int(r.id): str(r.name) for r in rows}
    return "、".join(name_by_id.get(i, str(i)) for i in product_ids)


def _require_products(product_ids: list[int] | None) -> list[int]:
    if not product_ids:
        raise HTTPException(status_code=400, detail="请至少选择一个信托产品")
    return product_ids


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    out = dict(item)
    for k, v in list(out.items()):
        out[k] = _jsonable(v)
    if not out.get("source_asset_code") and out.get("asset_code"):
        out["source_asset_code"] = out.get("asset_code")
    return out


# ── live queries ──────────────────────────────────────────────


def fetch_repayment_live(
    conn: Connection,
    product_ids: list[int],
    as_of: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """明细：repayment_date ≤ as_of；计划：每产品 data_date≤as_of 最新一批；逾期：监控 ≤as_of 最新。"""
    prod_sql, prod_params = query_utils.sql_in_int_column(
        "r.trust_product_id", product_ids, param_prefix="tp"
    )
    params = {**prod_params, "as_of": as_of}
    detail_rows = conn.execute(
        text(
            f"""
            SELECT r.*, tp.name AS trust_product_name,
                   COALESCE(mon.overdue_days, 0) AS overdue_days
            FROM trust_repayment_detail_records r
            JOIN trust_products tp ON tp.id = r.trust_product_id
            LEFT JOIN LATERAL (
                SELECT m.overdue_days
                FROM trust_asset_monitor_records m
                WHERE m.trust_product_id = r.trust_product_id
                  AND m.data_date <= :as_of
                  AND (
                      m.custody_asset_code = r.custody_asset_code
                      OR (
                          r.custody_asset_code IS NULL
                          AND m.asset_code = r.asset_code
                      )
                  )
                ORDER BY m.data_date DESC NULLS LAST, m.id DESC
                LIMIT 1
            ) mon ON TRUE
            WHERE r.repayment_date IS NOT NULL
              AND r.repayment_date <= :as_of
              {prod_sql}
            ORDER BY r.trust_product_id, r.repayment_date, r.id
            """
        ),
        params,
    ).fetchall()
    details = [_normalize_item(_row_dict(r)) for r in detail_rows]

    plan_prod_sql, plan_prod_params = query_utils.sql_in_int_column(
        "p.trust_product_id", product_ids, param_prefix="ptp"
    )
    latest_prod_sql, latest_prod_params = query_utils.sql_in_int_column(
        "trust_product_id", product_ids, param_prefix="ltp"
    )
    plan_params = {**plan_prod_params, **latest_prod_params, "as_of": as_of}
    plan_rows = conn.execute(
        text(
            f"""
            WITH latest AS (
                SELECT trust_product_id, MAX(data_date) AS data_date
                FROM trust_repayment_plan_records
                WHERE data_date <= :as_of
                  {latest_prod_sql}
                GROUP BY trust_product_id
            )
            SELECT p.*, tp.name AS trust_product_name
            FROM trust_repayment_plan_records p
            JOIN trust_products tp ON tp.id = p.trust_product_id
            INNER JOIN latest l
              ON l.trust_product_id = p.trust_product_id
             AND l.data_date = p.data_date
            WHERE 1=1
              {plan_prod_sql}
            ORDER BY p.trust_product_id, p.id
            """
        ),
        plan_params,
    ).fetchall()
    plans = [_normalize_item(_row_dict(r)) for r in plan_rows]
    return details, plans


def fetch_monitor_live(
    conn: Connection,
    product_ids: list[int],
    as_of: date,
) -> list[dict[str, Any]]:
    prod_sql, prod_params = query_utils.sql_in_int_column(
        "r.trust_product_id", product_ids, param_prefix="tp"
    )
    params = {**prod_params, "as_of": as_of}
    rows = conn.execute(
        text(
            f"""
            SELECT r.*, tp.name AS trust_product_name
            FROM trust_asset_monitor_records r
            JOIN trust_products tp ON tp.id = r.trust_product_id
            WHERE r.data_date = :as_of
              {prod_sql}
            ORDER BY r.trust_product_id, r.id
            """
        ),
        params,
    ).fetchall()
    return [_normalize_item(_row_dict(r)) for r in rows]


# ── freeze ────────────────────────────────────────────────────


def _insert_snapshot_header(
    conn: Connection,
    *,
    snapshot_type: str,
    as_of: date,
    product_ids: list[int],
    product_names: str,
    note: Optional[str],
    created_by: Optional[str],
    detail_row_count: int = 0,
    plan_row_count: int = 0,
    monitor_row_count: int = 0,
) -> dict[str, Any]:
    row = conn.execute(
        text(
            """
            INSERT INTO disclosure_snapshots (
                snapshot_type, as_of_date, product_ids, product_names, note, created_by,
                detail_row_count, plan_row_count, monitor_row_count
            ) VALUES (
                :stype, :as_of, CAST(:pids AS bigint[]), :pnames, :note, :created_by,
                :dcount, :pcount, :mcount
            )
            RETURNING id, frozen_at, as_of_date, snapshot_type
            """
        ),
        {
            "stype": snapshot_type,
            "as_of": as_of,
            "pids": _pg_bigint_array_literal(product_ids),
            "pnames": product_names,
            "note": (note or "").strip() or None,
            "created_by": created_by,
            "dcount": detail_row_count,
            "pcount": plan_row_count,
            "mcount": monitor_row_count,
        },
    ).fetchone()
    return _row_dict(row)


def freeze_repayment(
    conn: Connection,
    product_ids: list[int],
    as_of: date,
    *,
    note: Optional[str] = None,
    created_by: Optional[str] = None,
) -> dict[str, Any]:
    product_ids = _require_products(product_ids)
    details, plans = fetch_repayment_live(conn, product_ids, as_of)
    if len(details) + len(plans) > EXPORT_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"结果超过 {EXPORT_MAX} 条，请缩小产品或截止日范围后再冻结",
        )
    names = _product_names_label(conn, product_ids)
    snap = _insert_snapshot_header(
        conn,
        snapshot_type="repayment",
        as_of=as_of,
        product_ids=product_ids,
        product_names=names,
        note=note,
        created_by=created_by,
        detail_row_count=len(details),
        plan_row_count=len(plans),
    )
    sid = int(snap["id"])
    for d in details:
        conn.execute(
            text(
                """
                INSERT INTO disclosure_repayment_rows (
                    snapshot_id, trust_product_id, trust_product_name,
                    asset_pool_code, current_payer, custody_asset_code,
                    planned_repayment_amount, initial_renovation_amount,
                    cumulative_repaid_amount, remaining_balance,
                    actual_repayment_amount, overdue_days, source_record_id
                ) VALUES (
                    :sid, :tp, :tpn, :apc, :payer, :cac,
                    :pra, :ira, :cra, :rb, :ara, :od, :src
                )
                """
            ),
            {
                "sid": sid,
                "tp": d.get("trust_product_id"),
                "tpn": d.get("trust_product_name"),
                "apc": d.get("asset_pool_code"),
                "payer": d.get("current_payer"),
                "cac": d.get("custody_asset_code"),
                "pra": d.get("planned_repayment_amount"),
                "ira": d.get("initial_renovation_amount"),
                "cra": d.get("cumulative_repaid_amount"),
                "rb": d.get("remaining_balance"),
                "ara": d.get("actual_repayment_amount"),
                "od": d.get("overdue_days") if d.get("overdue_days") is not None else 0,
                "src": d.get("id"),
            },
        )
    for p in plans:
        conn.execute(
            text(
                """
                INSERT INTO disclosure_repayment_plan_rows (
                    snapshot_id, trust_product_id, trust_product_name,
                    asset_pool_code, source_asset_code, renovation_vendor, data_date,
                    initial_transfer_amount, repaid_amount, remaining_amount,
                    community_name, city, current_bill_date, repayment_amount_detail,
                    planned_monthly_repayment_amount, final_planned_repayment_amount,
                    source_record_id
                ) VALUES (
                    :sid, :tp, :tpn, :apc, :sac, :rv, :dd,
                    :ita, :ra, :rema, :cn, :city, :cbd, :rad,
                    :pmra, :fpra, :src
                )
                """
            ),
            {
                "sid": sid,
                "tp": p.get("trust_product_id"),
                "tpn": p.get("trust_product_name"),
                "apc": p.get("asset_pool_code"),
                "sac": p.get("source_asset_code") or p.get("asset_code"),
                "rv": p.get("renovation_vendor"),
                "dd": p.get("data_date"),
                "ita": p.get("initial_transfer_amount"),
                "ra": p.get("repaid_amount"),
                "rema": p.get("remaining_amount"),
                "cn": p.get("community_name"),
                "city": p.get("city"),
                "cbd": p.get("current_bill_date"),
                "rad": p.get("repayment_amount_detail"),
                "pmra": p.get("planned_monthly_repayment_amount"),
                "fpra": p.get("final_planned_repayment_amount"),
                "src": p.get("id"),
            },
        )
    return {
        "snapshot_id": sid,
        "frozen_at": snap.get("frozen_at"),
        "as_of_date": snap.get("as_of_date"),
        "detail_row_count": len(details),
        "plan_row_count": len(plans),
        "product_names": names,
    }


def freeze_monitor(
    conn: Connection,
    product_ids: list[int],
    as_of: date,
    *,
    note: Optional[str] = None,
    created_by: Optional[str] = None,
) -> dict[str, Any]:
    product_ids = _require_products(product_ids)
    rows = fetch_monitor_live(conn, product_ids, as_of)
    if len(rows) > EXPORT_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"结果超过 {EXPORT_MAX} 条，请缩小产品范围后再冻结",
        )
    names = _product_names_label(conn, product_ids)
    snap = _insert_snapshot_header(
        conn,
        snapshot_type="monitor",
        as_of=as_of,
        product_ids=product_ids,
        product_names=names,
        note=note,
        created_by=created_by,
        monitor_row_count=len(rows),
    )
    sid = int(snap["id"])
    for r in rows:
        conn.execute(
            text(
                """
                INSERT INTO disclosure_monitor_rows (
                    snapshot_id, trust_product_id, trust_product_name,
                    asset_pool_code, source_asset_code, renovation_vendor, data_date,
                    initial_transfer_amount, repaid_amount, remaining_amount,
                    asset_status, last_renovation_payment_date, community_name, city,
                    collection_contract_code, custody_agreement_sign_date,
                    collection_contract_years, owner_code, withholding_ratio,
                    actual_monthly_rent, source_record_id
                ) VALUES (
                    :sid, :tp, :tpn, :apc, :sac, :rv, :dd,
                    :ita, :ra, :rema, :st, :lrpd, :cn, :city,
                    :ccc, :casd, :ccy, :oc, :wr, :amr, :src
                )
                """
            ),
            {
                "sid": sid,
                "tp": r.get("trust_product_id"),
                "tpn": r.get("trust_product_name"),
                "apc": r.get("asset_pool_code"),
                "sac": r.get("source_asset_code") or r.get("asset_code"),
                "rv": r.get("renovation_vendor"),
                "dd": r.get("data_date"),
                "ita": r.get("initial_transfer_amount"),
                "ra": r.get("repaid_amount"),
                "rema": r.get("remaining_amount"),
                "st": r.get("asset_status"),
                "lrpd": r.get("last_renovation_payment_date"),
                "cn": r.get("community_name"),
                "city": r.get("city"),
                "ccc": r.get("collection_contract_code"),
                "casd": r.get("custody_agreement_sign_date"),
                "ccy": r.get("collection_contract_years"),
                "oc": r.get("owner_code"),
                "wr": r.get("withholding_ratio"),
                "amr": r.get("actual_monthly_rent"),
                "src": r.get("id"),
            },
        )
    return {
        "snapshot_id": sid,
        "frozen_at": snap.get("frozen_at"),
        "as_of_date": snap.get("as_of_date"),
        "monitor_row_count": len(rows),
        "product_names": names,
    }


# ── snapshot CRUD ─────────────────────────────────────────────


def list_snapshots(conn: Connection, snapshot_type: str, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        text(
            """
            SELECT id, snapshot_type, as_of_date, frozen_at, product_ids, product_names,
                   note, detail_row_count, plan_row_count, monitor_row_count, created_by
            FROM disclosure_snapshots
            WHERE snapshot_type = :stype
            ORDER BY frozen_at DESC, id DESC
            LIMIT :lim
            """
        ),
        {"stype": snapshot_type, "lim": limit},
    ).fetchall()
    out = []
    for r in rows:
        d = _row_dict(r)
        pids = d.get("product_ids") or []
        if isinstance(pids, str):
            pids = [int(x) for x in pids.strip("{}").split(",") if x]
        d["product_ids"] = list(pids)
        out.append(d)
    return out


def get_snapshot(conn: Connection, snapshot_id: int) -> Optional[dict]:
    row = conn.execute(
        text("SELECT * FROM disclosure_snapshots WHERE id = :id"),
        {"id": snapshot_id},
    ).fetchone()
    if not row:
        return None
    d = _row_dict(row)
    pids = d.get("product_ids") or []
    if isinstance(pids, str):
        pids = [int(x) for x in pids.strip("{}").split(",") if x]
    d["product_ids"] = list(pids)
    return d


def load_snapshot_repayment(
    conn: Connection, snapshot_id: int
) -> tuple[list[dict], list[dict]]:
    details = [
        _row_dict(r)
        for r in conn.execute(
            text(
                """
                SELECT * FROM disclosure_repayment_rows
                WHERE snapshot_id = :sid ORDER BY id
                """
            ),
            {"sid": snapshot_id},
        ).fetchall()
    ]
    plans = [
        _row_dict(r)
        for r in conn.execute(
            text(
                """
                SELECT * FROM disclosure_repayment_plan_rows
                WHERE snapshot_id = :sid ORDER BY id
                """
            ),
            {"sid": snapshot_id},
        ).fetchall()
    ]
    return details, plans


def load_snapshot_monitor(conn: Connection, snapshot_id: int) -> list[dict]:
    return [
        _row_dict(r)
        for r in conn.execute(
            text(
                """
                SELECT * FROM disclosure_monitor_rows
                WHERE snapshot_id = :sid ORDER BY id
                """
            ),
            {"sid": snapshot_id},
        ).fetchall()
    ]


def delete_snapshot(conn: Connection, snapshot_id: int) -> dict:
    snap = get_snapshot(conn, snapshot_id)
    if not snap:
        raise HTTPException(status_code=404, detail="快照不存在")
    frozen_at = snap.get("frozen_at")
    if isinstance(frozen_at, str):
        frozen_at = datetime.fromisoformat(frozen_at.replace("Z", "+00:00"))
    if frozen_at is not None:
        if frozen_at.tzinfo is None:
            frozen_at = frozen_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - frozen_at >= timedelta(days=30):
            raise HTTPException(status_code=400, detail="冻结时间已满 1 个月，不可删除")
    conn.execute(
        text("DELETE FROM disclosure_snapshots WHERE id = :id"), {"id": snapshot_id}
    )
    return {"deleted": True, "snapshot_id": snapshot_id}


# ── preview / export helpers ──────────────────────────────────


def preview_repayment_live(
    conn: Connection,
    product_ids: list[int],
    as_of: date,
    *,
    limit: int = PREVIEW_DEFAULT_LIMIT,
) -> dict:
    product_ids = _require_products(product_ids)
    details, plans = fetch_repayment_live(conn, product_ids, as_of)
    return {
        "mode": "live",
        "as_of_date": as_of.isoformat(),
        "product_ids": product_ids,
        "detail_total": len(details),
        "plan_total": len(plans),
        "detail_headers": templates.template_headers(templates.REPAYMENT_DETAIL_TEMPLATE_COLUMNS),
        "plan_headers": templates.template_headers(templates.REPAYMENT_PLAN_TEMPLATE_COLUMNS),
        "detail_keys": DETAIL_COLS,
        "plan_keys": PLAN_COLS,
        "details": details[:limit],
        "plans": plans[:limit],
    }


def preview_monitor_live(
    conn: Connection,
    product_ids: list[int],
    as_of: date,
    *,
    limit: int = PREVIEW_DEFAULT_LIMIT,
) -> dict:
    product_ids = _require_products(product_ids)
    rows = fetch_monitor_live(conn, product_ids, as_of)
    return {
        "mode": "live",
        "as_of_date": as_of.isoformat(),
        "product_ids": product_ids,
        "monitor_total": len(rows),
        "headers": templates.template_headers(templates.MONITOR_TEMPLATE_COLUMNS),
        "keys": MONITOR_COLS,
        "rows": rows[:limit],
    }


def preview_repayment_snapshot(
    conn: Connection, snapshot_id: int, *, limit: int = PREVIEW_DEFAULT_LIMIT
) -> dict:
    snap = get_snapshot(conn, snapshot_id)
    if not snap or snap.get("snapshot_type") != "repayment":
        raise HTTPException(status_code=404, detail="还款披露快照不存在")
    details, plans = load_snapshot_repayment(conn, snapshot_id)
    return {
        "mode": "snapshot",
        "snapshot": snap,
        "detail_total": len(details),
        "plan_total": len(plans),
        "detail_headers": templates.template_headers(templates.REPAYMENT_DETAIL_TEMPLATE_COLUMNS),
        "plan_headers": templates.template_headers(templates.REPAYMENT_PLAN_TEMPLATE_COLUMNS),
        "detail_keys": DETAIL_COLS,
        "plan_keys": PLAN_COLS,
        "details": details[:limit],
        "plans": plans[:limit],
    }


def preview_monitor_snapshot(
    conn: Connection, snapshot_id: int, *, limit: int = PREVIEW_DEFAULT_LIMIT
) -> dict:
    snap = get_snapshot(conn, snapshot_id)
    if not snap or snap.get("snapshot_type") != "monitor":
        raise HTTPException(status_code=404, detail="监控披露快照不存在")
    rows = load_snapshot_monitor(conn, snapshot_id)
    return {
        "mode": "snapshot",
        "snapshot": snap,
        "monitor_total": len(rows),
        "headers": templates.template_headers(templates.MONITOR_TEMPLATE_COLUMNS),
        "keys": MONITOR_COLS,
        "rows": rows[:limit],
    }


def export_repayment_xlsx(
    conn: Connection,
    *,
    product_ids: list[int] | None = None,
    as_of: date | None = None,
    snapshot_id: int | None = None,
) -> bytes:
    if snapshot_id is not None:
        snap = get_snapshot(conn, snapshot_id)
        if not snap or snap.get("snapshot_type") != "repayment":
            raise HTTPException(status_code=404, detail="还款披露快照不存在")
        details, plans = load_snapshot_repayment(conn, snapshot_id)
    else:
        product_ids = _require_products(product_ids)
        if as_of is None:
            raise HTTPException(status_code=400, detail="请提供披露截止日")
        details, plans = fetch_repayment_live(conn, product_ids, as_of)
        if len(details) > EXPORT_MAX:
            raise HTTPException(
                status_code=400,
                detail=f"结果超过 {EXPORT_MAX} 条，请缩小范围",
            )
    return assetinfo_upload.build_repayment_disclosure_export_xlsx(details, plans)


def export_monitor_xlsx(
    conn: Connection,
    *,
    product_ids: list[int] | None = None,
    as_of: date | None = None,
    snapshot_id: int | None = None,
) -> bytes:
    if snapshot_id is not None:
        snap = get_snapshot(conn, snapshot_id)
        if not snap or snap.get("snapshot_type") != "monitor":
            raise HTTPException(status_code=404, detail="监控披露快照不存在")
        rows = load_snapshot_monitor(conn, snapshot_id)
    else:
        product_ids = _require_products(product_ids)
        if as_of is None:
            raise HTTPException(status_code=400, detail="请提供统计日期")
        rows = fetch_monitor_live(conn, product_ids, as_of)
        if len(rows) > EXPORT_MAX:
            raise HTTPException(
                status_code=400,
                detail=f"结果超过 {EXPORT_MAX} 条，请缩小范围",
            )
    return assetinfo_upload.build_monitor_export_xlsx(rows)
