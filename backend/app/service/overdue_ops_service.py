"""Overdue Ops Service — orchestration only; delegates to engines."""

from sqlalchemy.engine import Engine

from app.overdue.action_engine import ActionEngine
from app.overdue.case_engine import OverdueCaseEngine
from app.overdue.queue_engine import QueueEngine
from app.overdue.sla_engine import SLAEngine
from app.projection.constants import IDENTITY_MODE, RUNTIME_PHASE
from app.repo.issuance_repo import IssuanceRepo
from app.repo.monitor_repo import MonitorRepo
from app.repo.repayment_repo import RepaymentRepo
from app.repo.trust_asset_repo import TrustAssetRepo


class OverdueOpsService:
    def __init__(self, engine: Engine):
        issuance_repo = IssuanceRepo(engine)
        monitor_repo = MonitorRepo(engine)
        repayment_repo = RepaymentRepo(engine)
        trust_asset_repo = TrustAssetRepo(engine)

        self._case_engine = OverdueCaseEngine(
            issuance_repo, monitor_repo, repayment_repo, trust_asset_repo
        )
        self._action_engine = ActionEngine()
        self._sla_engine = SLAEngine()
        self._queue_engine = QueueEngine()

    def get_cases(self, identity_id: int) -> list[dict]:
        return self._case_engine.build_cases(identity_id)

    def get_actions(self, identity_id: int) -> list[dict]:
        cases = self.get_cases(identity_id)
        return self._action_engine.build_actions(cases)

    def get_sla(self, identity_id: int) -> list[dict]:
        cases = self.get_cases(identity_id)
        return self._sla_engine.evaluate(cases)

    def get_queue(self, identity_id: int) -> list[dict]:
        cases = self.get_cases(identity_id)
        actions = self._action_engine.build_actions(cases)
        sla = self._sla_engine.evaluate(cases)
        return self._queue_engine.build_queue(cases, actions, sla)

    def get_ops(self, identity_id: int) -> dict | None:
        """Full ops payload for one identity."""
        issuance_repo = self._case_engine._issuance_repo
        if issuance_repo.fetch_by_identity_id(identity_id) is None:
            return None

        cases = self._case_engine.build_cases(identity_id)
        actions = self._action_engine.build_actions(cases)
        sla = self._sla_engine.evaluate(cases)
        queue = self._queue_engine.build_queue(cases, actions, sla)

        return {
            "identity_id": identity_id,
            "identity_mode": IDENTITY_MODE,
            "runtime_phase": RUNTIME_PHASE,
            "engine": "M3_OVERDUE_OPS_V1",
            "cases": cases,
            "actions": actions,
            "sla": sla,
            "queue": queue,
        }


def build_overdue_ops_service(engine: Engine) -> OverdueOpsService:
    return OverdueOpsService(engine)
