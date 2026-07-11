from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.repo._serialize import rows_to_dicts


class RepaymentRepo:
    def __init__(self, engine: Engine):
        self._engine = engine

    def fetch_by_trust_asset_id(self, trust_asset_id: int, limit: int = 100) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
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
                        period_no,
                        actual_repayment_amount,
                        repayment_date,
                        synced_at
                    FROM trust_repayment_detail_records
                    WHERE trust_asset_id = :trust_asset_id
                    ORDER BY repayment_date DESC NULLS LAST, id DESC
                    LIMIT :limit
                    """
                ),
                {"trust_asset_id": trust_asset_id, "limit": limit},
            ).fetchall()
        return rows_to_dicts(rows)

    def fetch_by_product_custody(
        self, trust_product_id: int, custody_asset_code: str, limit: int = 500
    ) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
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
                        period_no,
                        actual_repayment_amount,
                        repayment_date,
                        synced_at
                    FROM trust_repayment_detail_records
                    WHERE trust_product_id = :trust_product_id
                      AND COALESCE(custody_asset_code, asset_code) = :custody_asset_code
                    ORDER BY repayment_date DESC NULLS LAST, id DESC
                    LIMIT :limit
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "custody_asset_code": custody_asset_code,
                    "limit": limit,
                },
            ).fetchall()
        return rows_to_dicts(rows)

    def sum_by_product_custody(self, trust_product_id: int, custody_asset_code: str) -> float:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT COALESCE(SUM(actual_repayment_amount), 0) AS total
                    FROM trust_repayment_detail_records
                    WHERE trust_product_id = :trust_product_id
                      AND COALESCE(custody_asset_code, asset_code) = :custody_asset_code
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "custody_asset_code": custody_asset_code,
                },
            ).fetchone()
        return float(row.total) if row else 0.0

    def fetch_by_product_asset_code(
        self, trust_product_id: int, asset_code: str, limit: int = 500
    ) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
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
                        period_no,
                        actual_repayment_amount,
                        repayment_date,
                        synced_at
                    FROM trust_repayment_detail_records
                    WHERE trust_product_id = :trust_product_id
                      AND asset_code = :asset_code
                    ORDER BY repayment_date DESC NULLS LAST, id DESC
                    LIMIT :limit
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "asset_code": asset_code,
                    "limit": limit,
                },
            ).fetchall()
        return rows_to_dicts(rows)

    def sum_by_product_asset_code(self, trust_product_id: int, asset_code: str) -> float:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT COALESCE(SUM(actual_repayment_amount), 0) AS total
                    FROM trust_repayment_detail_records
                    WHERE trust_product_id = :trust_product_id
                      AND asset_code = :asset_code
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "asset_code": asset_code,
                },
            ).fetchone()
        return float(row.total) if row else 0.0

    def sum_by_canonical_asset_code(self, trust_product_id: int, asset_code: str) -> float:
        """按 trust_assets 权威主编号汇总还款（含事实表 asset_code 写错的行）。"""
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT COALESCE(SUM(r.actual_repayment_amount), 0) AS total
                    FROM trust_repayment_detail_records r
                    INNER JOIN trust_assets ta ON ta.id = r.trust_asset_id
                    WHERE r.trust_product_id = :trust_product_id
                      AND ta.asset_code = :asset_code
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "asset_code": asset_code,
                },
            ).fetchone()
        return float(row.total) if row else 0.0

    def max_repayment_date_by_canonical_asset_code(
        self, trust_product_id: int, asset_code: str
    ) -> str | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT MAX(r.repayment_date) AS max_rd
                    FROM trust_repayment_detail_records r
                    INNER JOIN trust_assets ta ON ta.id = r.trust_asset_id
                    WHERE r.trust_product_id = :trust_product_id
                      AND ta.asset_code = :asset_code
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "asset_code": asset_code,
                },
            ).fetchone()
        if row is None or row.max_rd is None:
            return None
        return str(row.max_rd)

    def fetch_code_mismatch_summary(
        self, trust_product_id: int, canonical_asset_code: str
    ) -> dict | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS row_count,
                        COALESCE(SUM(r.actual_repayment_amount), 0) AS amount_sum
                    FROM trust_repayment_detail_records r
                    INNER JOIN trust_assets ta ON ta.id = r.trust_asset_id
                    WHERE r.trust_product_id = :trust_product_id
                      AND ta.asset_code = :asset_code
                      AND r.asset_code IS DISTINCT FROM ta.asset_code
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "asset_code": canonical_asset_code,
                },
            ).fetchone()
        if row is None or int(row.row_count) == 0:
            return None
        return {
            "row_count": int(row.row_count),
            "amount_sum": float(row.amount_sum),
        }
