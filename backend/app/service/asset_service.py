from sqlalchemy.engine import Engine

from app.projection.constants import PROJECTION_VERSION, RUNTIME_PHASE
from app.projection.meta import utc_now_iso
from app.projection.header_builder import HeaderBuilder
from app.projection.operations_builder import OperationsBuilder
from app.projection.registry import ProjectionRegistry
from app.projection.snapshot_builder import SnapshotBuilder
from app.projection.timeline_builder import TimelineBuilder
from app.repo.event_repo import EventRepo
from app.repo.followup_repo import FollowupRepo
from app.repo.issuance_repo import IssuanceRepo
from app.repo.monitor_repo import MonitorRepo
from app.repo.repayment_repo import RepaymentRepo
from app.repo.risk_repo import RiskRepo
from app.repo.trust_asset_repo import TrustAssetRepo

REGISTRY_KIND_HEADER = "header"
REGISTRY_KIND_SNAPSHOT = "snapshot"
REGISTRY_KIND_TIMELINE = "timeline"
REGISTRY_KIND_OPERATIONS = "operations"


class AssetApplicationService:
    """M3.2 Application Service — forward via ProjectionRegistry only."""

    def __init__(self, engine: Engine):
        issuance_repo = IssuanceRepo(engine)
        monitor_repo = MonitorRepo(engine)
        repayment_repo = RepaymentRepo(engine)
        risk_repo = RiskRepo(engine)
        followup_repo = FollowupRepo(engine)
        event_repo = EventRepo(engine)
        trust_asset_repo = TrustAssetRepo(engine)

        self._registry = ProjectionRegistry()
        self._registry.register(REGISTRY_KIND_HEADER, HeaderBuilder(issuance_repo))
        self._registry.register(
            REGISTRY_KIND_SNAPSHOT,
            SnapshotBuilder(
                issuance_repo, monitor_repo, repayment_repo, risk_repo, trust_asset_repo
            ),
        )
        self._registry.register(
            REGISTRY_KIND_TIMELINE,
            TimelineBuilder(issuance_repo, event_repo, trust_asset_repo),
        )
        self._registry.register(
            REGISTRY_KIND_OPERATIONS,
            OperationsBuilder(issuance_repo, followup_repo, trust_asset_repo),
        )

    @property
    def registry(self) -> ProjectionRegistry:
        return self._registry

    def fetch_header(self, identity_id: int) -> dict | None:
        return self._registry.build(REGISTRY_KIND_HEADER, identity_id)

    def fetch_snapshot(self, identity_id: int) -> dict | None:
        return self._registry.build(REGISTRY_KIND_SNAPSHOT, identity_id)

    def fetch_timeline(self, identity_id: int) -> dict | None:
        return self._registry.build(REGISTRY_KIND_TIMELINE, identity_id)

    def fetch_operations(self, identity_id: int) -> dict | None:
        return self._registry.build(REGISTRY_KIND_OPERATIONS, identity_id)

    def rebuild_projection(self, identity_id: int) -> dict | None:
        """M3.3 A-1: invalidate cache + full Registry rebuild for identity_id."""
        result = self._registry.rebuild_all(identity_id)
        if result is None:
            return None
        result["runtime_phase"] = RUNTIME_PHASE
        result["projection_version"] = PROJECTION_VERSION
        return result

    def invalidate_projection(self, identity_id: int) -> dict | None:
        """
        M3.3 A-2: bump cache_inv_version and drop cached projections only.
        Does not rebuild or write to DB.
        """
        header_builder = self._registry.get(REGISTRY_KIND_HEADER)
        if header_builder.build(identity_id) is None:
            return None
        inv = self._registry.invalidate(identity_id)
        return {
            "identity_id": identity_id,
            "invalidated_at": utc_now_iso(),
            "cache_inv_version": inv,
            "rebuilt": False,
            "runtime_phase": RUNTIME_PHASE,
        }


def build_asset_application_service(engine: Engine) -> AssetApplicationService:
    return AssetApplicationService(engine)
