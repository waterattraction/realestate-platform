"""数据披露：活数据预览、多快照冻结、模版导出。"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from typing import Any, Optional
import zipfile

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import assetinfo_templates as templates
from app import assetinfo_upload
from app import query_utils
from app import timeutil
from app.disclosure_attribution import (
    STATUS_REPURCHASED,
    STATUS_SWAP_OUT,
    apply_monitor_amounts_from_attribution,
    apply_product_from_attribution,
    apply_triad_from_attribution,
    build_attribution_index,
    load_repurchased_asset_codes,
    load_swap_out_pairs,
)
from app.overdue.buckets import (
    RECONCILIATION_TOLERANCE_DEFAULT,
    calc_delinquency_bucket,
)

EXPORT_MAX = assetinfo_upload.MONITOR_EXPORT_MAX
PREVIEW_DEFAULT_LIMIT = 200
_REPAYMENT_EXPORT_FIXED_TITLE = "还款明细披露信息"
_MONITOR_EXPORT_FIXED_TITLE = "资产监控表"
_FILENAME_FORBIDDEN = '<>:"/\\|?*'

DETAIL_COLS = templates.template_field_keys(templates.REPAYMENT_DETAIL_TEMPLATE_COLUMNS)
PLAN_COLS = templates.template_field_keys(templates.REPAYMENT_PLAN_TEMPLATE_COLUMNS)
MONITOR_COLS = templates.template_field_keys(
    templates.DISCLOSURE_MONITOR_TEMPLATE_COLUMNS
)

# 披露「资产状态」按 M 级覆写
_DISCLOSURE_STATUS_BY_BUCKET = {
    "ES": "提前结清",
    "M0": "正常",
    "M0_5": "轻度",
    "M1": "轻度",
    "M1_PLUS": "轻度",
    "SD": "重度",
}


def _normalize_disclosure_m_bucket(code: str | None) -> str | None:
    if code is None:
        return None
    raw = str(code).strip().upper().replace(" ", "")
    if not raw:
        return None
    aliases = {
        "ES": "ES",
        "M0": "M0",
        "M05": "M0_5",
        "M0.5": "M0_5",
        "M0_5": "M0_5",
        "M1": "M1",
        "M1+": "M1_PLUS",
        "M1_PLUS": "M1_PLUS",
        "SD": "SD",
    }
    return aliases.get(raw, raw)


def disclosure_monitor_asset_status(
    *,
    overdue_days: Any,
    remaining_amount: Any,
    fallback_status: Any = None,
    has_severe_followup: bool = False,
    force_status: Any = None,
) -> Any:
    """披露用资产状态。

    优先级：
    1. 强制业务态「已回购」「已置换转出」（高于 M 级与重度跟进）
    2. 存在活跃「重度逾期」跟进事项 → 重度
    3. M 级：ES→提前结清，M0→正常，M0.5/M1/M1+→轻度，SD→重度
       （转入资产、无强制业务态时走本级）
    4. 其余保留导入原值
    """
    if force_status:
        return force_status
    if has_severe_followup:
        return "重度"
    try:
        rem = float(remaining_amount) if remaining_amount is not None else 0.0
    except (TypeError, ValueError):
        rem = 0.0
    od: int | None
    try:
        od = int(overdue_days) if overdue_days is not None else None
    except (TypeError, ValueError):
        od = None
    bucket = _normalize_disclosure_m_bucket(
        calc_delinquency_bucket(od, rem, tolerance=RECONCILIATION_TOLERANCE_DEFAULT)
    )
    mapped = _status_from_m_bucket(bucket)
    if mapped is not None:
        return mapped
    # 兼容源数据将 M 级代码写在资产状态列（含 SD）
    mapped = _status_from_m_bucket(_normalize_disclosure_m_bucket(fallback_status))
    if mapped is not None:
        return mapped
    return fallback_status


def monitor_force_business_status(
    *,
    is_repurchased: bool,
    is_swap_out_view: bool,
) -> str | None:
    """监控披露强制业务态：仅转出方/已回购；转入方返回 None（走 M 级）。"""
    if is_repurchased:
        return STATUS_REPURCHASED
    if is_swap_out_view:
        return STATUS_SWAP_OUT
    return None


def _status_from_m_bucket(bucket: str | None) -> str | None:
    if not bucket:
        return None
    return _DISCLOSURE_STATUS_BY_BUCKET.get(bucket)


# 披露监控：仅这些状态展示逾期天数
_DISCLOSURE_OVERDUE_VISIBLE_STATUSES = frozenset({"轻度", "重度"})


def _apply_disclosure_monitor_row(
    row: dict[str, Any],
    *,
    severe_followup_keys: set[tuple[int, str]] | None = None,
    force_status: Any = None,
) -> dict[str, Any]:
    out = dict(row)
    pid = out.get("trust_product_id")
    ac = str(out.get("asset_code") or "").strip()
    has_severe = False
    if severe_followup_keys and pid is not None and ac:
        has_severe = (int(pid), ac) in severe_followup_keys
    out["asset_status"] = disclosure_monitor_asset_status(
        overdue_days=out.get("overdue_days"),
        remaining_amount=out.get("remaining_amount"),
        fallback_status=out.get("asset_status"),
        has_severe_followup=has_severe,
        force_status=force_status,
    )
    # 披露展示/冻结：仅轻度/重度显示逾期天数；已回购/已置换转出/正常等置空
    status = out.get("asset_status")
    if status in _DISCLOSURE_OVERDUE_VISIBLE_STATUSES:
        if out.get("overdue_days") is None:
            out["overdue_days"] = 0
    else:
        out["overdue_days"] = None
    return out


def _blank_repayment_overdue_if_normal(
    row: dict[str, Any],
    *,
    monitor_remaining_amount: Any = None,
) -> None:
    """还款明细披露：披露状态为「正常」时当期逾期天数置空。"""
    rem = monitor_remaining_amount
    if rem is None:
        rem = row.get("remaining_balance")
    if rem is None:
        rem = row.get("remaining_amount")
    status = disclosure_monitor_asset_status(
        overdue_days=row.get("overdue_days"),
        remaining_amount=rem,
        fallback_status=None,
    )
    if status == "正常":
        row["overdue_days"] = None
    row.pop("_monitor_remaining_amount", None)


def _fetch_active_severe_followup_keys(
    conn: Connection, product_ids: list[int]
) -> set[tuple[int, str]]:
    """活跃（open / in_progress）且分类为「重度逾期」的 (trust_product_id, asset_code)。"""
    if not product_ids:
        return set()
    prod_sql, prod_params = query_utils.sql_in_int_column(
        "c.trust_product_id", product_ids, param_prefix="sftp"
    )
    rows = conn.execute(
        text(
            f"""
            SELECT DISTINCT c.trust_product_id, c.asset_code
            FROM trust_overdue_followup_cases c
            WHERE c.category = '重度逾期'
              AND c.status IN ('open', 'in_progress')
              AND c.asset_code IS NOT NULL
              AND TRIM(c.asset_code) <> ''
              {prod_sql}
            """
        ),
        prod_params,
    ).fetchall()
    return {
        (int(r.trust_product_id), str(r.asset_code).strip())
        for r in rows
        if r.trust_product_id is not None and r.asset_code
    }


def _jsonable(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        # 系统时间统一北京时间展示（含 frozen_at 等）
        return timeutil.format_beijing_datetime(v) or v.isoformat()
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
    return out


def _row_asset_tuple(row: dict[str, Any]) -> tuple[str, str | None]:
    ac = str(row.get("asset_code") or "").strip()
    cac = str(row.get("custody_asset_code") or "").strip() or None
    return ac or (cac or ""), cac


def _product_name_map(conn: Connection, product_ids: list[int]) -> dict[int, str]:
    if not product_ids:
        return {}
    rows = conn.execute(
        text("SELECT id, name FROM trust_products WHERE id = ANY(CAST(:pids AS bigint[]))"),
        {"pids": _pg_bigint_array_literal(product_ids)},
    ).fetchall()
    return {int(r.id): str(r.name) for r in rows}


def _attributed_product_id(
    row: dict[str, Any], attr: Any
) -> int | None:
    if attr is not None and getattr(attr, "trust_product_id", None) is not None:
        return int(attr.trust_product_id)
    pid = row.get("trust_product_id")
    return int(pid) if pid is not None else None


# ── live queries ──────────────────────────────────────────────


def fetch_repayment_live(
    conn: Connection,
    product_ids: list[int],
    as_of: date,
    *,
    as_of_start: date | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """明细：截止日当天且实际还款 > 0；计划：各产品 data_date≤as_of 最新一批。

    ``as_of`` = 披露截止日：明细裁切、计划批次、回购/置换/发行归属均只用此日（不受开始日影响）。
    ``as_of_start`` = 披露开始日：仅用于范围内手工结算并入「当期实际还款金额」；
    省略时等同单日（``as_of_start = as_of``）。
    累计已还 / 剩余应还、回款计划已还 / 剩余：叠加全部历史手工结算。

    归属 / 三列 / 已回购排除：见 disclosure_attribution。
    """
    start = as_of_start if as_of_start is not None else as_of
    if start > as_of:
        raise HTTPException(status_code=400, detail="披露开始日不能晚于截止日")
    selected = set(int(x) for x in product_ids)
    params = {"as_of": as_of}
    detail_rows = conn.execute(
        text(
            """
            SELECT r.*, tp.name AS trust_product_name,
                   mon.overdue_days AS overdue_days,
                   mon.remaining_amount AS _monitor_remaining_amount
            FROM trust_repayment_detail_records r
            JOIN trust_products tp ON tp.id = r.trust_product_id
            LEFT JOIN LATERAL (
                SELECT m.overdue_days, m.remaining_amount
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
            WHERE r.repayment_date = :as_of
              AND r.actual_repayment_amount > 0
            ORDER BY r.trust_product_id, r.repayment_date, r.id
            """
        ),
        params,
    ).fetchall()
    details_raw = [_normalize_item(_row_dict(r)) for r in detail_rows]

    plan_rows = conn.execute(
        text(
            """
            WITH latest AS (
                SELECT trust_product_id, MAX(data_date) AS data_date
                FROM trust_repayment_plan_records
                WHERE data_date <= :as_of
                GROUP BY trust_product_id
            )
            SELECT p.*, tp.name AS trust_product_name
            FROM trust_repayment_plan_records p
            JOIN trust_products tp ON tp.id = p.trust_product_id
            INNER JOIN latest l
              ON l.trust_product_id = p.trust_product_id
             AND l.data_date = p.data_date
            ORDER BY p.trust_product_id, p.id
            """
        ),
        params,
    ).fetchall()
    plans_raw = [_normalize_item(_row_dict(r)) for r in plan_rows]

    asset_tuples = [_row_asset_tuple(r) for r in details_raw + plans_raw]
    attrs = build_attribution_index(conn, as_of, asset_tuples)
    repurchased = load_repurchased_asset_codes(conn, as_of)
    name_by_id = _product_name_map(conn, list(selected))

    details: list[dict[str, Any]] = []
    for row in details_raw:
        key, _ = _row_asset_tuple(row)
        if key and key in repurchased:
            continue
        attr = attrs.get(key) if key else None
        apply_product_from_attribution(row, attr, name_by_id=name_by_id)
        apply_triad_from_attribution(row, attr)
        pid = _attributed_product_id(row, attr)
        if pid is None or pid not in selected:
            continue
        _blank_repayment_overdue_if_normal(
            row,
            monitor_remaining_amount=row.get("_monitor_remaining_amount"),
        )
        details.append(row)

    plans: list[dict[str, Any]] = []
    for row in plans_raw:
        key, _ = _row_asset_tuple(row)
        if key and key in repurchased:
            continue
        attr = attrs.get(key) if key else None
        apply_product_from_attribution(row, attr, name_by_id=name_by_id)
        apply_monitor_amounts_from_attribution(row, attr)
        pid = _attributed_product_id(row, attr)
        if pid is None or pid not in selected:
            continue
        plans.append(row)

    from app import manual_settlement as ms

    all_sums = ms.settlement_sums_by_asset_code(conn, product_ids=product_ids)
    range_sums = ms.settlement_sums_by_asset_code(
        conn, product_ids=product_ids, date_from=start, date_to=as_of
    )

    covered: set[tuple[int, str]] = set()
    for i, row in enumerate(details):
        key, _ = _row_asset_tuple(row)
        pid = int(row.get("trust_product_id") or 0)
        if key:
            covered.add((pid, key))
        range_s = float(range_sums.get((pid, key), 0) or 0) if key else 0.0
        if range_s:
            row["actual_repayment_amount"] = (
                float(row.get("actual_repayment_amount") or 0) + range_s
            )
        all_s = float(all_sums.get((pid, key), 0) or 0) if key else 0.0
        if all_s:
            details[i] = ms.overlay_repayment_detail_amounts(row, all_s)

    for i, row in enumerate(plans):
        key, _ = _row_asset_tuple(row)
        pid = int(row.get("trust_product_id") or 0)
        all_s = float(all_sums.get((pid, key), 0) or 0) if key else 0.0
        if all_s:
            plans[i] = ms.overlay_monitor_amounts(row, all_s)

    # 范围内有手工结算、但截止日无明细事实行：按资产汇总追加虚拟行
    settlements_in_range = ms.fetch_settlements_for_disclosure(
        conn, product_ids, date_from=start, date_to=as_of
    )
    settlement_meta: dict[tuple[int, str], dict[str, Any]] = {}
    for s in settlements_in_range:
        key = str(s.get("asset_code") or "").strip()
        if not key:
            continue
        pid = int(s["trust_product_id"]) if s.get("trust_product_id") is not None else None
        if pid is None:
            continue
        # 同资产多笔时保留最后一笔的还款方展示（ORDER BY date, id 已排序）
        settlement_meta[(pid, key)] = s

    plan_initial_by_asset: dict[tuple[int, str], Any] = {}
    for p in plans:
        key, _ = _row_asset_tuple(p)
        pid = int(p.get("trust_product_id") or 0)
        if not key or pid <= 0:
            continue
        if (pid, key) not in plan_initial_by_asset:
            plan_initial_by_asset[(pid, key)] = p.get("initial_transfer_amount")

    for (pid, key), range_s in range_sums.items():
        if range_s <= 0 or (pid, key) in covered:
            continue
        if key in repurchased or pid not in selected:
            continue
        s = settlement_meta.get((pid, key))
        if not s:
            continue
        vrow = ms.virtual_repayment_rows_from_settlements([s])[0]
        actual = float(range_s)
        vrow["actual_repayment_amount"] = actual
        vrow["planned_repayment_amount"] = actual
        vrow["current_payer"] = (str(s.get("repayer") or "").strip() or None)
        vrow["trust_product_name"] = s.get("trust_product_name")
        init_amt = plan_initial_by_asset.get((pid, key))
        if init_amt is not None:
            vrow["initial_renovation_amount"] = init_amt
        all_s = float(all_sums.get((pid, key), 0) or 0)
        if all_s:
            vrow = ms.overlay_repayment_detail_amounts(vrow, all_s)
        details.append(vrow)

    details.sort(
        key=lambda r: (
            int(r.get("trust_product_id") or 0),
            str(r.get("repayment_date") or ""),
            int(r.get("id") or 0),
        )
    )
    plans.sort(
        key=lambda r: (int(r.get("trust_product_id") or 0), int(r.get("id") or 0))
    )
    return details, plans


def fetch_monitor_live(
    conn: Connection,
    product_ids: list[int],
    as_of: date,
) -> list[dict[str, Any]]:
    selected = set(int(x) for x in product_ids)
    params = {"as_of": as_of}
    rows = conn.execute(
        text(
            """
            SELECT r.*, tp.name AS trust_product_name
            FROM trust_asset_monitor_records r
            JOIN trust_products tp ON tp.id = r.trust_product_id
            WHERE r.data_date = :as_of
            ORDER BY r.trust_product_id, r.id
            """
        ),
        params,
    ).fetchall()
    raw = [_normalize_item(_row_dict(r)) for r in rows]
    attrs = build_attribution_index(
        conn, as_of, [_row_asset_tuple(r) for r in raw]
    )
    repurchased = load_repurchased_asset_codes(conn, as_of)
    swap_outs = load_swap_out_pairs(conn, as_of)
    name_by_id = _product_name_map(conn, list(selected))
    severe_keys = _fetch_active_severe_followup_keys(conn, product_ids)
    from app import manual_settlement as ms

    settlement_sums = ms.settlement_sums_by_asset_code(conn, product_ids=product_ids)

    out: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for row in raw:
        key, _ = _row_asset_tuple(row)
        if not key:
            continue
        attr = attrs.get(key)
        original_pid = int(row["trust_product_id"]) if row.get("trust_product_id") is not None else None
        attributed_pid = (
            int(attr.trust_product_id)
            if attr is not None and attr.trust_product_id is not None
            else original_pid
        )

        # 转出方产品：强制「已置换转出」（或已回购），优先级高于 M 级
        if original_pid is not None and (original_pid, key) in swap_outs and original_pid in selected:
            display = dict(row)
            display["trust_product_id"] = original_pid
            if name_by_id.get(original_pid):
                display["trust_product_name"] = name_by_id[original_pid]
            total = float(settlement_sums.get((original_pid, key), 0) or 0)
            if total:
                display = ms.overlay_monitor_amounts(display, total)
            force = monitor_force_business_status(
                is_repurchased=key in repurchased,
                is_swap_out_view=True,
            )
            item = _apply_disclosure_monitor_row(
                display, severe_followup_keys=severe_keys, force_status=force
            )
            sig = (original_pid, key)
            if sig not in seen:
                seen.add(sig)
                out.append(item)

        # 归属产品（含转入方）：不标「已置换转出」，状态以 M 级为准（已回购除外）
        if attributed_pid is None or attributed_pid not in selected:
            continue
        # 已在转出方展示且归属仍是转出方时不重复
        if (
            original_pid is not None
            and (original_pid, key) in swap_outs
            and attributed_pid == original_pid
        ):
            continue

        display = dict(row)
        if attr is not None and attr.trust_product_id is not None:
            apply_product_from_attribution(display, attr, name_by_id=name_by_id)
            # 转入方（及归属产品）：金额用转入快照/胜出事件；状态走 M 级（已回购除外）
            apply_monitor_amounts_from_attribution(display, attr)
        pid_for_sum = int(display.get("trust_product_id") or attributed_pid or 0)
        total = float(settlement_sums.get((pid_for_sum, key), 0) or 0)
        if total:
            display = ms.overlay_monitor_amounts(display, total)
        force = monitor_force_business_status(
            is_repurchased=key in repurchased,
            is_swap_out_view=False,
        )
        item = _apply_disclosure_monitor_row(
            display, severe_followup_keys=severe_keys, force_status=force
        )
        sig = (int(item["trust_product_id"]), key)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(item)

    out.sort(
        key=lambda r: (int(r.get("trust_product_id") or 0), int(r.get("id") or 0))
    )
    return out


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
    as_of_start: date | None = None,
) -> dict[str, Any]:
    row = conn.execute(
        text(
            """
            INSERT INTO disclosure_snapshots (
                snapshot_type, as_of_date, as_of_start_date, product_ids, product_names,
                note, created_by, detail_row_count, plan_row_count, monitor_row_count
            ) VALUES (
                :stype, :as_of, :as_of_start, CAST(:pids AS bigint[]), :pnames,
                :note, :created_by, :dcount, :pcount, :mcount
            )
            RETURNING id, frozen_at, as_of_date, as_of_start_date, snapshot_type
            """
        ),
        {
            "stype": snapshot_type,
            "as_of": as_of,
            "as_of_start": as_of_start,
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
    as_of_start: date | None = None,
    note: Optional[str] = None,
    created_by: Optional[str] = None,
) -> dict[str, Any]:
    product_ids = _require_products(product_ids)
    start = as_of_start if as_of_start is not None else as_of
    details, plans = fetch_repayment_live(
        conn, product_ids, as_of, as_of_start=start
    )
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
        as_of_start=start,
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
                    current_payer, custody_asset_code, asset_code,
                    planned_repayment_amount, initial_renovation_amount,
                    cumulative_repaid_amount, remaining_balance,
                    actual_repayment_amount, overdue_days, source_record_id
                ) VALUES (
                    :sid, :tp, :tpn, :payer, :cac, :ac,
                    :pra, :ira, :cra, :rb, :ara, :od, :src
                )
                """
            ),
            {
                "sid": sid,
                "tp": d.get("trust_product_id"),
                "tpn": d.get("trust_product_name"),
                "payer": d.get("current_payer"),
                "cac": d.get("custody_asset_code"),
                "ac": d.get("asset_code"),
                "pra": d.get("planned_repayment_amount"),
                "ira": d.get("initial_renovation_amount"),
                "cra": d.get("cumulative_repaid_amount"),
                "rb": d.get("remaining_balance"),
                "ara": d.get("actual_repayment_amount"),
                "od": d.get("overdue_days"),
                "src": d.get("id"),
            },
        )
    for p in plans:
        conn.execute(
            text(
                """
                INSERT INTO disclosure_repayment_plan_rows (
                    snapshot_id, trust_product_id, trust_product_name,
                    source_asset_code, renovation_vendor, data_date,
                    initial_transfer_amount, repaid_amount, remaining_amount,
                    community_name, city, current_bill_date, repayment_amount_detail,
                    planned_monthly_repayment_amount, final_planned_repayment_amount,
                    source_record_id
                ) VALUES (
                    :sid, :tp, :tpn, :sac, :rv, :dd,
                    :ita, :ra, :rema, :cn, :city, :cbd, :rad,
                    :pmra, :fpra, :src
                )
                """
            ),
            {
                "sid": sid,
                "tp": p.get("trust_product_id"),
                "tpn": p.get("trust_product_name"),
                "sac": p.get("asset_code"),
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
        "as_of_start_date": snap.get("as_of_start_date"),
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
                    source_asset_code, renovation_vendor, data_date,
                    initial_transfer_amount, repaid_amount, remaining_amount,
                    asset_status, overdue_days, last_renovation_payment_date,
                    community_name, city,
                    collection_contract_code, custody_agreement_sign_date,
                    collection_contract_years, owner_code, withholding_ratio,
                    actual_monthly_rent, source_record_id
                ) VALUES (
                    :sid, :tp, :tpn, :sac, :rv, :dd,
                    :ita, :ra, :rema, :st, :od, :lrpd, :cn, :city,
                    :ccc, :casd, :ccy, :oc, :wr, :amr, :src
                )
                """
            ),
            {
                "sid": sid,
                "tp": r.get("trust_product_id"),
                "tpn": r.get("trust_product_name"),
                "sac": r.get("asset_code"),
                "rv": r.get("renovation_vendor"),
                "dd": r.get("data_date"),
                "ita": r.get("initial_transfer_amount"),
                "ra": r.get("repaid_amount"),
                "rema": r.get("remaining_amount"),
                "st": r.get("asset_status"),
                "od": r.get("overdue_days"),
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
            SELECT id, snapshot_type, as_of_date, as_of_start_date, frozen_at, product_ids,
                   product_names, note, detail_row_count, plan_row_count, monitor_row_count,
                   created_by
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
    # 模版「资产编号(房源)」= asset_code；旧快照兼容回填展示字段
    for d in details:
        if not d.get("asset_code"):
            d["asset_code"] = d.get("custody_asset_code")
    for p in plans:
        if not p.get("asset_code"):
            p["asset_code"] = p.get("source_asset_code")
    return details, plans


def load_snapshot_monitor(conn: Connection, snapshot_id: int) -> list[dict]:
    rows = [
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
    # 模版「资产编号(房源)」= asset_code（主编号）；快照表存于 source_asset_code
    for r in rows:
        if not r.get("asset_code"):
            r["asset_code"] = r.get("source_asset_code")
    return rows


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
    as_of_start: date | None = None,
    limit: int = PREVIEW_DEFAULT_LIMIT,
) -> dict:
    product_ids = _require_products(product_ids)
    start = as_of_start if as_of_start is not None else as_of
    details, plans = fetch_repayment_live(
        conn, product_ids, as_of, as_of_start=start
    )
    return {
        "mode": "live",
        "as_of_date": as_of.isoformat(),
        "as_of_start_date": start.isoformat(),
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
        "headers": templates.template_headers(
            templates.DISCLOSURE_MONITOR_TEMPLATE_COLUMNS
        ),
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
        "headers": templates.template_headers(
            templates.DISCLOSURE_MONITOR_TEMPLATE_COLUMNS
        ),
        "keys": MONITOR_COLS,
        "rows": rows[:limit],
    }


def export_repayment_xlsx(
    conn: Connection,
    *,
    product_ids: list[int] | None = None,
    as_of: date | None = None,
    as_of_start: date | None = None,
    snapshot_id: int | None = None,
) -> bytes:
    """活数据导出：单文件双 Sheet（还款明细 / 回款计划）。快照请用 export_repayment_snapshot_zip。"""
    if snapshot_id is not None:
        raise HTTPException(
            status_code=400,
            detail="快照导出请使用按产品 ZIP 接口",
        )
    product_ids = _require_products(product_ids)
    if as_of is None:
        raise HTTPException(status_code=400, detail="请提供披露截止日")
    start = as_of_start if as_of_start is not None else as_of
    details, plans = fetch_repayment_live(
        conn, product_ids, as_of, as_of_start=start
    )
    if len(details) > EXPORT_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"结果超过 {EXPORT_MAX} 条，请缩小范围",
        )
    return assetinfo_upload.build_repayment_disclosure_export_xlsx(details, plans)


def _as_of_label(value: Any) -> str:
    """快照业务日导出用 YYYYMMDD（xlsx / Sheet 名）。"""
    if isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    else:
        text_v = str(value or "").strip()
        if not text_v:
            raise HTTPException(status_code=400, detail="快照缺少披露截止日")
        try:
            d = date.fromisoformat(text_v[:10])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="快照披露截止日无效") from exc
    return d.strftime("%Y%m%d")


def _export_zip_datetime_label(value: Any = None) -> str:
    """ZIP 文件名用北京时间 YYYYMMDDHHMM（快照取 frozen_at，否则当前时刻）。"""
    if value is None:
        return timeutil.now_beijing().strftime("%Y%m%d%H%M")
    # 披露 API 已把 frozen_at 格式化为无时区的北京墙钟字符串，不可再按 UTC 解释
    if isinstance(value, str):
        text = value.strip().replace("T", " ")
        if (
            len(text) >= 16
            and text[4] == "-"
            and "+" not in value
            and "Z" not in value.upper()
            and "z" not in value
        ):
            try:
                dt = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
                return dt.strftime("%Y%m%d%H%M")
            except ValueError:
                try:
                    dt = datetime.strptime(text[:16], "%Y-%m-%d %H:%M")
                    return dt.strftime("%Y%m%d%H%M")
                except ValueError:
                    pass
    dt = timeutil.to_beijing(value)
    if dt is None:
        dt = timeutil.now_beijing()
    return dt.strftime("%Y%m%d%H%M")


def snapshot_export_zip_filename(title: str, frozen_at: Any = None) -> str:
    """{标题}-{YYYYMMDDHHMM}.zip（无「-按产品」后缀）。"""
    return f"{title}-{_export_zip_datetime_label(frozen_at)}.zip"


def _safe_export_filename_part(value: str) -> str:
    out = "".join("_" if ch in _FILENAME_FORBIDDEN else ch for ch in (value or "").strip())
    out = out.strip(" .")
    return out or "未命名产品"


def repayment_snapshot_sheet_names(as_of_label: str) -> tuple[str, str]:
    """明细 Sheet = {YYYYMMDD}已还款；计划 Sheet 固定「回款计划」。"""
    return f"{as_of_label}已还款", "回款计划"


def repayment_snapshot_product_filename(product_name: str, as_of_label: str) -> str:
    name = _safe_export_filename_part(product_name)
    return f"{name}-{_REPAYMENT_EXPORT_FIXED_TITLE}-{as_of_label}.xlsx"


def export_repayment_snapshot_zip(
    conn: Connection, snapshot_id: int
) -> tuple[bytes, str]:
    """按信托产品拆多份 xlsx，打包为 ZIP。"""
    snap = get_snapshot(conn, snapshot_id)
    if not snap or snap.get("snapshot_type") != "repayment":
        raise HTTPException(status_code=404, detail="还款披露快照不存在")
    product_ids = [int(x) for x in (snap.get("product_ids") or [])]
    if not product_ids:
        raise HTTPException(status_code=400, detail="快照未包含信托产品")
    as_of_label = _as_of_label(snap.get("as_of_date"))
    detail_sheet, plan_sheet = repayment_snapshot_sheet_names(as_of_label)
    details, plans = load_snapshot_repayment(conn, snapshot_id)
    name_by_id = _product_name_map(conn, product_ids)
    for row in details + plans:
        pid = row.get("trust_product_id")
        tpn = row.get("trust_product_name")
        if pid is not None and tpn and int(pid) not in name_by_id:
            name_by_id[int(pid)] = str(tpn)

    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for pid in product_ids:
            product_name = name_by_id.get(pid) or str(pid)
            d_rows = [r for r in details if int(r.get("trust_product_id") or 0) == pid]
            p_rows = [r for r in plans if int(r.get("trust_product_id") or 0) == pid]
            xlsx = assetinfo_upload.build_repayment_disclosure_export_xlsx(
                d_rows,
                p_rows,
                detail_sheet_name=detail_sheet,
                plan_sheet_name=plan_sheet,
            )
            member = repayment_snapshot_product_filename(product_name, as_of_label)
            zf.writestr(member, xlsx)
    zip_name = snapshot_export_zip_filename(
        _REPAYMENT_EXPORT_FIXED_TITLE, snap.get("frozen_at")
    )
    return buf.getvalue(), zip_name


def monitor_export_sheet_name() -> str:
    return _MONITOR_EXPORT_FIXED_TITLE


def monitor_product_filename(product_name: str, as_of_label: str) -> str:
    """{信托产品}-资产监控表-{YYYYMMDD}.xlsx"""
    name = _safe_export_filename_part(product_name)
    return f"{name}-{_MONITOR_EXPORT_FIXED_TITLE}-{as_of_label}.xlsx"


def export_monitor_zip(
    conn: Connection,
    *,
    product_ids: list[int] | None = None,
    as_of: date | None = None,
    snapshot_id: int | None = None,
) -> tuple[bytes, str]:
    """按信托产品拆多份 xlsx（Sheet「资产监控表」），打包为 ZIP。"""
    if snapshot_id is not None:
        snap = get_snapshot(conn, snapshot_id)
        if not snap or snap.get("snapshot_type") != "monitor":
            raise HTTPException(status_code=404, detail="监控披露快照不存在")
        product_ids = [int(x) for x in (snap.get("product_ids") or [])]
        if not product_ids:
            raise HTTPException(status_code=400, detail="快照未包含信托产品")
        as_of_label = _as_of_label(snap.get("as_of_date"))
        zip_stamp = snap.get("frozen_at")
        rows = load_snapshot_monitor(conn, snapshot_id)
    else:
        product_ids = _require_products(product_ids)
        if as_of is None:
            raise HTTPException(status_code=400, detail="请提供统计日期")
        as_of_label = _as_of_label(as_of)
        zip_stamp = None
        rows = fetch_monitor_live(conn, product_ids, as_of)
        if len(rows) > EXPORT_MAX:
            raise HTTPException(
                status_code=400,
                detail=f"结果超过 {EXPORT_MAX} 条，请缩小范围",
            )

    name_by_id = _product_name_map(conn, product_ids)
    for row in rows:
        pid = row.get("trust_product_id")
        tpn = row.get("trust_product_name")
        if pid is not None and tpn and int(pid) not in name_by_id:
            name_by_id[int(pid)] = str(tpn)

    sheet_name = monitor_export_sheet_name()
    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for pid in product_ids:
            product_name = name_by_id.get(pid) or str(pid)
            p_rows = [r for r in rows if int(r.get("trust_product_id") or 0) == pid]
            xlsx = assetinfo_upload.build_monitor_export_xlsx(
                p_rows,
                columns=templates.DISCLOSURE_MONITOR_TEMPLATE_COLUMNS,
                sheet_name=sheet_name,
            )
            zf.writestr(monitor_product_filename(product_name, as_of_label), xlsx)
    zip_name = snapshot_export_zip_filename(_MONITOR_EXPORT_FIXED_TITLE, zip_stamp)
    return buf.getvalue(), zip_name
