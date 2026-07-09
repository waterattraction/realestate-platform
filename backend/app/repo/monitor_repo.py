from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.overdue.buckets import (
    OVERDUE_ASSET_MIN_DAYS,
    RECONCILIATION_TOLERANCE_DEFAULT,
    matches_delinquency_bucket_filter,
    sql_agg_delinquency_filter,
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
        trust_product_id: int | None,
        data_date: str,
        limit: int = 100,
        trust_marker: str | None = None,
        followup_status: str | None = None,
        delinquency_bucket: str = "M2_PLUS",
    ) -> list[dict]:
        """Return one row per asset_code for the workbench left-column list."""
        pid_clause = (
            "AND m.trust_product_id = :trust_product_id"
            if trust_product_id is not None
            else ""
        )
        marker_clause = (
            """AND EXISTS (
                SELECT 1 FROM trust_asset_trust_marks tm
                WHERE tm.trust_product_id = m.trust_product_id
                  AND tm.asset_code = m.asset_code
                  AND tm.data_date = :data_date
                  AND tm.trust_marker = :trust_marker
            )"""
            if trust_marker
            else ""
        )
        status_clause = (
            """AND EXISTS (
                SELECT 1 FROM trust_asset_trust_marks tm2
                WHERE tm2.trust_product_id = m.trust_product_id
                  AND tm2.asset_code = m.asset_code
                  AND tm2.data_date = :data_date
                  AND tm2.internal_status = :followup_status
            )"""
            if followup_status
            else ""
        )
        having_clause = sql_agg_delinquency_filter(
            delinquency_bucket or "M2_PLUS",
            "MAX(m.overdue_days)",
            "SUM(m.remaining_amount)",
            tolerance_param=":tolerance",
        )
        params: dict = {
            "data_date": data_date,
            "tolerance": RECONCILIATION_TOLERANCE_DEFAULT,
            "limit": limit,
        }
        if trust_product_id is not None:
            params["trust_product_id"] = trust_product_id
        if trust_marker:
            params["trust_marker"] = trust_marker
        if followup_status:
            params["followup_status"] = followup_status
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
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
                        ) AS custody_asset_codes
                    FROM trust_asset_monitor_records m
                    INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
                    INNER JOIN trust_products tp ON tp.id = m.trust_product_id
                    WHERE m.data_date = :data_date
                      {pid_clause}
                      {marker_clause}
                      {status_clause}
                    GROUP BY m.asset_code, m.trust_product_id, tp.name
                    HAVING {having_clause}
                    ORDER BY MAX(m.overdue_days) DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).fetchall()
        return rows_to_dicts(rows)
