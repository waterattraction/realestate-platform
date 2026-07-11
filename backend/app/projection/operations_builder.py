from app.projection.constants import (
    BUILDER_VERSION_OPERATIONS,
    SNAPSHOT_VERSION,
)
from app.projection.meta import build_meta, wrap_projection
from app.projection.scope import resolve_trust_asset_id
from app.repo.followup_repo import FollowupRepo
from app.repo.issuance_repo import IssuanceRepo
from app.repo.trust_asset_repo import TrustAssetRepo


class OperationsBuilder:
    def __init__(
        self,
        issuance_repo: IssuanceRepo,
        followup_repo: FollowupRepo,
        trust_asset_repo: TrustAssetRepo,
    ):
        self._issuance_repo = issuance_repo
        self._followup_repo = followup_repo
        self._trust_asset_repo = trust_asset_repo

    def build(self, identity_id: int) -> dict | None:
        issuance = self._issuance_repo.fetch_by_identity_id(identity_id)
        if not issuance:
            return None

        trust_asset_id = resolve_trust_asset_id(issuance, self._trust_asset_repo)
        followups: list[dict] = []
        if trust_asset_id:
            raw = self._followup_repo.fetch_by_trust_asset_id(trust_asset_id)
            followups = [
                {
                    "type": "FOLLOWUP",
                    "id": row.get("id"),
                    "status": row.get("status"),
                    "owner_name": row.get("owner_name"),
                    "data_date": row.get("data_date"),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("created_at"),
                }
                for row in raw
            ]

        data = {
            "identity_id": identity_id,
            "projection_kind": "asset_operations",
            "operations": followups,
        }
        meta = build_meta(
            builder_version=BUILDER_VERSION_OPERATIONS,
            snapshot_version=SNAPSHOT_VERSION,
        )
        return wrap_projection(data, meta)
