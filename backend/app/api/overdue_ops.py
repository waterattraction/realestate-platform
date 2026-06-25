"""M3 Overdue Ops API — operational system entry (no business logic in routes)."""

from fastapi import APIRouter, HTTPException

from app.db import get_engine
from app.service.overdue_ops_service import build_overdue_ops_service

router = APIRouter(tags=["overdue-ops"])

_service = build_overdue_ops_service(get_engine())


@router.get("/overdue/ops/{identity_id}")
def get_overdue_ops(identity_id: int) -> dict:
    """
    Deterministic overdue operations: Case → Action → SLA → Queue.
    identity_id = trust_product_issuance_asset_records.id (SURROGATE_PHASE_0).
    """
    payload = _service.get_ops(identity_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "ASSET_NOT_FOUND",
                "message": "identity not resolved",
            },
        )
    return {
        "identity_id": identity_id,
        "cases": payload["cases"],
        "actions": payload["actions"],
        "queue": payload["queue"],
        "sla": payload["sla"],
        "identity_mode": payload["identity_mode"],
        "runtime_phase": payload["runtime_phase"],
        "engine": payload["engine"],
    }
