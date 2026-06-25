"""Standardized timeline event shape for M3 Phase 0."""


def standard_event(
    *,
    event_id: str,
    event_type: str,
    occurred_at,
    source: str,
    correlation_id: str,
    recorded_at=None,
    source_ref: str | None = None,
    payload_summary: str | None = None,
) -> dict:
    event = {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "source": source,
        "correlation_id": correlation_id,
    }
    if recorded_at is not None:
        event["recorded_at"] = recorded_at
    if source_ref is not None:
        event["source_ref"] = source_ref
    if payload_summary is not None:
        event["payload_summary"] = payload_summary
    return event
