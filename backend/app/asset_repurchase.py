"""资产回购 — 单位主数据 + 预览 + 新表落库执行（不改监控/发行/还款事实表）。

全程以资产主编号（asset_code）贯穿：选择、预览、落库、查重。
资产明细与冻结监控快照合并为 asset_repurchase_assets 单表，
历史房源号 = 该资产涉及的全部 distinct custody/source 编号（逗号分隔）。
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import assetinfo_upload as au
from app.overdue.buckets import (
    DELINQUENCY_BUCKET_LABELS,
    RECONCILIATION_TOLERANCE_DEFAULT,
    calc_delinquency_bucket,
)

MAX_REPURCHASE_ASSETS = 100
TOLERANCE = RECONCILIATION_TOLERANCE_DEFAULT

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# 与资产监控页的标准列顺序一致。回购预览逐分笔返回这些列，不以主编号
# 聚合覆盖文本、日期、来源和风险等字段。
MONITOR_PREVIEW_COLUMNS: tuple[tuple[str, str], ...] = (
    ("trust_product_name", "信托产品"),
    ("asset_code", "资产主编号"),
    ("custody_asset_code", "托管房源号"),
    ("renovation_vendor", "装修服务商"),
    ("data_date", "数据日期"),
    ("initial_transfer_amount", "初始受让金额"),
    ("repaid_amount", "已还款金额"),
    ("remaining_amount", "剩余还款金额"),
    ("asset_status", "资产状态"),
    ("last_renovation_payment_date", "最后一期装修款付款时间"),
    ("community_name", "小区名称"),
    ("city", "城市"),
    ("collection_contract_code", "收房合同编码"),
    ("custody_agreement_sign_date", "托管协议签署日期"),
    ("collection_contract_years", "收房合同签约年数"),
    ("owner_code", "业主代码"),
    ("withholding_ratio", "代扣比例"),
    ("actual_monthly_rent", "实际出房月租金"),
    ("overdue_days", "逾期天数"),
    ("asset_transfer_discount_rate", "资产转让折扣率(%)"),
    ("source_file_name", "文件名"),
    ("source_sheet_name", "Sheet名"),
    ("synced_at", "同步时间"),
    ("created_at", "创建时间"),
    ("last_payment_date", "最后回款日"),
    ("max_payment_date", "最大回款日"),
    ("risk_score", "风险评分"),
    ("risk_level", "风险等级"),
    ("id", "ID"),
    ("trust_product_id", "产品ID"),
    ("trust_asset_id", "资产ID"),
)

MONITOR_PREVIEW_MONEY_FIELDS = frozenset(
    {"initial_transfer_amount", "repaid_amount", "remaining_amount", "actual_monthly_rent"}
)
MONITOR_PREVIEW_RATE_FIELDS = frozenset(
    {"withholding_ratio", "asset_transfer_discount_rate"}
)


def _jsonable_val(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v.isoformat()
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, (int, float, str, bool)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {k: _jsonable_val(v) for k, v in dict(row._mapping).items()}


def _bucket_display(bucket: str | None, overdue_days: int | None) -> str:
    label = DELINQUENCY_BUCKET_LABELS.get(bucket or "", bucket or "—")
    if overdue_days is None:
        return str(label)
    return f"{label} · {overdue_days}天"


# ── 回购单位主数据 ─────────────────────────────────────────────


def _validate_unit_fields(
    company_name: str, contact_name: str, contact_email: str
) -> tuple[str, str, str]:
    company = (company_name or "").strip()
    contact = (contact_name or "").strip()
    email = (contact_email or "").strip()
    if not company:
        raise HTTPException(status_code=400, detail="公司名称不能为空")
    if len(company) > 200:
        raise HTTPException(status_code=400, detail="公司名称过长")
    if not contact:
        raise HTTPException(status_code=400, detail="联系人不能为空")
    if not email or not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    return company, contact, email


def list_units(conn: Connection, include_inactive: bool = True) -> list[dict[str, Any]]:
    where = "" if include_inactive else "WHERE status = 'active'"
    rows = conn.execute(
        text(f"""
            SELECT id, company_name, contact_name, contact_email, status,
                   created_at, updated_at
            FROM asset_repurchase_units
            {where}
            ORDER BY status ASC, company_name ASC
        """)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_unit(conn: Connection, unit_id: int) -> dict[str, Any]:
    row = conn.execute(
        text("SELECT * FROM asset_repurchase_units WHERE id = :id"),
        {"id": unit_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="回购单位不存在")
    return _row_to_dict(row)


def create_unit(
    conn: Connection,
    *,
    company_name: str,
    contact_name: str,
    contact_email: str,
) -> dict[str, Any]:
    company, contact, email = _validate_unit_fields(
        company_name, contact_name, contact_email
    )
    dup = conn.execute(
        text("SELECT 1 FROM asset_repurchase_units WHERE company_name = :name"),
        {"name": company},
    ).fetchone()
    if dup:
        raise HTTPException(status_code=400, detail=f"公司「{company}」已存在")
    row = conn.execute(
        text("""
            INSERT INTO asset_repurchase_units (company_name, contact_name, contact_email)
            VALUES (:company, :contact, :email)
            RETURNING id
        """),
        {"company": company, "contact": contact, "email": email},
    ).fetchone()
    return get_unit(conn, int(row.id))


def update_unit(
    conn: Connection,
    unit_id: int,
    *,
    company_name: str | None = None,
    contact_name: str | None = None,
    contact_email: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    current = get_unit(conn, unit_id)
    company, contact, email = _validate_unit_fields(
        company_name if company_name is not None else current["company_name"],
        contact_name if contact_name is not None else current["contact_name"],
        contact_email if contact_email is not None else current["contact_email"],
    )
    new_status = (status or current["status"] or "active").strip()
    if new_status not in ("active", "inactive"):
        raise HTTPException(status_code=400, detail="单位状态无效")
    dup = conn.execute(
        text("""
            SELECT 1 FROM asset_repurchase_units
            WHERE company_name = :name AND id <> :id
        """),
        {"name": company, "id": unit_id},
    ).fetchone()
    if dup:
        raise HTTPException(status_code=400, detail=f"公司「{company}」已存在")
    conn.execute(
        text("""
            UPDATE asset_repurchase_units
            SET company_name = :company,
                contact_name = :contact,
                contact_email = :email,
                status = :status,
                updated_at = NOW()
            WHERE id = :id
        """),
        {
            "company": company,
            "contact": contact,
            "email": email,
            "status": new_status,
            "id": unit_id,
        },
    )
    return get_unit(conn, unit_id)


# ── 资产查询（按资产主编号聚合最新监控快照层）──────────────────


def _product_name(conn: Connection, product_id: int) -> str:
    row = conn.execute(
        text("SELECT name FROM trust_products WHERE id = :id"),
        {"id": product_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=400, detail=f"信托产品 {product_id} 不存在")
    return str(row.name)


def _active_repurchased_codes(
    conn: Connection, trust_product_id: int
) -> set[str]:
    """产品下已存在生效（completed）回购单的资产主编号集合。"""
    rows = conn.execute(
        text("""
            SELECT DISTINCT a.asset_code
            FROM asset_repurchase_assets a
            JOIN asset_repurchase_orders o ON o.id = a.repurchase_order_id
            WHERE a.trust_product_id = :pid
              AND o.status = 'completed'
        """),
        {"pid": trust_product_id},
    ).fetchall()
    return {str(r.asset_code) for r in rows}


def _historical_codes_sql() -> str:
    """该主编号在监控全历史 + trust_assets 中涉及的 distinct custody 编号。"""
    return """
        SELECT STRING_AGG(DISTINCT code, ',' ORDER BY code)
        FROM (
            SELECT NULLIF(TRIM(h.custody_asset_code), '') AS code
            FROM trust_asset_monitor_records h
            WHERE h.trust_product_id = agg.trust_product_id
              AND h.asset_code = agg.asset_code
            UNION
            SELECT NULLIF(TRIM(t.custody_asset_code), '')
            FROM trust_assets t
            WHERE t.trust_product_id = agg.trust_product_id
              AND t.asset_code = agg.asset_code
        ) codes
        WHERE code IS NOT NULL
    """


def _aggregated_assets_sql(asset_filter: str = "") -> str:
    """最新监控快照层按 asset_code 聚合 + 历史房源号 + 城市。"""
    return f"""
        SELECT
            agg.*,
            ({_historical_codes_sql()}) AS historical_property_codes,
            city_pick.city AS city
        FROM (
            SELECT
                r.trust_product_id,
                r.asset_code,
                MAX(r.data_date)                 AS monitor_data_date,
                SUM(r.initial_transfer_amount)   AS initial_transfer_amount,
                SUM(r.repaid_amount)             AS repaid_amount,
                SUM(r.remaining_amount)          AS remaining_amount,
                MAX(r.overdue_days)              AS overdue_days,
                MAX(r.asset_status)              AS asset_status,
                MAX(r.community_name)            AS community_name,
                COUNT(*)                         AS split_count,
                STRING_AGG(DISTINCT r.id::text, ',' ORDER BY r.id::text)
                                                 AS source_monitor_record_ids
            FROM trust_asset_monitor_records r
            {au._monitor_latest_snapshot_join_sql()}
            WHERE r.trust_product_id = :pid
              {asset_filter}
            GROUP BY r.trust_product_id, r.asset_code
        ) agg
        LEFT JOIN LATERAL (
            SELECT NULLIF(TRIM(i.city), '') AS city
            FROM trust_product_issuance_asset_records i
            WHERE i.trust_product_id = agg.trust_product_id
              AND (
                  split_part(i.custody_asset_code, '-', 1) = agg.asset_code
                  OR i.custody_asset_code = agg.asset_code
              )
            ORDER BY i.issue_date DESC NULLS LAST, i.id DESC
            LIMIT 1
        ) city_pick ON TRUE
    """


def _fetch_monitor_preview_records(
    conn: Connection,
    *,
    trust_product_id: int,
    asset_codes: list[str],
) -> list[dict[str, Any]]:
    """取所选主编号最新快照层的全部监控分笔，供回购预览完整展示。"""
    placeholders = ", ".join(f":monitor_ac_{i}" for i in range(len(asset_codes)))
    params: dict[str, Any] = {"monitor_pid": trust_product_id}
    for i, code in enumerate(asset_codes):
        params[f"monitor_ac_{i}"] = code
    rows = conn.execute(
        text(f"""
            SELECT
                r.*,
                tp.name AS trust_product_name,
                iss.city AS issuance_city,
                iss.asset_transfer_discount_rate
            FROM trust_asset_monitor_records r
            JOIN trust_products tp ON tp.id = r.trust_product_id
            {au._monitor_latest_snapshot_join_sql()}
            {au._monitor_issuance_lateral_join_sql()}
            WHERE r.trust_product_id = :monitor_pid
              AND r.asset_code IN ({placeholders})
            ORDER BY r.asset_code, r.source_asset_code NULLS LAST,
                     r.custody_asset_code NULLS LAST, r.id
        """),
        params,
    ).fetchall()
    items = []
    for row in rows:
        item = _row_to_dict(row)
        if not item.get("city"):
            item["city"] = item.get("issuance_city")
        item.pop("issuance_city", None)
        items.append(item)
    return items


def _decorate_asset_item(item: dict[str, Any]) -> dict[str, Any]:
    overdue = item.get("overdue_days")
    overdue_i = int(overdue) if overdue is not None else None
    remaining = float(item.get("remaining_amount") or 0)
    bucket = calc_delinquency_bucket(overdue_i, remaining, tolerance=TOLERANCE)
    item["overdue_days"] = overdue_i
    item["remaining_amount"] = round(remaining, 2)
    item["delinquency_bucket"] = bucket
    item["delinquency_bucket_display"] = _bucket_display(bucket, overdue_i)
    item["city"] = item.get("city") or "—"
    item["historical_property_codes"] = item.get("historical_property_codes") or ""
    return item


def fetch_repurchasable_assets(
    conn: Connection, trust_product_id: int
) -> dict[str, Any]:
    """产品下按主编号聚合的最新监控资产（含已回购标记）。"""
    product_name = _product_name(conn, trust_product_id)
    repurchased = _active_repurchased_codes(conn, trust_product_id)
    rows = conn.execute(
        text(f"""
            {_aggregated_assets_sql()}
            ORDER BY agg.remaining_amount DESC NULLS LAST, agg.asset_code ASC
        """),
        {"pid": trust_product_id},
    ).fetchall()
    items = []
    for r in rows:
        item = _decorate_asset_item(_row_to_dict(r))
        item["already_repurchased"] = item["asset_code"] in repurchased
        items.append(item)
    return {
        "trust_product_id": trust_product_id,
        "trust_product_name": product_name,
        "asset_count": len(items),
        "items": items,
    }


def parse_repurchase_asset_codes(raw: list[str] | None) -> list[str]:
    if not raw:
        raise HTTPException(status_code=400, detail="请至少选择一个资产主编号")
    seen: set[str] = set()
    result: list[str] = []
    for part in raw:
        code = str(part).strip()
        if not code or code in seen:
            continue
        seen.add(code)
        result.append(code)
    if not result:
        raise HTTPException(status_code=400, detail="请至少选择一个资产主编号")
    if len(result) > MAX_REPURCHASE_ASSETS:
        raise HTTPException(
            status_code=400,
            detail=f"单次回购资产最多 {MAX_REPURCHASE_ASSETS} 个",
        )
    return result


def _normalize_amounts(amounts: dict | None) -> dict[str, float]:
    result: dict[str, float] = {}
    for code, value in (amounts or {}).items():
        key = str(code).strip()
        if not key or value is None or str(value).strip() == "":
            continue
        try:
            amt = round(float(value), 2)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400, detail=f"资产 {key} 的回购金额格式不正确"
            )
        if amt < 0:
            raise HTTPException(
                status_code=400, detail=f"资产 {key} 的回购金额不能为负数"
            )
        result[key] = amt
    return result


def build_repurchase_preview(
    conn: Connection,
    *,
    trust_product_id: int,
    asset_codes: list[str],
    repurchase_unit_id: int,
    repurchase_business_date: date,
    amounts: dict | None = None,
) -> dict[str, Any]:
    """预览回购（只读，不写库）：重取最新监控聚合 + 单位校验 + 查重。"""
    codes = parse_repurchase_asset_codes(asset_codes)
    product_name = _product_name(conn, trust_product_id)

    unit = get_unit(conn, repurchase_unit_id)
    if unit["status"] != "active":
        raise HTTPException(
            status_code=400,
            detail=f"回购单位「{unit['company_name']}」已停用",
        )

    repurchased = _active_repurchased_codes(conn, trust_product_id)
    dup = [c for c in codes if c in repurchased]
    if dup:
        joined = "、".join(dup[:5])
        raise HTTPException(
            status_code=400,
            detail=f"以下资产已存在生效回购单，不可重复回购：{joined}",
        )

    placeholders = ", ".join(f":ac_{i}" for i in range(len(codes)))
    params: dict[str, Any] = {"pid": trust_product_id}
    for i, code in enumerate(codes):
        params[f"ac_{i}"] = code
    rows = conn.execute(
        text(f"""
            {_aggregated_assets_sql(f"AND r.asset_code IN ({placeholders})")}
            ORDER BY agg.asset_code ASC
        """),
        params,
    ).fetchall()
    found = {str(r.asset_code): _decorate_asset_item(_row_to_dict(r)) for r in rows}
    missing = [c for c in codes if c not in found]
    if missing:
        joined = "、".join(missing[:5])
        raise HTTPException(
            status_code=400,
            detail=f"以下资产在所选产品下无最新监控数据：{joined}",
        )

    amount_map = _normalize_amounts(amounts)
    unknown_amounts = [c for c in amount_map if c not in found]
    if unknown_amounts:
        joined = "、".join(sorted(unknown_amounts)[:5])
        raise HTTPException(
            status_code=400,
            detail=f"以下回购金额对应的资产不在本次选择中：{joined}",
        )

    assets = []
    for code in codes:
        item = found[code]
        remaining = float(item["remaining_amount"] or 0)
        # 默认 = 监控剩余金额；确认前允许修改
        repurchase_amount = amount_map.get(code, round(remaining, 2))
        assets.append({**item, "repurchase_amount": repurchase_amount})

    total_remaining = round(sum(float(a["remaining_amount"] or 0) for a in assets), 2)
    total_repurchase = round(sum(float(a["repurchase_amount"]) for a in assets), 2)
    monitor_records = _fetch_monitor_preview_records(
        conn,
        trust_product_id=trust_product_id,
        asset_codes=codes,
    )

    return {
        "trust_product_id": trust_product_id,
        "trust_product_name": product_name,
        "repurchase_unit_id": int(unit["id"]),
        "unit_company_name": unit["company_name"],
        "unit_contact_name": unit["contact_name"],
        "unit_contact_email": unit["contact_email"],
        "repurchase_business_date": repurchase_business_date.isoformat(),
        "asset_count": len(assets),
        "total_remaining": total_remaining,
        "total_repurchase_amount": total_repurchase,
        "assets": assets,
        "monitor_columns": [
            {
                "key": key,
                "label": label,
                "format": (
                    "money"
                    if key in MONITOR_PREVIEW_MONEY_FIELDS
                    else "rate"
                    if key in MONITOR_PREVIEW_RATE_FIELDS
                    else "default"
                ),
            }
            for key, label in MONITOR_PREVIEW_COLUMNS
        ],
        "monitor_records": monitor_records,
        "note": (
            "预览不写库。确认回购后仅写入回购新表，"
            "不修改资产监控导入表、发行表与还款表。"
        ),
    }


# ── 执行 / 订单 / 失效 ─────────────────────────────────────────


def execute_repurchase(
    conn: Connection,
    *,
    trust_product_id: int,
    asset_codes: list[str],
    repurchase_unit_id: int,
    repurchase_business_date: date,
    amounts: dict | None = None,
    note: str | None = None,
    executed_by: str | None = None,
) -> dict[str, Any]:
    """执行回购：服务端重建预览（重校验），单事务写 asset_repurchase_* 新表。"""
    preview = build_repurchase_preview(
        conn,
        trust_product_id=trust_product_id,
        asset_codes=asset_codes,
        repurchase_unit_id=repurchase_unit_id,
        repurchase_business_date=repurchase_business_date,
        amounts=amounts,
    )
    row = conn.execute(
        text("""
            INSERT INTO asset_repurchase_orders (
                trust_product_id, trust_product_name,
                repurchase_unit_id, unit_company_name,
                unit_contact_name, unit_contact_email,
                repurchase_business_date, asset_count,
                total_remaining, total_repurchase_amount,
                status, note, executed_by
            ) VALUES (
                :pid, :pname, :uid, :company, :contact, :email,
                :biz_date, :count, :total_remaining, :total_repurchase,
                'completed', :note, :executed_by
            )
            RETURNING id, executed_at
        """),
        {
            "pid": preview["trust_product_id"],
            "pname": preview["trust_product_name"],
            "uid": preview["repurchase_unit_id"],
            "company": preview["unit_company_name"],
            "contact": preview["unit_contact_name"],
            "email": preview["unit_contact_email"],
            "biz_date": repurchase_business_date,
            "count": preview["asset_count"],
            "total_remaining": preview["total_remaining"],
            "total_repurchase": preview["total_repurchase_amount"],
            "note": (note or "").strip() or None,
            "executed_by": executed_by,
        },
    ).fetchone()
    order_id = int(row.id)
    for a in preview["assets"]:
        conn.execute(
            text("""
                INSERT INTO asset_repurchase_assets (
                    repurchase_order_id, asset_code,
                    trust_product_id, trust_product_name,
                    historical_property_codes, monitor_data_date,
                    initial_transfer_amount, repaid_amount, remaining_amount,
                    repurchase_amount, overdue_days, delinquency_bucket,
                    asset_status, split_count, city, community_name,
                    source_monitor_record_ids
                ) VALUES (
                    :oid, :asset_code, :pid, :pname,
                    :hist_codes, :data_date,
                    :initial, :repaid, :remaining,
                    :repurchase_amount, :overdue_days, :bucket,
                    :asset_status, :split_count, :city, :community,
                    :monitor_ids
                )
            """),
            {
                "oid": order_id,
                "asset_code": a["asset_code"],
                "pid": preview["trust_product_id"],
                "pname": preview["trust_product_name"],
                "hist_codes": a.get("historical_property_codes") or None,
                "data_date": a.get("monitor_data_date"),
                "initial": a.get("initial_transfer_amount"),
                "repaid": a.get("repaid_amount"),
                "remaining": a.get("remaining_amount"),
                "repurchase_amount": a.get("repurchase_amount"),
                "overdue_days": a.get("overdue_days"),
                "bucket": a.get("delinquency_bucket"),
                "asset_status": a.get("asset_status"),
                "split_count": int(a.get("split_count") or 0),
                "city": None if a.get("city") in (None, "—") else a.get("city"),
                "community": a.get("community_name"),
                "monitor_ids": a.get("source_monitor_record_ids") or None,
            },
        )
    return {
        "order_id": order_id,
        "executed_at": _jsonable_val(row.executed_at),
        "repurchase_business_date": repurchase_business_date.isoformat(),
        "status": "completed",
        "asset_count": preview["asset_count"],
        "total_repurchase_amount": preview["total_repurchase_amount"],
    }


def _monitor_import_after(
    conn: Connection, trust_product_id: int, after_ts: Any
) -> bool:
    row = conn.execute(
        text("""
            SELECT 1
            FROM assetinfo_pipeline_runs
            WHERE trust_product_id = :pid
              AND inserted_monitor_count > 0
              AND created_at > :after_ts
            LIMIT 1
        """),
        {"pid": trust_product_id, "after_ts": after_ts},
    ).fetchone()
    return row is not None


def can_void_order(
    conn: Connection, order: dict[str, Any]
) -> tuple[bool, str | None]:
    if order.get("status") == "voided":
        return False, "该回购单已失效"
    if _monitor_import_after(
        conn, int(order["trust_product_id"]), order.get("executed_at")
    ):
        return False, "回购后已对该信托产品进行过新的资产监控表导入，不可失效"
    return True, None


def list_orders(conn: Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("""
            SELECT *
            FROM asset_repurchase_orders
            ORDER BY executed_at DESC, id DESC
            LIMIT :lim
        """),
        {"lim": limit},
    ).fetchall()
    items = []
    for r in rows:
        d = _row_to_dict(r)
        ok, reason = can_void_order(conn, d)
        d["can_void"] = ok
        d["void_block_reason"] = reason
        items.append(d)
    return items


def get_order(conn: Connection, order_id: int) -> dict[str, Any]:
    row = conn.execute(
        text("SELECT * FROM asset_repurchase_orders WHERE id = :id"),
        {"id": order_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="回购单不存在")
    order = _row_to_dict(row)
    ok, reason = can_void_order(conn, order)
    order["can_void"] = ok
    order["void_block_reason"] = reason
    assets = []
    for r in conn.execute(
        text("""
            SELECT *
            FROM asset_repurchase_assets
            WHERE repurchase_order_id = :oid
            ORDER BY asset_code
        """),
        {"oid": order_id},
    ).fetchall():
        a = _row_to_dict(r)
        a["delinquency_bucket_display"] = _bucket_display(
            a.get("delinquency_bucket"),
            int(a["overdue_days"]) if a.get("overdue_days") is not None else None,
        )
        assets.append(a)
    order["assets"] = assets
    return order


def void_order(
    conn: Connection,
    order_id: int,
    *,
    voided_by: str | None = None,
) -> dict[str, Any]:
    order = get_order(conn, order_id)
    ok, reason = can_void_order(conn, order)
    if not ok:
        raise HTTPException(status_code=400, detail=reason or "不可失效")
    conn.execute(
        text("""
            UPDATE asset_repurchase_orders
            SET status = 'voided',
                voided_at = NOW(),
                voided_by = :voided_by
            WHERE id = :id AND status = 'completed'
        """),
        {"id": order_id, "voided_by": voided_by},
    )
    return {"order_id": order_id, "status": "voided", "voided_by": voided_by}
