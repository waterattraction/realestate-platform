"""Stage classification from monitor overdue_days — deterministic rules."""

from datetime import date, datetime, timezone

from app.overdue.buckets import stage_from_overdue_days

__all__ = ["stage_from_overdue_days", "utc_today", "STAGE_SLA_DAYS", "STAGE_WEIGHT", "STAGE_ACTION"]

STAGE_SLA_DAYS: dict[str, int] = {
    "M0.5": 7,
    "M1": 5,
    "M1+": 1,
}

STAGE_WEIGHT: dict[str, int] = {
    "M0.5": 1,
    "M1": 2,
    "M1+": 4,
}

STAGE_ACTION: dict[str, str] = {
    "M0.5": "CALL",
    "M1": "NOTICE",
    "M1+": "ESCALATE",
}


def utc_today() -> date:
    return datetime.now(timezone.utc).date()
