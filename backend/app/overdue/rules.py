"""Stage classification from monitor overdue_days — deterministic rules."""

from datetime import date, datetime, timezone

from app.overdue.buckets import stage_from_overdue_days

__all__ = ["stage_from_overdue_days", "utc_today", "STAGE_SLA_DAYS", "STAGE_WEIGHT", "STAGE_ACTION"]

STAGE_SLA_DAYS: dict[str, int] = {
    "M1": 7,
    "M2": 5,
    "M3": 3,
    "M3+": 1,
}

STAGE_WEIGHT: dict[str, int] = {
    "M1": 1,
    "M2": 2,
    "M3": 3,
    "M3+": 4,
}

STAGE_ACTION: dict[str, str] = {
    "M1": "CALL",
    "M2": "NOTICE",
    "M3": "VISIT",
    "M3+": "ESCALATE",
}


def utc_today() -> date:
    return datetime.now(timezone.utc).date()
