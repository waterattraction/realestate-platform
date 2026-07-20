"""Overdue-days formula helpers (aligned with PostgreSQL ``date + interval '1 month'``)."""

from __future__ import annotations

import calendar
from datetime import date


def add_calendar_months(d: date, months: int = 1) -> date:
    """Month-end aligned: 2026-01-31 + 1 month → 2026-02-28 (or 29)."""
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def compute_overdue_days(as_of: date, anchor: date) -> int:
    """重算日 −（锚点日的下月同日）。可为负。"""
    due = add_calendar_months(anchor, 1)
    return (as_of - due).days


# SQL expression: as_of_param - (anchor_expr + 1 month)::date
SQL_OVERDUE_DAYS_EXPR = "(CAST(:as_of AS date) - ({anchor} + INTERVAL '1 month')::date)"
