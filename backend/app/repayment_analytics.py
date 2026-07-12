"""资产情况统计 — 还款周期汇总、发行基准、未还清存量（只读）."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import assetinfo_cleanse as cleanse
from app.overdue.buckets import M1_MAX_DAYS

PeriodKind = Literal["week", "month", "year"]

RECONCILIATION_TOLERANCE = cleanse.RECONCILIATION_TOLERANCE
STATS_OVERDUE_THRESHOLD_DAYS = M1_MAX_DAYS  # 未逾期: overdue_days <= 35; 逾期: > 35 (M2+)

PRIMARY_FROM_CUSTODY_SQL = """
    CASE
        WHEN LENGTH(TRIM({expr})) >= 12 THEN LEFT(TRIM({expr}), 12)
        ELSE TRIM({expr})
    END
"""

REPAYMENT_PRIMARY_SQL = f"""
    COALESCE(
        NULLIF(TRIM(ta.asset_code), ''),
        {PRIMARY_FROM_CUSTODY_SQL.format(expr="COALESCE(r.custody_asset_code, ta.custody_asset_code, r.asset_code)")},
        NULLIF(TRIM(r.asset_code), '')
    )
"""

ISSUANCE_PRIMARY_SQL = PRIMARY_FROM_CUSTODY_SQL.format(expr="i.custody_asset_code")

ISSUE_DATE_ALL = "all"
ISSUE_DATE_ALL_LABEL = "全部"


def _period_trunc_sql(period: PeriodKind) -> str:
    if period == "week":
        return "date_trunc('week', r.repayment_date::timestamp)::date"
    if period == "month":
        return "date_trunc('month', r.repayment_date::timestamp)::date"
    return "date_trunc('year', r.repayment_date::timestamp)::date"


def _period_label(period: PeriodKind, period_start: date) -> str:
    if period == "week":
        end = period_start + timedelta(days=6)
        iso = period_start.isocalendar()
        return f"{period_start.year}-W{iso.week:02d} ({period_start:%m-%d} ~ {end:%m-%d})"
    if period == "month":
        return f"{period_start.year}-{period_start.month:02d}"
    return str(period_start.year)


def _period_end(period: PeriodKind, period_start: date) -> date:
    if period == "week":
        return period_start + timedelta(days=6)
    if period == "month":
        if period_start.month == 12:
            return date(period_start.year, 12, 31)
        next_month = date(period_start.year, period_start.month + 1, 1)
        return next_month - timedelta(days=1)
    return date(period_start.year, 12, 31)


def _ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    num = float(numerator or 0)
    den = float(denominator or 0)
    if den <= 0:
        return None
    return round(num / den, 6)


def fetch_all_issue_summary(conn: Connection, trust_product_id: int) -> dict[str, Any]:
    row = conn.execute(
        text("""
            SELECT COUNT(DISTINCT custody_asset_code) AS issued_asset_count
            FROM trust_product_issuance_asset_records
            WHERE trust_product_id = :pid
        """),
        {"pid": trust_product_id},
    ).mappings().first()
    count = int(row["issued_asset_count"] or 0) if row else 0
    return {
        "issue_date": ISSUE_DATE_ALL,
        "issued_asset_count": count,
        "label": f"{ISSUE_DATE_ALL_LABEL}（{count} 个资产）",
    }


def fetch_issue_dates(conn: Connection, trust_product_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("""
            SELECT
                issue_date,
                COUNT(DISTINCT custody_asset_code) AS issued_asset_count
            FROM trust_product_issuance_asset_records
            WHERE trust_product_id = :pid
            GROUP BY issue_date
            ORDER BY issue_date DESC
        """),
        {"pid": trust_product_id},
    ).mappings()
    result: list[dict[str, Any]] = []
    for row in rows:
        issue = row["issue_date"]
        count = int(row["issued_asset_count"] or 0)
        issue_str = str(issue)
        result.append({
            "issue_date": issue_str,
            "issued_asset_count": count,
            "label": f"{issue_str}（{count} 个资产）",
        })
    return result


def resolve_issue_date(
    conn: Connection, trust_product_id: int, issue_date: str | None,
) -> str | None:
    dates = fetch_issue_dates(conn, trust_product_id)
    if not dates:
        return None
    if issue_date == ISSUE_DATE_ALL:
        return ISSUE_DATE_ALL
    if issue_date:
        for item in dates:
            if item["issue_date"] == issue_date:
                return issue_date
    return dates[0]["issue_date"]


def _issuance_issue_date_filter(
    issue_date: str, *, column: str = "i.issue_date",
) -> tuple[str, dict[str, Any]]:
    if issue_date == ISSUE_DATE_ALL:
        return "", {}
    return f" AND {column} = :issue_date", {"issue_date": issue_date}


def _has_batches_missing_min(
    conn: Connection, trust_product_id: int, issue_date: str,
) -> bool:
    issue_filter = ""
    params: dict[str, Any] = {"pid": trust_product_id}
    if issue_date != ISSUE_DATE_ALL:
        issue_filter = " AND issue_date = :issue_date"
        params["issue_date"] = issue_date
    row = conn.execute(
        text(f"""
            SELECT EXISTS (
                SELECT 1
                FROM trust_product_issuance_asset_records
                WHERE trust_product_id = :pid
                  {issue_filter}
                GROUP BY issue_date
                HAVING COUNT(*) > 0
                   AND COUNT(min_institution_transferable_amount)
                       FILTER (WHERE min_institution_transferable_amount IS NOT NULL) = 0
            ) AS missing
        """),
        params,
    ).mappings().first()
    return bool(row and row["missing"])


def _display_issue_date(issue_date: str) -> str:
    return ISSUE_DATE_ALL_LABEL if issue_date == ISSUE_DATE_ALL else issue_date


def _empty_issuance_stock() -> dict[str, Any]:
    return {
        "issued_asset_count": 0,
        "transferred_out_count": 0,
        "active_asset_count": 0,
        "effective_asset_count": 0,
        "min_transferable_total": 0.0,
        "receivable_transfer_total": 0.0,
        "active_min_transferable_total": 0.0,
        "active_receivable_transfer_total": 0.0,
        "transferred_min_transferable_total": 0.0,
        "transferred_receivable_transfer_total": 0.0,
        "pre_transfer_repaid_total": 0.0,
        "transferred_in_count": 0,
        "transferred_out_dest_count": 0,
        "paid_off_count": None,
        "unpaid_count": None,
        "no_monitor_count": 0,
        "monitor_snapshot_date": None,
    }


def _empty_monitor_summary() -> dict[str, Any]:
    empty_bucket = _empty_monitor_bucket()
    return {
        "monitor_snapshot_date": None,
        "monitor_asset_count": None,
        "paid_off_count": None,
        "unpaid_count": None,
        "overdue_count": None,
        "current_count": None,
        "initial_transfer_total": None,
        "repaid_total": None,
        "remaining_total": None,
        "by_bucket": {
            "paid_off": empty_bucket,
            "current": empty_bucket,
            "overdue": empty_bucket,
            "no_monitor": empty_bucket,
        },
    }


def _empty_monitor_bucket() -> dict[str, Any]:
    return {
        "asset_count": 0,
        "initial_transfer_total": 0.0,
        "repaid_total": 0.0,
        "remaining_total": 0.0,
    }


def _monitor_bucket_from_row(row: dict[str, Any], prefix: str) -> dict[str, Any]:
    return {
        "asset_count": int(row[f"{prefix}_asset_count"] or 0),
        "initial_transfer_total": float(row[f"{prefix}_initial"] or 0),
        "repaid_total": float(row[f"{prefix}_repaid"] or 0),
        "remaining_total": float(row[f"{prefix}_remaining"] or 0),
    }


def _split_stock_and_monitor(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    snapshot = row.get("monitor_snapshot_date")
    has_monitor = snapshot is not None
    active_count = int(row["active_asset_count"] or 0)
    stock = {
        "issued_asset_count": int(row["issued_asset_count"] or 0),
        "transferred_out_count": int(row["transferred_out_count"] or 0),
        "active_asset_count": active_count,
        "effective_asset_count": active_count,
        "min_transferable_total": float(row["min_transferable_total"] or 0),
        "receivable_transfer_total": float(row["receivable_transfer_total"] or 0),
        "active_min_transferable_total": float(row["active_min_transferable_total"] or 0),
        "active_receivable_transfer_total": float(row["active_receivable_transfer_total"] or 0),
        "transferred_min_transferable_total": float(
            row["transferred_min_transferable_total"] or 0
        ),
        "transferred_receivable_transfer_total": float(
            row["transferred_receivable_transfer_total"] or 0
        ),
        "pre_transfer_repaid_total": float(row["pre_transfer_repaid_total"] or 0),
        "transferred_in_count": int(row["transferred_in_count"] or 0),
        "transferred_out_dest_count": int(row["transferred_out_dest_count"] or 0),
        "paid_off_count": int(row["paid_off_count"] or 0) if has_monitor else None,
        "unpaid_count": int(row["unpaid_count"] or 0) if has_monitor else None,
        "no_monitor_count": int(row["no_monitor_count"] or 0),
        "monitor_snapshot_date": str(snapshot) if snapshot else None,
    }
    monitor_summary = {
        "monitor_snapshot_date": str(snapshot) if snapshot else None,
        "monitor_asset_count": int(row["monitor_asset_count"] or 0) if has_monitor else None,
        "paid_off_count": stock["paid_off_count"],
        "unpaid_count": stock["unpaid_count"],
        "overdue_count": int(row["overdue_asset_count"] or 0) if has_monitor else None,
        "current_count": int(row["current_asset_count"] or 0) if has_monitor else None,
        "initial_transfer_total": float(row["initial_transfer_total"] or 0) if has_monitor else None,
        "repaid_total": float(row["repaid_total"] or 0) if has_monitor else None,
        "remaining_total": float(row["remaining_total"] or 0) if has_monitor else None,
        "by_bucket": {
            "paid_off": _monitor_bucket_from_row(row, "paid_off"),
            "current": _monitor_bucket_from_row(row, "current"),
            "overdue": _monitor_bucket_from_row(row, "overdue"),
            "no_monitor": _monitor_bucket_from_row(row, "no_monitor"),
        },
    }
    return stock, monitor_summary


def fetch_issuance_stock(
    conn: Connection,
    trust_product_id: int,
    issue_date: str,
    *,
    city: str | None = None,
) -> dict[str, Any]:
    stock, _monitor = fetch_issuance_stock_with_monitor(
        conn, trust_product_id, issue_date, city=city,
    )
    return stock


def fetch_monitor_summary(
    conn: Connection,
    trust_product_id: int,
    issue_date: str,
    *,
    city: str | None = None,
) -> dict[str, Any]:
    issue_date_filter, issue_params = _issuance_issue_date_filter(issue_date)
    city_filter = ""
    params: dict[str, Any] = {
        "pid": trust_product_id,
        "tolerance": RECONCILIATION_TOLERANCE,
        **issue_params,
    }
    if city:
        city_filter = " AND COALESCE(i.city, '未知') = :city"
        params["city"] = city

    row = conn.execute(
        text(f"""
            WITH scoped_rows AS (
                SELECT DISTINCT
                    i.custody_asset_code,
                    i.issue_date,
                    {PRIMARY_FROM_CUSTODY_SQL.format(expr="i.custody_asset_code")} AS primary_asset_code
                FROM trust_product_issuance_asset_records i
                WHERE i.trust_product_id = :pid
                  {issue_date_filter}
                  {city_filter}
            ),
            transferred AS (
                SELECT DISTINCT s.custody_asset_code
                FROM scoped_rows s
                WHERE EXISTS (
                    SELECT 1
                    FROM trust_product_issuance_asset_records dst
                    WHERE dst.custody_asset_code = s.custody_asset_code
                      AND dst.trust_product_id <> :pid
                      AND dst.from_trust_product_id = :pid
                      AND dst.issue_date > s.issue_date
                )
            ),
            active_pool AS (
                SELECT DISTINCT s.custody_asset_code, s.primary_asset_code
                FROM scoped_rows s
                WHERE NOT EXISTS (
                    SELECT 1 FROM transferred t WHERE t.custody_asset_code = s.custody_asset_code
                )
            ),
            monitor_latest AS (
                SELECT MAX(data_date) AS data_date
                FROM trust_asset_monitor_records
                WHERE trust_product_id = :pid
            ),
            monitor_by_primary AS (
                SELECT
                    m.asset_code,
                    SUM(m.initial_transfer_amount) AS initial_transfer_amount,
                    SUM(m.repaid_amount) AS repaid_amount,
                    SUM(m.remaining_amount) AS remaining_amount
                FROM trust_asset_monitor_records m
                INNER JOIN monitor_latest ml ON m.data_date = ml.data_date
                WHERE m.trust_product_id = :pid
                GROUP BY m.asset_code
            ),
            active_primaries AS (
                SELECT DISTINCT primary_asset_code FROM active_pool
            ),
            classified AS (
                SELECT a.custody_asset_code, m.remaining_amount
                FROM active_pool a
                LEFT JOIN monitor_by_primary m ON m.asset_code = a.primary_asset_code
            ),
            monitor_totals AS (
                SELECT
                    COUNT(*) FILTER (WHERE m.asset_code IS NOT NULL) AS monitor_asset_count,
                    COALESCE(SUM(m.initial_transfer_amount), 0) AS initial_transfer_total,
                    COALESCE(SUM(m.repaid_amount), 0) AS repaid_total,
                    COALESCE(SUM(m.remaining_amount), 0) AS remaining_total
                FROM active_primaries ap
                LEFT JOIN monitor_by_primary m ON m.asset_code = ap.primary_asset_code
            )
            SELECT
                ml.data_date AS monitor_snapshot_date,
                monitor_totals.monitor_asset_count,
                monitor_totals.initial_transfer_total,
                monitor_totals.repaid_total,
                monitor_totals.remaining_total,
                (SELECT COUNT(*) FROM classified
                 WHERE remaining_amount IS NOT NULL AND remaining_amount <= :tolerance) AS paid_off_count,
                (SELECT COUNT(*) FROM classified
                 WHERE remaining_amount IS NULL OR remaining_amount > :tolerance) AS unpaid_count
            FROM monitor_latest ml
            CROSS JOIN monitor_totals
        """),
        params,
    ).mappings().first()

    if row is None or row["monitor_snapshot_date"] is None:
        return _empty_monitor_summary()

    snapshot = str(row["monitor_snapshot_date"])
    return {
        "monitor_snapshot_date": snapshot,
        "monitor_asset_count": int(row["monitor_asset_count"] or 0),
        "paid_off_count": int(row["paid_off_count"] or 0),
        "unpaid_count": int(row["unpaid_count"] or 0),
        "initial_transfer_total": float(row["initial_transfer_total"] or 0),
        "repaid_total": float(row["repaid_total"] or 0),
        "remaining_total": float(row["remaining_total"] or 0),
    }


def fetch_issuance_stock_with_monitor(
    conn: Connection,
    trust_product_id: int,
    issue_date: str,
    *,
    city: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """一次查询返回发行基准与监控汇总（内部复用同一 CTE 逻辑）。"""
    issue_date_filter, issue_params = _issuance_issue_date_filter(issue_date)
    city_filter = ""
    params: dict[str, Any] = {
        "pid": trust_product_id,
        "tolerance": RECONCILIATION_TOLERANCE,
        "overdue_threshold": STATS_OVERDUE_THRESHOLD_DAYS,
        **issue_params,
    }
    if city:
        city_filter = " AND COALESCE(i.city, '未知') = :city"
        params["city"] = city

    row = conn.execute(
        text(f"""
            WITH scoped_rows AS (
                SELECT DISTINCT
                    i.custody_asset_code,
                    i.issue_date,
                    {PRIMARY_FROM_CUSTODY_SQL.format(expr="i.custody_asset_code")} AS primary_asset_code
                FROM trust_product_issuance_asset_records i
                WHERE i.trust_product_id = :pid
                  {issue_date_filter}
                  {city_filter}
            ),
            transferred AS (
                SELECT DISTINCT
                    s.custody_asset_code,
                    s.primary_asset_code,
                    (
                        SELECT MIN(dst.issue_date)
                        FROM trust_product_issuance_asset_records dst
                        WHERE dst.custody_asset_code = s.custody_asset_code
                          AND dst.trust_product_id <> :pid
                          AND dst.from_trust_product_id = :pid
                          AND dst.issue_date > s.issue_date
                    ) AS transfer_issue_date
                FROM scoped_rows s
                WHERE EXISTS (
                    SELECT 1
                    FROM trust_product_issuance_asset_records dst
                    WHERE dst.custody_asset_code = s.custody_asset_code
                      AND dst.trust_product_id <> :pid
                      AND dst.from_trust_product_id = :pid
                      AND dst.issue_date > s.issue_date
                )
            ),
            active_pool AS (
                SELECT DISTINCT s.custody_asset_code, s.primary_asset_code
                FROM scoped_rows s
                WHERE NOT EXISTS (
                    SELECT 1 FROM transferred t WHERE t.custody_asset_code = s.custody_asset_code
                )
            ),
            amounts AS (
                SELECT
                    COALESCE(SUM(i.min_institution_transferable_amount), 0) AS min_transferable_total,
                    COALESCE(SUM(i.receivable_transfer_amount), 0) AS receivable_transfer_total
                FROM trust_product_issuance_asset_records i
                WHERE i.trust_product_id = :pid
                  {issue_date_filter}
                  {city_filter}
            ),
            active_amounts AS (
                SELECT
                    COALESCE(SUM(i.min_institution_transferable_amount), 0) AS active_min_transferable_total,
                    COALESCE(SUM(i.receivable_transfer_amount), 0) AS active_receivable_transfer_total
                FROM trust_product_issuance_asset_records i
                INNER JOIN active_pool ap ON ap.custody_asset_code = i.custody_asset_code
                WHERE i.trust_product_id = :pid
                  {issue_date_filter}
                  {city_filter}
            ),
            transferred_amounts AS (
                SELECT
                    COALESCE(SUM(dst.min_institution_transferable_amount), 0)
                        AS transferred_min_transferable_total,
                    COALESCE(SUM(dst.receivable_transfer_amount), 0)
                        AS transferred_receivable_transfer_total
                FROM trust_product_issuance_asset_records dst
                INNER JOIN transferred t ON t.custody_asset_code = dst.custody_asset_code
                WHERE dst.from_trust_product_id = :pid
                  AND dst.trust_product_id <> :pid
            ),
            pre_transfer_repaid AS (
                SELECT COALESCE(SUM(r.actual_repayment_amount), 0) AS pre_transfer_repaid_total
                FROM trust_repayment_detail_records r
                LEFT JOIN trust_assets ta ON ta.id = r.trust_asset_id
                INNER JOIN transferred t
                    ON t.primary_asset_code = {REPAYMENT_PRIMARY_SQL}
                WHERE r.trust_product_id = :pid
                  AND r.repayment_date IS NOT NULL
                  AND r.repayment_date < t.transfer_issue_date
            ),
            transferred_in_counts AS (
                SELECT COUNT(DISTINCT i.custody_asset_code) AS transferred_in_count
                FROM trust_product_issuance_asset_records i
                WHERE i.trust_product_id = :pid
                  AND i.from_trust_product_id IS NOT NULL
                  AND i.from_trust_product_id <> :pid
                  {issue_date_filter}
                  {city_filter}
            ),
            transferred_out_dest AS (
                SELECT COUNT(DISTINCT dst.custody_asset_code) AS transferred_out_dest_count
                FROM trust_product_issuance_asset_records dst
                INNER JOIN transferred t ON t.custody_asset_code = dst.custody_asset_code
                WHERE dst.from_trust_product_id = :pid
                  AND dst.trust_product_id <> :pid
            ),
            monitor_latest AS (
                SELECT MAX(data_date) AS data_date
                FROM trust_asset_monitor_records
                WHERE trust_product_id = :pid
            ),
            monitor_by_primary AS (
                SELECT
                    m.asset_code,
                    SUM(m.initial_transfer_amount) AS initial_transfer_amount,
                    SUM(m.repaid_amount) AS repaid_amount,
                    SUM(m.remaining_amount) AS remaining_amount,
                    MAX(m.overdue_days) AS overdue_days
                FROM trust_asset_monitor_records m
                INNER JOIN monitor_latest ml ON m.data_date = ml.data_date
                WHERE m.trust_product_id = :pid
                GROUP BY m.asset_code
            ),
            active_primaries AS (
                SELECT DISTINCT primary_asset_code FROM active_pool
            ),
            active_monitor AS (
                SELECT
                    ap.primary_asset_code,
                    m.asset_code,
                    COALESCE(m.initial_transfer_amount, 0) AS initial_transfer_amount,
                    COALESCE(m.repaid_amount, 0) AS repaid_amount,
                    m.remaining_amount,
                    m.overdue_days
                FROM active_primaries ap
                LEFT JOIN monitor_by_primary m ON m.asset_code = ap.primary_asset_code
            ),
            asset_bucket AS (
                SELECT
                    primary_asset_code,
                    initial_transfer_amount,
                    repaid_amount,
                    remaining_amount,
                    CASE
                        WHEN asset_code IS NULL OR remaining_amount IS NULL THEN 'no_monitor'
                        WHEN remaining_amount <= :tolerance THEN 'paid_off'
                        WHEN overdue_days > :overdue_threshold THEN 'overdue'
                        ELSE 'current'
                    END AS bucket
                FROM active_monitor
            ),
            monitor_totals AS (
                SELECT
                    COUNT(*) FILTER (WHERE bucket <> 'no_monitor') AS monitor_asset_count,
                    COALESCE(SUM(initial_transfer_amount), 0) AS initial_transfer_total,
                    COALESCE(SUM(repaid_amount), 0) AS repaid_total,
                    COALESCE(SUM(remaining_amount), 0) AS remaining_total,
                    COUNT(*) FILTER (WHERE bucket = 'paid_off') AS paid_off_count,
                    COUNT(*) FILTER (WHERE bucket IN ('current', 'overdue', 'no_monitor')) AS unpaid_count,
                    COUNT(*) FILTER (WHERE bucket = 'overdue') AS overdue_asset_count,
                    COUNT(*) FILTER (WHERE bucket = 'current') AS current_asset_count,
                    COUNT(*) FILTER (WHERE bucket = 'no_monitor') AS no_monitor_count,
                    COUNT(*) FILTER (WHERE bucket = 'paid_off') AS paid_off_asset_count,
                    COALESCE(SUM(initial_transfer_amount) FILTER (WHERE bucket = 'paid_off'), 0) AS paid_off_initial,
                    COALESCE(SUM(repaid_amount) FILTER (WHERE bucket = 'paid_off'), 0) AS paid_off_repaid,
                    COALESCE(SUM(remaining_amount) FILTER (WHERE bucket = 'paid_off'), 0) AS paid_off_remaining,
                    COUNT(*) FILTER (WHERE bucket = 'current') AS current_asset_count_dup,
                    COALESCE(SUM(initial_transfer_amount) FILTER (WHERE bucket = 'current'), 0) AS current_initial,
                    COALESCE(SUM(repaid_amount) FILTER (WHERE bucket = 'current'), 0) AS current_repaid,
                    COALESCE(SUM(remaining_amount) FILTER (WHERE bucket = 'current'), 0) AS current_remaining,
                    COUNT(*) FILTER (WHERE bucket = 'overdue') AS overdue_asset_count_dup,
                    COALESCE(SUM(initial_transfer_amount) FILTER (WHERE bucket = 'overdue'), 0) AS overdue_initial,
                    COALESCE(SUM(repaid_amount) FILTER (WHERE bucket = 'overdue'), 0) AS overdue_repaid,
                    COALESCE(SUM(remaining_amount) FILTER (WHERE bucket = 'overdue'), 0) AS overdue_remaining,
                    COUNT(*) FILTER (WHERE bucket = 'no_monitor') AS no_monitor_asset_count,
                    COALESCE(SUM(initial_transfer_amount) FILTER (WHERE bucket = 'no_monitor'), 0) AS no_monitor_initial,
                    COALESCE(SUM(repaid_amount) FILTER (WHERE bucket = 'no_monitor'), 0) AS no_monitor_repaid,
                    COALESCE(SUM(remaining_amount) FILTER (WHERE bucket = 'no_monitor'), 0) AS no_monitor_remaining
                FROM asset_bucket
            )
            SELECT
                (SELECT COUNT(DISTINCT custody_asset_code) FROM scoped_rows) AS issued_asset_count,
                (SELECT COUNT(*) FROM transferred) AS transferred_out_count,
                (SELECT COUNT(*) FROM active_pool) AS active_asset_count,
                amounts.min_transferable_total,
                amounts.receivable_transfer_total,
                active_amounts.active_min_transferable_total,
                active_amounts.active_receivable_transfer_total,
                transferred_amounts.transferred_min_transferable_total,
                transferred_amounts.transferred_receivable_transfer_total,
                pre_transfer_repaid.pre_transfer_repaid_total,
                transferred_in_counts.transferred_in_count,
                transferred_out_dest.transferred_out_dest_count,
                ml.data_date AS monitor_snapshot_date,
                monitor_totals.monitor_asset_count,
                monitor_totals.initial_transfer_total,
                monitor_totals.repaid_total,
                monitor_totals.remaining_total,
                monitor_totals.paid_off_count,
                monitor_totals.unpaid_count,
                monitor_totals.overdue_asset_count,
                monitor_totals.current_asset_count,
                monitor_totals.no_monitor_count,
                monitor_totals.paid_off_asset_count,
                monitor_totals.paid_off_initial,
                monitor_totals.paid_off_repaid,
                monitor_totals.paid_off_remaining,
                monitor_totals.current_initial,
                monitor_totals.current_repaid,
                monitor_totals.current_remaining,
                monitor_totals.overdue_initial,
                monitor_totals.overdue_repaid,
                monitor_totals.overdue_remaining,
                monitor_totals.no_monitor_asset_count,
                monitor_totals.no_monitor_initial,
                monitor_totals.no_monitor_repaid,
                monitor_totals.no_monitor_remaining
            FROM amounts
            CROSS JOIN active_amounts
            CROSS JOIN transferred_amounts
            CROSS JOIN pre_transfer_repaid
            CROSS JOIN transferred_in_counts
            CROSS JOIN transferred_out_dest
            CROSS JOIN monitor_latest ml
            CROSS JOIN monitor_totals
        """),
        params,
    ).mappings().first()

    if row is None:
        return _empty_issuance_stock(), _empty_monitor_summary()

    return _split_stock_and_monitor(dict(row))


def fetch_monitor_stock(
    conn: Connection,
    trust_product_id: int,
    issue_date: str,
    *,
    city: str | None = None,
) -> dict[str, Any]:
    """兼容旧调用：返回监控存量字段子集。"""
    _stock, monitor = fetch_issuance_stock_with_monitor(
        conn, trust_product_id, issue_date, city=city,
    )
    return {
        "monitor_snapshot_date": monitor["monitor_snapshot_date"],
        "paid_off_count": monitor["paid_off_count"],
        "unpaid_asset_count": monitor["unpaid_count"],
    }


def fetch_cumulative_repayments(
    conn: Connection,
    trust_product_id: int,
    issue_date: str,
    period: PeriodKind,
    period_starts: list[date],
    *,
    city: str | None = None,
) -> dict[str, float]:
    if not period_starts:
        return {}

    period_ends = [_period_end(period, ps) for ps in period_starts]
    issue_date_filter, issue_params = _issuance_issue_date_filter(issue_date)
    issuance_city_filter = ""
    repayment_city_filter = ""
    params: dict[str, Any] = {"pid": trust_product_id, **issue_params}
    if city:
        issuance_city_filter = " AND COALESCE(i.city, '未知') = :city"
        repayment_city_filter = " AND COALESCE(ic.city, '未知') = :city"
        params["city"] = city

    end_params = {f"pe_{i}": pe for i, pe in enumerate(period_ends)}
    start_params = {f"ps_{i}": ps for i, ps in enumerate(period_starts)}
    params.update(end_params)
    params.update(start_params)

    values_sql = ", ".join(
        f"(:ps_{i}, :pe_{i})" for i in range(len(period_starts))
    )

    rows = conn.execute(
        text(f"""
            WITH scoped_rows AS (
                SELECT DISTINCT
                    i.custody_asset_code,
                    i.issue_date,
                    {PRIMARY_FROM_CUSTODY_SQL.format(expr="i.custody_asset_code")} AS primary_asset_code
                FROM trust_product_issuance_asset_records i
                WHERE i.trust_product_id = :pid
                  {issue_date_filter}
                  {issuance_city_filter}
            ),
            transferred AS (
                SELECT DISTINCT s.custody_asset_code
                FROM scoped_rows s
                WHERE EXISTS (
                    SELECT 1
                    FROM trust_product_issuance_asset_records dst
                    WHERE dst.custody_asset_code = s.custody_asset_code
                      AND dst.trust_product_id <> :pid
                      AND dst.from_trust_product_id = :pid
                      AND dst.issue_date > s.issue_date
                )
            ),
            active_primaries AS (
                SELECT DISTINCT s.primary_asset_code
                FROM scoped_rows s
                WHERE NOT EXISTS (
                    SELECT 1 FROM transferred t WHERE t.custody_asset_code = s.custody_asset_code
                )
            ),
            periods(period_start, period_end) AS (
                VALUES {values_sql}
            ),
            repayment_tagged AS (
                SELECT
                    r.repayment_date,
                    r.actual_repayment_amount,
                    {REPAYMENT_PRIMARY_SQL} AS primary_asset_code
                FROM trust_repayment_detail_records r
                LEFT JOIN trust_assets ta ON ta.id = r.trust_asset_id
                LEFT JOIN LATERAL (
                    SELECT COALESCE(iss.city, '未知') AS city
                    FROM trust_product_issuance_asset_records iss
                    WHERE iss.trust_product_id = r.trust_product_id
                      AND iss.custody_asset_code = COALESCE(r.custody_asset_code, ta.custody_asset_code, r.asset_code)
                    ORDER BY iss.issue_date DESC
                    LIMIT 1
                ) ic ON TRUE
                WHERE r.trust_product_id = :pid
                  AND r.repayment_date IS NOT NULL
                  {repayment_city_filter}
            )
            SELECT
                p.period_start,
                COALESCE(SUM(rt.actual_repayment_amount), 0) AS cumulative_repayment
            FROM periods p
            LEFT JOIN repayment_tagged rt
                ON rt.repayment_date <= p.period_end
               AND rt.primary_asset_code IN (SELECT primary_asset_code FROM active_primaries)
            GROUP BY p.period_start
            ORDER BY p.period_start
        """),
        params,
    ).mappings().all()

    result: dict[str, float] = {}
    for row in rows:
        ps = row["period_start"]
        if ps is None:
            continue
        period_start = ps if isinstance(ps, date) else date.fromisoformat(str(ps)[:10])
        result[str(period_start)] = float(row["cumulative_repayment"] or 0)
    return result


def fetch_repayment_period_rows(
    conn: Connection,
    trust_product_id: int,
    period: PeriodKind,
    date_from: date,
    date_to: date,
    *,
    city: str | None = None,
) -> list[dict[str, Any]]:
    trunc = _period_trunc_sql(period)
    city_filter = ""
    params: dict[str, Any] = {
        "pid": trust_product_id,
        "date_from": date_from,
        "date_to": date_to,
    }
    if city:
        city_filter = " AND COALESCE(ic.city, '未知') = :city"
        params["city"] = city

    rows = conn.execute(
        text(f"""
            WITH repayment_tagged AS (
                SELECT
                    {trunc} AS period_start,
                    {REPAYMENT_PRIMARY_SQL} AS primary_asset_code,
                    r.actual_repayment_amount
                FROM trust_repayment_detail_records r
                LEFT JOIN trust_assets ta ON ta.id = r.trust_asset_id
                LEFT JOIN LATERAL (
                    SELECT COALESCE(iss.city, '未知') AS city
                    FROM trust_product_issuance_asset_records iss
                    WHERE iss.trust_product_id = r.trust_product_id
                      AND iss.custody_asset_code = COALESCE(r.custody_asset_code, ta.custody_asset_code, r.asset_code)
                    ORDER BY iss.issue_date DESC
                    LIMIT 1
                ) ic ON TRUE
                WHERE r.trust_product_id = :pid
                  AND r.repayment_date IS NOT NULL
                  AND r.repayment_date >= :date_from
                  AND r.repayment_date <= :date_to
                  {city_filter}
            )
            SELECT
                period_start,
                COUNT(DISTINCT primary_asset_code) AS repaid_asset_count,
                COALESCE(SUM(actual_repayment_amount), 0) AS repayment_amount
            FROM repayment_tagged
            WHERE primary_asset_code IS NOT NULL
            GROUP BY period_start
            ORDER BY period_start
        """),
        params,
    ).mappings().all()

    result: list[dict[str, Any]] = []
    for row in rows:
        ps = row["period_start"]
        if ps is None:
            continue
        period_start = ps if isinstance(ps, date) else date.fromisoformat(str(ps)[:10])
        result.append({
            "period_key": str(period_start),
            "period_label": _period_label(period, period_start),
            "repaid_asset_count": int(row["repaid_asset_count"] or 0),
            "repayment_amount": float(row["repayment_amount"] or 0),
        })
    return result


def fetch_issuance_cities(
    conn: Connection, trust_product_id: int, issue_date: str,
) -> list[str]:
    issue_date_filter, issue_params = _issuance_issue_date_filter(
        issue_date, column="issue_date",
    )
    rows = conn.execute(
        text(f"""
            SELECT DISTINCT COALESCE(city, '未知') AS city
            FROM trust_product_issuance_asset_records
            WHERE trust_product_id = :pid
              {issue_date_filter}
            ORDER BY city
        """),
        {"pid": trust_product_id, **issue_params},
    ).mappings()
    return [str(r["city"]) for r in rows]


def fetch_city_breakdown(
    conn: Connection,
    trust_product_id: int,
    issue_date: str,
    period: PeriodKind,
    date_from: date,
    date_to: date,
) -> list[dict[str, Any]]:
    cities = fetch_issuance_cities(conn, trust_product_id, issue_date)
    breakdown: list[dict[str, Any]] = []
    for city in cities:
        stock, monitor = fetch_issuance_stock_with_monitor(
            conn, trust_product_id, issue_date, city=city,
        )
        periods = fetch_repayment_period_rows(
            conn, trust_product_id, period, date_from, date_to, city=city,
        )
        periods = _attach_ratios(
            conn, trust_product_id, issue_date, period, periods, stock, monitor,
            city=city,
        )
        breakdown.append({
            "city": city,
            "issuance_baseline": stock,
            "monitor_summary": monitor,
            "monitor_stock": {
                "monitor_snapshot_date": monitor["monitor_snapshot_date"],
                "paid_off_count": monitor["paid_off_count"],
                "unpaid_asset_count": monitor["unpaid_count"],
            },
            "periods": periods,
        })
    return breakdown


def _attach_ratios(
    conn: Connection,
    trust_product_id: int,
    issue_date: str,
    period: PeriodKind,
    periods: list[dict[str, Any]],
    stock: dict[str, Any],
    monitor: dict[str, Any],
    *,
    city: str | None = None,
) -> list[dict[str, Any]]:
    asset_den = stock.get("active_asset_count") or 0
    min_den = stock.get("active_min_transferable_total") or 0
    unpaid = stock.get("unpaid_count")
    paid_off = stock.get("paid_off_count")
    snapshot = monitor.get("monitor_snapshot_date")
    initial_total = monitor.get("initial_transfer_total") or 0

    period_starts = [date.fromisoformat(row["period_key"]) for row in periods]
    cumulative_map = fetch_cumulative_repayments(
        conn, trust_product_id, issue_date, period, period_starts, city=city,
    )

    enriched: list[dict[str, Any]] = []
    for row in periods:
        cumulative = cumulative_map.get(row["period_key"], 0.0)
        remaining = (
            float(initial_total) - cumulative
            if initial_total else None
        )
        enriched.append({
            **row,
            "paid_off_count": paid_off,
            "unpaid_asset_count": unpaid,
            "monitor_snapshot_date": snapshot,
            "cumulative_repayment": cumulative,
            "remaining_repayment": remaining,
            "repaid_asset_ratio": _ratio(row["repaid_asset_count"], asset_den),
            "repayment_amount_ratio": _ratio(row["repayment_amount"], min_den),
            "cumulative_repayment_ratio": _ratio(cumulative, initial_total),
        })
    return enriched


def build_asset_stats_report(
    conn: Connection,
    *,
    trust_product_id: int,
    issue_date: str | None,
    period: PeriodKind,
    date_from: date,
    date_to: date,
    city: str | None = None,
    include_city_breakdown: bool = True,
) -> dict[str, Any]:
    product_row = conn.execute(
        text("SELECT id, name FROM trust_products WHERE id = :id"),
        {"id": trust_product_id},
    ).mappings().first()
    if not product_row:
        raise ValueError("trust_product_id not found")

    resolved_issue = resolve_issue_date(conn, trust_product_id, issue_date)
    issue_dates = fetch_issue_dates(conn, trust_product_id)

    if not resolved_issue:
        empty = _empty_issuance_stock()
        empty_monitor = _empty_monitor_summary()
        return {
            "trust_product_id": trust_product_id,
            "trust_product_name": product_row["name"],
            "issue_dates": issue_dates,
            "issuance_baseline": None,
            "monitor_summary": empty_monitor,
            "monitor_stock": {
                "monitor_snapshot_date": empty_monitor["monitor_snapshot_date"],
                "paid_off_count": empty_monitor["paid_off_count"],
                "unpaid_asset_count": empty_monitor["unpaid_count"],
            },
            "periods": [],
            "by_city": [],
            "warnings": ["该产品暂无发行数据，无法计算发行基准与占比。"],
        }

    stock, monitor = fetch_issuance_stock_with_monitor(
        conn, trust_product_id, resolved_issue, city=city,
    )
    periods = fetch_repayment_period_rows(
        conn, trust_product_id, period, date_from, date_to, city=city,
    )
    periods = _attach_ratios(
        conn, trust_product_id, resolved_issue, period, periods, stock, monitor,
        city=city,
    )

    by_city: list[dict[str, Any]] = []
    if include_city_breakdown and not city:
        by_city = fetch_city_breakdown(
            conn, trust_product_id, resolved_issue, period, date_from, date_to,
        )

    warnings: list[str] = []
    if stock["issued_asset_count"] == 0:
        if resolved_issue == ISSUE_DATE_ALL:
            warnings.append("该产品全部发行批次无有效发行资产。")
        else:
            warnings.append("所选发行日无有效发行资产。")
    if _has_batches_missing_min(conn, trust_product_id, resolved_issue):
        warnings.append("部分发行批次 MIN 可转让金额未录入，合计可能偏低。")
    elif stock["active_min_transferable_total"] <= 0:
        warnings.append("在管池 MIN 可转让金额合计为 0，还款金额占比无法计算。")
    if stock["receivable_transfer_total"] <= 0:
        warnings.append("应收账款转让价款合计为 0。")
    if monitor["monitor_snapshot_date"] is None:
        warnings.append("该产品暂无监控快照，已还清/未还清资产数无法计算。")
    elif stock["no_monitor_count"] > 0:
        warnings.append(
            f"{stock['no_monitor_count']} 笔在管资产暂无监控快照，已计入未还清。"
        )

    display_issue = _display_issue_date(resolved_issue)
    monitor_stock = {
        "monitor_snapshot_date": monitor["monitor_snapshot_date"],
        "paid_off_count": monitor["paid_off_count"],
        "unpaid_asset_count": monitor["unpaid_count"],
    }
    return {
        "trust_product_id": trust_product_id,
        "trust_product_name": product_row["name"],
        "issue_date": display_issue,
        "issue_date_param": resolved_issue,
        "issue_dates": issue_dates,
        "all_issue_summary": fetch_all_issue_summary(conn, trust_product_id),
        "issuance_baseline": {
            "issue_date": display_issue,
            **stock,
        },
        "monitor_summary": monitor,
        "monitor_stock": monitor_stock,
        "period": period,
        "date_from": str(date_from),
        "date_to": str(date_to),
        "city_filter": city,
        "periods": periods,
        "by_city": by_city,
        "warnings": warnings,
    }
