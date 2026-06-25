from sqlalchemy import text
from sqlalchemy.engine import Engine


class TrustAssetRepo:
    """Single-table lookup — resolve persistence FK when issuance.trust_asset_id is null."""

    def __init__(self, engine: Engine):
        self._engine = engine

    def fetch_id_by_product_custody(
        self, trust_product_id: int, custody_asset_code: str | None
    ) -> int | None:
        if not custody_asset_code:
            return None
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id
                    FROM trust_assets
                    WHERE trust_product_id = :trust_product_id
                      AND custody_asset_code = :custody_asset_code
                    LIMIT 1
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "custody_asset_code": custody_asset_code,
                },
            ).fetchone()
        return int(row.id) if row else None
