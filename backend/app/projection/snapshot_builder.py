from app.projection.constants import (
    BUILDER_VERSION_SNAPSHOT,
    SNAPSHOT_VERSION,
)
from app.projection.meta import build_meta, wrap_projection
from app.projection.scope import resolve_trust_asset_id
from app.repo.issuance_repo import IssuanceRepo
from app.repo.monitor_repo import MonitorRepo
from app.repo.repayment_repo import RepaymentRepo
from app.repo.risk_repo import RiskRepo
from app.repo.trust_asset_repo import TrustAssetRepo


class SnapshotBuilder:
    def __init__(
        self,
        issuance_repo: IssuanceRepo,
        monitor_repo: MonitorRepo,
        repayment_repo: RepaymentRepo,
        risk_repo: RiskRepo,
        trust_asset_repo: TrustAssetRepo,
    ):
        self._issuance_repo = issuance_repo
        self._monitor_repo = monitor_repo
        self._repayment_repo = repayment_repo
        self._risk_repo = risk_repo
        self._trust_asset_repo = trust_asset_repo

    def build(self, identity_id: int) -> dict | None:
        issuance = self._issuance_repo.fetch_by_identity_id(identity_id)
        if not issuance:
            return None

        trust_asset_id = resolve_trust_asset_id(issuance, self._trust_asset_repo)
        monitor = None
        repayment: list = []
        risk: list = []
        if trust_asset_id:
            monitor = self._monitor_repo.fetch_latest(trust_asset_id)
            repayment = self._repayment_repo.fetch_by_trust_asset_id(trust_asset_id)
            risk = self._risk_repo.fetch_by_trust_asset_id(trust_asset_id)

        data = {
            "identity_id": identity_id,
            "projection_kind": "asset_snapshot",
            "issuance": issuance,
            "monitor": monitor,
            "repayment": repayment,
            "risk": risk,
        }
        meta = build_meta(
            builder_version=BUILDER_VERSION_SNAPSHOT,
            snapshot_version=SNAPSHOT_VERSION,
        )
        return wrap_projection(data, meta)
