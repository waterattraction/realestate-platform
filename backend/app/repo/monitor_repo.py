from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.overdue.buckets import OVERDUE_ASSET_MIN_DAYS
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
