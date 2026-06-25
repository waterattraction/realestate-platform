from app.projection.constants import (
    BUILDER_VERSION_HEADER,
    SNAPSHOT_VERSION,
)
from app.projection.meta import build_meta, wrap_projection
from app.repo.issuance_repo import IssuanceRepo


class HeaderBuilder:
    def __init__(self, issuance_repo: IssuanceRepo):
        self._issuance_repo = issuance_repo

    def build(self, identity_id: int) -> dict | None:
        issuance = self._issuance_repo.fetch_by_identity_id(identity_id)
        if not issuance:
            return None
        data = {
            "identity_id": identity_id,
            "asset_name": issuance.get("contract_name") or issuance.get("debtor_name") or "",
            "trust_product": issuance.get("trust_product_name") or "",
            "issue_date": issuance.get("issue_date"),
            "canonical_custody_asset_code": issuance.get("custody_asset_code"),
        }
        meta = build_meta(
            builder_version=BUILDER_VERSION_HEADER,
            snapshot_version=SNAPSHOT_VERSION,
        )
        return wrap_projection(data, meta)
