from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.overdue.buckets import (
    OVERDUE_ASSET_MIN_DAYS,
    RECONCILIATION_TOLERANCE_DEFAULT,
    sql_agg_delinquency_filter_any,
    sql_custody_list_sort_priority,
)
from app.repo._serialize import row_to_dict, rows_to_dicts


class MonitorRepo:
    def __init__(self, engine: Engine):
        self._engine = engine

    def fetch_latest(self, trust_asset_id: int) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        id,
                        trust_product_id,
                        trust_asset_id,
                        asset_code,
                        custody_asset_code,
                        source_asset_code,
                        data_date,
                        initial_transfer_amount,
                        repaid_amount,
                        remaining_amount,
                        overdue_days,
                        last_payment_date,
                        risk_score,
                        risk_level,
                        synced_at
                    FROM trust_asset_monitor_records
                    WHERE trust_asset_id = :trust_asset_id
                    ORDER BY data_date DESC
                    LIMIT 1
                    """
                ),
                {"trust_asset_id": trust_asset_id},
            ).fetchone()
        return row_to_dict(row)

    def fetch_all_for_asset(self, trust_asset_id: int) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        id,
                        trust_asset_id,
                        data_date,
                        repaid_amount,
                        remaining_amount,
                        overdue_days,
                        synced_at
                    FROM trust_asset_monitor_records
                    WHERE trust_asset_id = :trust_asset_id
                    ORDER BY data_date DESC
                    """
                ),
                {"trust_asset_id": trust_asset_id},
            ).fetchall()
        return rows_to_dicts(rows)

    def resolve_latest_data_date(
        self, trust_product_id: int | None, data_date: str | None
    ) -> str | None:
        with self._engine.connect() as conn:
            if data_date:
                return data_date
            if trust_product_id is not None:
                row = conn.execute(
                    text(
                        """
                        SELECT MAX(data_date) AS data_date
                        FROM trust_asset_monitor_records
                        WHERE trust_product_id = :trust_product_id
                        """
                    ),
                    {"trust_product_id": trust_product_id},
                ).fetchone()
            else:
                row = conn.execute(
                    text("SELECT MAX(data_date) AS data_date FROM trust_asset_monitor_records")
                ).fetchone()
        if row is None or row.data_date is None:
            return None
        return str(row.data_date)

    def fetch_splits_by_custody(
        self,
        trust_product_id: int,
        custody_asset_code: str,
        data_date: str,
    ) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        m.trust_asset_id,
                        m.asset_code,
                        COALESCE(m.custody_asset_code, ta.custody_asset_code, m.asset_code)
                            AS custody_asset_code,
                        COALESCE(m.source_asset_code, ta.source_asset_code, m.asset_code)
                            AS source_asset_code,
                        m.trust_product_id,
                        m.data_date,
                        m.overdue_days,
                        m.risk_score,
                        m.risk_level,
                        m.initial_transfer_amount,
                        m.repaid_amount,
                        m.remaining_amount,
                        m.last_payment_date,
                        m.max_payment_date,
                        ta.asset_name,
                        tp.name AS trust_product_name
                    FROM trust_asset_monitor_records m
                    INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
                    INNER JOIN trust_products tp ON tp.id = m.trust_product_id
                    WHERE m.trust_product_id = :trust_product_id
                      AND m.data_date = :data_date
                      AND COALESCE(m.custody_asset_code, ta.custody_asset_code, m.asset_code)
                          = :custody_asset_code
                    ORDER BY m.risk_score DESC NULLS LAST,
                             m.overdue_days DESC,
                             m.asset_code
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "custody_asset_code": custody_asset_code,
                    "data_date": data_date,
                },
            ).fetchall()
        return rows_to_dicts(rows)

    def fetch_splits_by_asset_code(
        self,
        trust_product_id: int,
        asset_code: str,
        data_date: str,
    ) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        m.trust_asset_id,
                        m.asset_code,
                        COALESCE(m.custody_asset_code, ta.custody_asset_code, m.asset_code)
                            AS custody_asset_code,
                        COALESCE(m.source_asset_code, ta.source_asset_code, m.asset_code)
                            AS source_asset_code,
                        m.trust_product_id,
                        m.data_date,
                        m.overdue_days,
                        m.risk_score,
                        m.risk_level,
                        m.initial_transfer_amount,
                        m.repaid_amount,
                        m.remaining_amount,
                        m.last_payment_date,
                        m.max_payment_date,
                        ta.asset_name,
                        tp.name AS trust_product_name
                    FROM trust_asset_monitor_records m
                    INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
                    INNER JOIN trust_products tp ON tp.id = m.trust_product_id
                    WHERE m.trust_product_id = :trust_product_id
                      AND m.data_date = :data_date
                      AND m.asset_code = :asset_code
                    ORDER BY m.risk_score DESC NULLS LAST,
                             m.overdue_days DESC,
                             m.custody_asset_code
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "asset_code": asset_code,
                    "data_date": data_date,
                },
            ).fetchall()
        return rows_to_dicts(rows)

    def resolve_asset_code(
        self,
        trust_product_id: int,
        custody_asset_code: str,
        data_date: str | None = None,
    ) -> str | None:
        """Legacy: map custody URL param to canonical asset_code."""
        with self._engine.connect() as conn:
            params: dict = {
                "trust_product_id": trust_product_id,
                "custody_asset_code": custody_asset_code,
            }
            date_clause = ""
            if data_date:
                date_clause = "AND m.data_date = :data_date"
                params["data_date"] = data_date
            row = conn.execute(
                text(
                    f"""
                    SELECT m.asset_code
                    FROM trust_asset_monitor_records m
                    INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
                    WHERE m.trust_product_id = :trust_product_id
                      AND COALESCE(m.custody_asset_code, ta.custody_asset_code, m.asset_code)
                          = :custody_asset_code
                      {date_clause}
                    ORDER BY m.data_date DESC
                    LIMIT 1
                    """
                ),
                params,
            ).fetchone()
        if row is None or row.asset_code is None:
            return None
        return str(row.asset_code)

    def fetch_custody_queue(
        self, trust_product_id: int, data_date: str, limit: int = 50
    ) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        COALESCE(m.custody_asset_code, ta.custody_asset_code, m.asset_code)
                            AS custody_asset_code,
                        MAX(m.overdue_days) AS overdue_days,
                        SUM(m.remaining_amount) AS remaining_amount,
                        COUNT(*) AS split_count
                    FROM trust_asset_monitor_records m
                    INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
                    WHERE m.trust_product_id = :trust_product_id
                      AND m.data_date = :data_date
                      AND m.overdue_days >= :overdue_min_days
                    GROUP BY COALESCE(m.custody_asset_code, ta.custody_asset_code, m.asset_code)
                    ORDER BY MAX(m.overdue_days) DESC
                    LIMIT :limit
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "data_date": data_date,
                    "overdue_min_days": OVERDUE_ASSET_MIN_DAYS,
                    "limit": limit,
                },
            ).fetchall()
        return rows_to_dicts(rows)

    def fetch_asset_queue(
        self,
        trust_product_id: int | None = None,
        data_date: str = "",
        limit: int = 100,
        trust_marker: str | None = None,
        trust_markers: list[str] | None = None,
        followup_status: str | None = None,
        followup_statuses: list[str] | None = None,
        delinquency_bucket: str | None = None,
        delinquency_buckets: list[str] | None = None,
        trust_product_ids: list[int] | None = None,
        prefer_trust_product_id: int | None = None,
        prefer_asset_code: str | None = None,
    ) -> list[dict]:
        """Return one row per asset_code for the workbench left-column list.

        全序：等级优先级 → 逾期天数 DESC → 资产主编号 ASC → trust_product_id。
        默认取全序第 1 页（OFFSET 0 LIMIT）。
        有 prefer_* 时：翻到该资产所在页（同序 OFFSET 对齐到 limit 边界），页内顺序不变。
        """
        from app import query_utils

        ids = trust_product_ids
        if ids is None and trust_product_id is not None:
            ids = [trust_product_id]
        pid_sql, pid_params = query_utils.sql_in_int_column(
            "m.trust_product_id", ids, param_prefix="qpid"
        )
        markers = trust_markers
        if markers is None and trust_marker:
            markers = [trust_marker]
        marker_sql, marker_params = query_utils.sql_in_str_column(
            "tm.trust_marker", markers, param_prefix="qmarker"
        )
        marker_clause = (
            f"""AND EXISTS (
                SELECT 1 FROM trust_asset_trust_marks tm
                WHERE tm.trust_product_id = m.trust_product_id
                  AND tm.asset_code = m.asset_code
                  {marker_sql}
            )"""
            if markers
            else ""
        )
        _ = (followup_status, followup_statuses)
        buckets = delinquency_buckets
        if buckets is None and delinquency_bucket:
            buckets = [delinquency_bucket]
        having_clause = sql_agg_delinquency_filter_any(
            buckets,
            "MAX(m.overdue_days)",
            "SUM(m.remaining_amount)",
            tolerance_param=":tolerance",
        )
        sort_priority = sql_custody_list_sort_priority(
            "MAX(m.overdue_days)",
            "SUM(m.remaining_amount)",
        )
        params: dict = {
            "data_date": data_date,
            "tolerance": RECONCILIATION_TOLERANCE_DEFAULT,
            "limit": limit,
            "offset": 0,
            **pid_params,
            **marker_params,
        }

        agg_sql = f"""
            SELECT
                m.asset_code,
                m.trust_product_id,
                tp.name AS trust_product_name,
                MAX(m.overdue_days)     AS overdue_days,
                SUM(m.remaining_amount) AS remaining_amount,
                COUNT(*)                AS split_count,
                ARRAY_AGG(
                    DISTINCT COALESCE(m.custody_asset_code, ta.custody_asset_code, m.asset_code)
                    ORDER BY COALESCE(m.custody_asset_code, ta.custody_asset_code, m.asset_code)
                ) AS custody_asset_codes,
                ({sort_priority}) AS sort_priority
            FROM trust_asset_monitor_records m
            INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
            INNER JOIN trust_products tp ON tp.id = m.trust_product_id
            WHERE m.data_date = :data_date
              {pid_sql}
              {marker_clause}
            GROUP BY m.asset_code, m.trust_product_id, tp.name
            HAVING {having_clause}
        """

        prefer_code = (prefer_asset_code or "").strip() or None
        use_prefer = prefer_trust_product_id is not None and prefer_code is not None

        page_sql = f"""
            SELECT
                asset_code,
                trust_product_id,
                trust_product_name,
                overdue_days,
                remaining_amount,
                split_count,
                custody_asset_codes
            FROM ({agg_sql}) agg
            ORDER BY
                sort_priority ASC,
                COALESCE(overdue_days, 0) DESC,
                asset_code ASC,
                trust_product_id ASC
            OFFSET :offset
            LIMIT :limit
        """

        with self._engine.connect() as conn:
            if use_prefer:
                rank_row = conn.execute(
                    text(
                        f"""
                        SELECT rn
                        FROM (
                            SELECT
                                trust_product_id,
                                asset_code,
                                ROW_NUMBER() OVER (
                                    ORDER BY
                                        sort_priority ASC,
                                        COALESCE(overdue_days, 0) DESC,
                                        asset_code ASC,
                                        trust_product_id ASC
                                ) AS rn
                            FROM ({agg_sql}) agg
                        ) ranked
                        WHERE trust_product_id = :prefer_pid
                          AND asset_code = :prefer_code
                        LIMIT 1
                        """
                    ),
                    {
                        **params,
                        "prefer_pid": int(prefer_trust_product_id),
                        "prefer_code": prefer_code,
                    },
                ).fetchone()
                if rank_row is not None:
                    rn = int(rank_row.rn)
                    params["offset"] = ((rn - 1) // int(limit)) * int(limit)

            rows = conn.execute(text(page_sql), params).fetchall()
        return rows_to_dicts(rows)
