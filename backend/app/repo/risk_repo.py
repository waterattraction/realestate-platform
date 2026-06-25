from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.repo._serialize import rows_to_dicts


class RiskRepo:
    def __init__(self, engine: Engine):
        self._engine = engine

    def fetch_by_trust_asset_id(self, trust_asset_id: int, limit: int = 50) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        id,
                        trust_product_id,
                        trust_asset_id,
                        data_date,
                        risk_type,
                        risk_level,
                        trigger_rule,
                        status,
                        generated_at,
                        resolved_at
                    FROM risk_alerts
                    WHERE trust_asset_id = :trust_asset_id
                    ORDER BY generated_at DESC
                    LIMIT :limit
                    """
                ),
                {"trust_asset_id": trust_asset_id, "limit": limit},
            ).fetchall()
        return rows_to_dicts(rows)
