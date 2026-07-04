"""资产情况统计 — 还款周期汇总、发行基准、未还清存量（只读）."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import assetinfo_cleanse as cleanse

PeriodKind = Literal["week", "month", "year"]

RECONCILIATION_TOLERANCE = cleanse.RECONCILIATION_TOLERANCE

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


def _ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    num = float(numerator or 0)
    den = float(denominator or 0)
    if den <= 0:
        return None
    return round(num / den, 6)


def fetch_issue_dates(conn: Connection, trust_product_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(f"""
            SELECT
                i.issue_date,
                COUNT(DISTINCT {ISSUANCE_PRIMARY_SQL}) AS asset_primary_count
            FROM trust_product_issuance_asset_records i
            WHERE i.trust_product_id = :pid
            GROUP BY i.issue_date
            ORDER BY i.issue_date DESC
        """),
        {"pid": trust_product_id},
    ).mappings()
    result: list[dict[str, Any]] = []
    for row in rows:
        issue = row["issue_date"]
        count = int(row["asset_primary_count"] or 0)
        issue_str = str(issue)
        result.append({
            "issue_date": issue_str,
            "asset_primary_count": count,
            "label": f"{issue_str}（{count} 个资产）",
        })
    return result


def resolve_issue_date(
    conn: Connection, trust_product_id: int, issue_date: str | None,
) -> str | None:
    dates = fetch_issue_dates(conn, trust_product_id)
    if not dates:
        return None
    if issue_date:
        for item in dates:
            if item["issue_date"] == issue_date:
                return issue_date
    return dates[0]["issue_date"]


def fetch_issuance_baseline(
    conn: Connection,
    trust_product_id: int,
    issue_date: str,
    *,
    city: str | None = None,
) -> dict[str, Any]:
    city_filter = ""
    params: dict[str, Any] = {"pid": trust_product_id, "issue_date": issue_date}
    if city:
        city_filter = " AND COALESCE(i.city, '未知') = :city"
        params["city"] = city

    row = conn.execute(
        text(f"""
            SELECT
                COUNT(DISTINCT {ISSUANCE_PRIMARY_SQL}) AS asset_primary_count,
                COALESCE(SUM(i.min_institution_transferable_amount), 0) AS min_transferable_total,
                COALESCE(SUM(i.receivable_transfer_amount), 0) AS receivable_transfer_total
            FROM trust_product_issuance_asset_records i
            WHERE i.trust_product_id = :pid
              AND i.issue_date = :issue_date
              {city_filter}
        """),
        params,
    ).mappings().first()

    if row is None:
        return {
            "asset_primary_count": 0,
            "min_transferable_total": 0.0,
            "receivable_transfer_total": 0.0,
        }
    return {
        "asset_primary_count": int(row["asset_primary_count"] or 0),
        "min_transferable_total": float(row["min_transferable_total"] or 0),
        "receivable_transfer_total": float(row["receivable_transfer_total"] or 0),
    }


def fetch_monitor_stock(
    conn: Connection,
    trust_product_id: int,
    *,
    city: str | None = None,
) -> dict[str, Any]:
    """未还清主编号数：该产品各自最新监控日。"""
    latest_row = conn.execute(
        text("""
            SELECT MAX(data_date) AS data_date
            FROM trust_asset_monitor_records
            WHERE trust_product_id = :pid
        """),
        {"pid": trust_product_id},
    ).mappings().first()

    if not latest_row or latest_row["data_date"] is None:
        return {
            "monitor_snapshot_date": None,
            "unpaid_asset_count": None,
        }

    snapshot_date = str(latest_row["data_date"])
    city_join = ""
    city_filter = ""
    params: dict[str, Any] = {
        "pid": trust_product_id,
        "data_date": latest_row["data_date"],
        "tolerance": RECONCILIATION_TOLERANCE,
    }
    if city:
        city_join = """
            LEFT JOIN LATERAL (
                SELECT COALESCE(iss.city, '未知') AS city
                FROM trust_product_issuance_asset_records iss
                WHERE iss.trust_product_id = m.trust_product_id
                  AND iss.custody_asset_code = COALESCE(m.custody_asset_code, ta.custody_asset_code, m.asset_code)
                ORDER BY iss.issue_date DESC
                LIMIT 1
            ) ic ON TRUE
        """
        city_filter = " AND COALESCE(ic.city, '未知') = :city"
        params["city"] = city

    unpaid_row = conn.execute(
        text(f"""
            WITH by_custody AS (
                SELECT
                    m.asset_code,
                    COALESCE(m.custody_asset_code, ta.custody_asset_code, m.asset_code) AS custody_asset_code,
                    SUM(m.remaining_amount) AS remaining_amount
                FROM trust_asset_monitor_records m
                INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
                {city_join}
                WHERE m.trust_product_id = :pid
                  AND m.data_date = :data_date
                  {city_filter}
                GROUP BY m.asset_code, COALESCE(m.custody_asset_code, ta.custody_asset_code, m.asset_code)
            ),
            by_primary AS (
                SELECT asset_code, SUM(remaining_amount) AS remaining_amount
                FROM by_custody
                GROUP BY asset_code
            )
            SELECT COUNT(*) AS unpaid_asset_count
            FROM by_primary
            WHERE remaining_amount > :tolerance
        """),
        params,
    ).mappings().first()

    unpaid = int(unpaid_row["unpaid_asset_count"] or 0) if unpaid_row else 0
    return {
        "monitor_snapshot_date": snapshot_date,
        "unpaid_asset_count": unpaid,
    }


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
    rows = conn.execute(
        text("""
            SELECT DISTINCT COALESCE(city, '未知') AS city
            FROM trust_product_issuance_asset_records
            WHERE trust_product_id = :pid AND issue_date = :issue_date
            ORDER BY city
        """),
        {"pid": trust_product_id, "issue_date": issue_date},
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
        baseline = fetch_issuance_baseline(
            conn, trust_product_id, issue_date, city=city,
        )
        stock = fetch_monitor_stock(conn, trust_product_id, city=city)
        periods = fetch_repayment_period_rows(
            conn, trust_product_id, period, date_from, date_to, city=city,
        )
        breakdown.append({
            "city": city,
            "issuance_baseline": baseline,
            "monitor_stock": stock,
            "periods": _attach_ratios(periods, baseline, stock),
        })
    return breakdown


def _attach_ratios(
    periods: list[dict[str, Any]],
    baseline: dict[str, Any],
    stock: dict[str, Any],
) -> list[dict[str, Any]]:
    asset_den = baseline.get("asset_primary_count") or 0
    min_den = baseline.get("min_transferable_total") or 0
    unpaid = stock.get("unpaid_asset_count")
    snapshot = stock.get("monitor_snapshot_date")
    enriched: list[dict[str, Any]] = []
    for row in periods:
        enriched.append({
            **row,
            "unpaid_asset_count": unpaid,
            "monitor_snapshot_date": snapshot,
            "repaid_asset_ratio": _ratio(row["repaid_asset_count"], asset_den),
            "repayment_amount_ratio": _ratio(row["repayment_amount"], min_den),
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
        return {
            "trust_product_id": trust_product_id,
            "trust_product_name": product_row["name"],
            "issue_dates": issue_dates,
            "issuance_baseline": None,
            "monitor_stock": fetch_monitor_stock(conn, trust_product_id, city=city),
            "periods": [],
            "by_city": [],
            "warnings": ["该产品暂无发行数据，无法计算发行基准与占比。"],
        }

    baseline = fetch_issuance_baseline(
        conn, trust_product_id, resolved_issue, city=city,
    )
    stock = fetch_monitor_stock(conn, trust_product_id, city=city)
    periods = fetch_repayment_period_rows(
        conn, trust_product_id, period, date_from, date_to, city=city,
    )
    periods = _attach_ratios(periods, baseline, stock)

    by_city: list[dict[str, Any]] = []
    if include_city_breakdown and not city:
        by_city = fetch_city_breakdown(
            conn, trust_product_id, resolved_issue, period, date_from, date_to,
        )

    warnings: list[str] = []
    if baseline["asset_primary_count"] == 0:
        warnings.append("所选发行日无有效资产主编号。")
    if baseline["min_transferable_total"] <= 0:
        warnings.append("MIN 可转让金额合计为 0，还款金额占比无法计算。")
    if baseline["receivable_transfer_total"] <= 0:
        warnings.append("应收账款转让价款合计为 0。")
    if stock["monitor_snapshot_date"] is None:
        warnings.append("该产品暂无监控快照，未还清资产数无法计算。")

    return {
        "trust_product_id": trust_product_id,
        "trust_product_name": product_row["name"],
        "issue_date": resolved_issue,
        "issue_dates": issue_dates,
        "issuance_baseline": {
            "issue_date": resolved_issue,
            **baseline,
        },
        "monitor_stock": stock,
        "period": period,
        "date_from": str(date_from),
        "date_to": str(date_to),
        "city_filter": city,
        "periods": periods,
        "by_city": by_city,
        "warnings": warnings,
    }
