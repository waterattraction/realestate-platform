from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.repo._serialize import row_to_dict, rows_to_dicts


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
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
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
                    WHERE i.trust_product_id = :trust_product_id
                      AND i.custody_asset_code = :custody_asset_code
                    ORDER BY i.issue_date DESC, i.id DESC
                    """
                ),
                {
                    "trust_product_id": trust_product_id,
                    "custody_asset_code": custody_asset_code,
                },
            ).fetchall()
        return rows_to_dicts(rows)
