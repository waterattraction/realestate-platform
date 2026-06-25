"""Overdue Case Engine — derived facts from monitor + repayment (no SQL join)."""

from app.overdue.rules import stage_from_overdue_days, utc_today
from app.projection.scope import resolve_trust_asset_id
from app.repo.issuance_repo import IssuanceRepo
from app.repo.monitor_repo import MonitorRepo
from app.repo.repayment_repo import RepaymentRepo
from app.repo.trust_asset_repo import TrustAssetRepo


class OverdueCaseEngine:
  """
  Case = deterministic derived fact from latest monitor + repayment context.
  One open case per identity when overdue_days > 0.
  """

  def __init__(
      self,
      issuance_repo: IssuanceRepo,
      monitor_repo: MonitorRepo,
      repayment_repo: RepaymentRepo,
      trust_asset_repo: TrustAssetRepo,
  ):
      self._issuance_repo = issuance_repo
      self._monitor_repo = monitor_repo
      self._repayment_repo = repayment_repo
      self._trust_asset_repo = trust_asset_repo

  def build_cases(self, identity_id: int) -> list[dict]:
      issuance = self._issuance_repo.fetch_by_identity_id(identity_id)
      if not issuance:
          return []

      trust_asset_id = resolve_trust_asset_id(issuance, self._trust_asset_repo)
      if not trust_asset_id:
          return []

      monitor = self._monitor_repo.fetch_latest(trust_asset_id)
      if not monitor:
          return []

      overdue_days = int(monitor.get("overdue_days") or 0)
      stage = stage_from_overdue_days(overdue_days)
      if stage is None:
          return []

      repayments = self._repayment_repo.fetch_by_trust_asset_id(trust_asset_id, limit=20)
      last_repayment = repayments[0] if repayments else None
      repayment_total = sum(float(r.get("actual_repayment_amount") or 0) for r in repayments)

      custody = (
          monitor.get("custody_asset_code")
          or issuance.get("custody_asset_code")
          or ""
      )
      amount = float(monitor.get("remaining_amount") or 0)
      opened_at = monitor.get("data_date") or utc_today().isoformat()

      return [
          {
              "case_id": f"case:{identity_id}",
              "identity_id": identity_id,
              "custody_asset_code": custody,
              "stage": stage,
              "overdue_days": overdue_days,
              "amount": amount,
              "status": "open",
              "opened_at": opened_at,
              "monitor_data_date": monitor.get("data_date"),
              "repayment_summary": {
                  "recent_count": len(repayments),
                  "cumulative_recent": repayment_total,
                  "last_repayment_date": (
                      last_repayment.get("repayment_date") if last_repayment else None
                  ),
              },
          }
      ]
