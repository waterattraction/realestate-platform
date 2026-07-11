"""Amount / repayment reconciliation checks for overdue workbench."""

from app.overdue.buckets import (
    RECONCILIATION_TOLERANCE_DEFAULT,
    calc_risk_level,
)

RECONCILIATION_TOLERANCE = RECONCILIATION_TOLERANCE_DEFAULT
RECONCILIATION_BASIS_LABEL = "监控快照日 + 全量还款明细"

__all__ = [
    "RECONCILIATION_TOLERANCE",
    "RECONCILIATION_BASIS_LABEL",
    "calc_risk_level",
    "is_es_closed",
    "run_asset_checks",
    "run_custody_checks",
]


def is_es_closed(remaining_amount: float, *, tolerance: float = RECONCILIATION_TOLERANCE) -> bool:
    return remaining_amount <= tolerance


def run_asset_checks(
    initial: float,
    repaid: float,
    remaining: float,
    detail_total: float,
    *,
    code_mismatch: dict | None = None,
) -> dict:
    balance_remainder = remaining - initial + repaid
    cross_diff = repaid - detail_total
    balance_passed = abs(balance_remainder) <= RECONCILIATION_TOLERANCE
    cross_passed = abs(cross_diff) <= RECONCILIATION_TOLERANCE
    code_mismatch_passed = code_mismatch is None
    result = {
        "balance_equation": {
            "passed": balance_passed,
            "left_amount": remaining,
            "right_amount": initial - repaid,
            "diff_amount": balance_remainder,
        },
        "cross_sheet_repayment": {
            "passed": cross_passed,
            "left_amount": repaid,
            "right_amount": detail_total,
            "diff_amount": cross_diff,
        },
        "has_anomaly": not balance_passed or not cross_passed or not code_mismatch_passed,
    }
    if code_mismatch is not None:
        result["code_mismatch"] = {
            "passed": code_mismatch_passed,
            "row_count": int(code_mismatch.get("row_count") or 0),
            "amount_sum": float(code_mismatch.get("amount_sum") or 0),
        }
    return result


def run_custody_checks(
    splits: list[dict],
    repayment_total: float,
    *,
    code_mismatch: dict | None = None,
) -> dict:
    initial = sum(float(s.get("initial_transfer_amount") or 0) for s in splits)
    repaid = sum(float(s.get("repaid_amount") or 0) for s in splits)
    remaining = sum(float(s.get("remaining_amount") or 0) for s in splits)
    return run_asset_checks(
        initial, repaid, remaining, repayment_total, code_mismatch=code_mismatch
    )
