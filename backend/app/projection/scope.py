"""Resolve trust_asset_id for Phase-0 scope (issuance FK or product+custody lookup)."""

from app.repo.issuance_repo import IssuanceRepo
from app.repo.trust_asset_repo import TrustAssetRepo


def resolve_trust_asset_id(
    issuance: dict,
    trust_asset_repo: TrustAssetRepo,
) -> int | None:
    trust_asset_id = issuance.get("trust_asset_id")
    if trust_asset_id:
        return int(trust_asset_id)
    return trust_asset_repo.fetch_id_by_product_custody(
        int(issuance["trust_product_id"]),
        issuance.get("custody_asset_code"),
    )
