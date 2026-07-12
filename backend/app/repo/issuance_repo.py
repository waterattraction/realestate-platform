from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.repo._serialize import row_to_dict, rows_to_dicts

_ISSUANCE_DETAIL_SELECT = """
    SELECT
        i.id,
        i.trust_product_id,
        i.trust_product_name,
        i.from_trust_product_name,
        i.migration_type,
        i.trust_asset_id,
        i.issue_date,
        i.custody_asset_code,
        i.business_asset_key,
        i.contract_name,
        i.debtor_name,
        i.property_address,
        i.city,
        i.contractor_name,
        i.receivable_contract_amount,
        i.asset_transfer_discount_rate,
        i.receivable_transfer_amount,
        i.min_institution_transferable_amount,
        i.rental_price,
        i.rent_withholding_ratio,
        i.calculated_rent_withholding_per_period,
        i.first_rent_withholding_date,
        i.withholding_periods_at_pooling,
        i.signing_date,
        i.rental_contract_end_date,
        i.source_file_name,
        i.source_sheet_name,
        i.source_row_number
    FROM trust_product_issuance_asset_records i
"""

_PRIMARY_ASSET_MATCH_SQL = """
    (
        i.custody_asset_code = :primary_asset_code
        OR split_part(i.custody_asset_code, '-', 1) = :primary_asset_code
    )
"""


class IssuanceRepo:
    """Single-table reads for trust_product_issuance_asset_records."""

    def __init__(self, engine: Engine):
        self._engine = engine

    def fetch_by_identity_id(self, identity_id: int) -> dict | None:
        """
        Phase-0 surrogate: identity_id = trust_product_issuance_asset_records.id
        until M3.1 asset_identities is migrated.
        """
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        i.id,
                        i.trust_product_id,
                        i.trust_product_name,
                        i.trust_asset_id,
                        i.issue_date,
                        i.custody_asset_code,
                        i.business_asset_key,
                        i.contract_name,
                        i.debtor_name,
                        i.property_address,
                        i.city,
                        i.receivable_contract_amount,
                        i.receivable_transfer_amount,
                        i.created_at,
                        i.updated_at
                    FROM trust_product_issuance_asset_records i
                    WHERE i.id = :identity_id
                    LIMIT 1
                    """
                ),
                {"identity_id": identity_id},
            ).fetchone()
        return row_to_dict(row)

    def fetch_by_product_custody(
        self, trust_product_id: int, custody_asset_code: str
    ) -> list[dict]:
        return self.fetch_by_product_custodies(trust_product_id, [custody_asset_code])

    def fetch_for_asset_code(
        self,
        trust_product_id: int,
        asset_code: str,
        custody_asset_codes: list[str] | None = None,
    ) -> list[dict]:
        """Issuance rows for workbench display keyed by monitor asset_code.

        Cross-product chain: matches primary asset_code and custody suffix variants
        (e.g. 107112396048 and 107112396048-1). trust_product_id is ignored here;
        callers pick identity_id for the current product separately.
        """
        _ = trust_product_id, custody_asset_codes
        return self.fetch_by_primary_asset_code(asset_code)

    def fetch_by_primary_asset_code(self, primary_asset_code: str) -> list[dict]:
        """All issuance rows for an asset primary code across trust products."""
        code = (primary_asset_code or "").strip()
        if not code:
            return []
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    {_ISSUANCE_DETAIL_SELECT}
                    WHERE {_PRIMARY_ASSET_MATCH_SQL}
                    ORDER BY i.issue_date ASC, i.trust_product_id, i.id ASC
                    """
                ),
                {"primary_asset_code": code},
            ).fetchall()
        return rows_to_dicts(rows)

    def fetch_by_product_custodies(
        self, trust_product_id: int, custody_asset_codes: list[str]
    ) -> list[dict]:
        """Fetch issuance records for multiple custody codes under one product.

        Results are ordered by custody_asset_code then issue_date DESC so the
        caller can group by custody_asset_code without re-sorting.
        """
        if not custody_asset_codes:
            return []
        placeholders = ", ".join(f":c{i}" for i in range(len(custody_asset_codes)))
        params: dict = {"trust_product_id": trust_product_id}
        for i, code in enumerate(custody_asset_codes):
            params[f"c{i}"] = code
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    {_ISSUANCE_DETAIL_SELECT}
                    WHERE i.trust_product_id = :trust_product_id
                      AND i.custody_asset_code IN ({placeholders})
                    ORDER BY i.custody_asset_code, i.issue_date DESC, i.id DESC
                    """
                ),
                params,
            ).fetchall()
        return rows_to_dicts(rows)
