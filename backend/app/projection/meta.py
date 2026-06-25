from datetime import datetime, timezone

from app.projection.constants import PROJECTION_VERSION, RUNTIME_PHASE


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_meta(
    *,
    builder_version: str,
    snapshot_version: str | None = None,
    timeline_version: str | None = None,
    health: str = "fresh",
) -> dict:
    meta = {
        "built_at": utc_now_iso(),
        "projection_version": PROJECTION_VERSION,
        "builder_version": builder_version,
        "health": health,
        "runtime_phase": RUNTIME_PHASE,
    }
    if snapshot_version is not None:
        meta["snapshot_version"] = snapshot_version
    if timeline_version is not None:
        meta["timeline_version"] = timeline_version
    return meta


def wrap_projection(data: dict, meta: dict) -> dict:
    """All Phase-0 builders return { data, meta }."""
    return {"data": data, "meta": meta}
