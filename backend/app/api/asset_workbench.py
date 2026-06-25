from fastapi import APIRouter, HTTPException

from app.db import get_engine
from app.projection.constants import IDENTITY_MODE, RUNTIME_PHASE
from app.service.asset_service import build_asset_application_service

router = APIRouter(tags=["asset-workbench"])

_service = build_asset_application_service(get_engine())


def _workbench_payload(identity_id: int) -> dict:
    header = _service.fetch_header(identity_id)
    if header is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "ASSET_NOT_FOUND",
                "message": "identity not resolved",
            },
        )
    return {
        "identity_id": identity_id,
        "identity_mode": IDENTITY_MODE,
        "runtime_phase": RUNTIME_PHASE,
        "header": header,
        "snapshot": _service.fetch_snapshot(identity_id),
        "timeline": _service.fetch_timeline(identity_id),
        "operations": _service.fetch_operations(identity_id),
    }


@router.get("/asset-workbench/{identity_id}")
def get_asset_workbench(identity_id: int) -> dict:
    """
    M3 Phase 0 MVP runtime — orchestration only.
    identity_id = trust_product_issuance_asset_records.id (SURROGATE_PHASE_0).
    """
    return _workbench_payload(identity_id)


@router.post("/asset-workbench/{identity_id}/invalidate")
def invalidate_asset_workbench(identity_id: int) -> dict:
    """
    M3.3 A-2: invalidate projection cache only (bump cache_inv_version).
    No DB writes; does not rebuild — next GET will miss cache and rebuild on fetch.
    """
    result = _service.invalidate_projection(identity_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "ASSET_NOT_FOUND",
                "message": "identity not resolved",
            },
        )
    return {
        "identity_id": identity_id,
        "identity_mode": IDENTITY_MODE,
        "runtime_phase": RUNTIME_PHASE,
        "invalidate": result,
    }


@router.post("/asset-workbench/{identity_id}/rebuild")
def rebuild_asset_workbench(identity_id: int) -> dict:
    """
    M3.3 A-1: rebuild all projections via Registry (cache invalidate + full build).
    Returns rebuild audit + fresh workbench payload.
    """
    rebuild = _service.rebuild_projection(identity_id)
    if rebuild is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "ASSET_NOT_FOUND",
                "message": "identity not resolved",
            },
        )
    return {
        "identity_id": identity_id,
        "identity_mode": IDENTITY_MODE,
        "runtime_phase": RUNTIME_PHASE,
        "rebuild": rebuild,
        "workbench": _workbench_payload(identity_id),
    }
