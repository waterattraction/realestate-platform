"""Single source of truth for M-level delinquency buckets and related SQL helpers.

Buckets (remaining > tolerance):
  M0    overdue_days <= 0          (green; includes negative days)
  M0_5  0 < overdue_days <= 15     (light green)
  M1    15 < overdue_days <= 30    (orange)
  M1_PLUS overdue_days > 30        (red)
  M0_PLUS = M0_5 ∪ M1 ∪ M1_PLUS

ES when remaining <= tolerance. overdue_days IS NULL ≠ M0.
"""

from __future__ import annotations

M0_MAX_DAYS = 0
M0_5_MIN_DAYS = 1
M0_5_MAX_DAYS = 15
M1_MIN_DAYS = 16
M1_MAX_DAYS = 30
M1_PLUS_MIN_DAYS = 31

# M0+ / 「逾期资产」：逾期天数 > 0
OVERDUE_ASSET_MIN_DAYS = 1

# Performing / 正常在贷上限（M0）
PERFORMING_MAX_DAYS = M0_MAX_DAYS

# Risk score thresholds (aligned with buckets)
RISK_SCORE_M0_MAX_DAYS = M0_MAX_DAYS
RISK_SCORE_M0_5_MAX_DAYS = M0_5_MAX_DAYS
RISK_SCORE_M1_MAX_DAYS = M1_MAX_DAYS
RISK_SCORE_M1_PLUS_MIN_DAYS = M1_PLUS_MIN_DAYS

# Legacy name aliases (imports / risk sync during transition)
M3_PLUS_MIN_DAYS = M1_PLUS_MIN_DAYS
RISK_SCORE_M3_PLUS_MIN_DAYS = M1_PLUS_MIN_DAYS

RECONCILIATION_TOLERANCE_DEFAULT = 0.01

DELINQUENCY_BUCKET_LABELS = {
    "ES": "ES（提前结清）",
    "M0": "M0",
    "M0_5": "M0.5",
    "M1": "M1",
    "M1_PLUS": "M1+",
}

DELINQUENCY_BUCKET_COLORS = {
    "ES": "#38bdf8",
    "M0": "#34d399",
    "M0_5": "#86efac",
    "M1": "#fb923c",
    "M1_PLUS": "#f87171",
}

# Unambiguous legacy filter codes only (bare M1 collides with new M1 — do not remap).
LEGACY_BUCKET_FILTER_ALIASES = {
    "M2": "M0_5",
    "M3": "M1",
    "M2_PLUS": "M0_PLUS",
    "M3_PLUS": "M1_PLUS",
}

CANONICAL_BUCKET_CODES = frozenset(
    {"ES", "M0", "M0_5", "M1", "M1_PLUS", "M0_PLUS"}
)


def normalize_delinquency_bucket_filter(code: str | None) -> str | None:
    """Map legacy filter codes to current codes; pass through canonical codes."""
    if code is None:
        return None
    raw = str(code).strip()
    if not raw:
        return None
    mapped = LEGACY_BUCKET_FILTER_ALIASES.get(raw, raw)
    return mapped


def normalize_delinquency_bucket_filters(
    codes: list[str] | None,
) -> list[str] | None:
    if not codes:
        return codes
    out: list[str] = []
    seen: set[str] = set()
    for c in codes:
        n = normalize_delinquency_bucket_filter(c)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def sql_days_not_null(overdue_days_expr: str) -> str:
    return f"({overdue_days_expr} IS NOT NULL)"


def sql_es_filter(
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    return f"({remaining_amount_expr} <= {tolerance_param})"


def sql_m0_filter(
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    return (
        f"({remaining_amount_expr} > {tolerance_param} "
        f"AND {sql_days_not_null(overdue_days_expr)} "
        f"AND {overdue_days_expr} <= {M0_MAX_DAYS})"
    )


def sql_m0_5_filter(
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    return (
        f"({remaining_amount_expr} > {tolerance_param} "
        f"AND {sql_days_not_null(overdue_days_expr)} "
        f"AND {overdue_days_expr} > {M0_MAX_DAYS} "
        f"AND {overdue_days_expr} <= {M0_5_MAX_DAYS})"
    )


def sql_m1_filter(
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    return (
        f"({remaining_amount_expr} > {tolerance_param} "
        f"AND {sql_days_not_null(overdue_days_expr)} "
        f"AND {overdue_days_expr} > {M0_5_MAX_DAYS} "
        f"AND {overdue_days_expr} <= {M1_MAX_DAYS})"
    )


def sql_m1_plus_filter(
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    return (
        f"({remaining_amount_expr} > {tolerance_param} "
        f"AND {sql_days_not_null(overdue_days_expr)} "
        f"AND {overdue_days_expr} > {M1_MAX_DAYS})"
    )


# Transition aliases
sql_m3_plus_filter = sql_m1_plus_filter
sql_m2_filter = sql_m0_5_filter
sql_m3_filter = sql_m1_filter


def sql_overdue_asset_filter(
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    """SQL fragment: M0+ only (excludes ES, M0)."""
    return (
        f"({remaining_amount_expr} > {tolerance_param} "
        f"AND {sql_days_not_null(overdue_days_expr)} "
        f"AND {overdue_days_expr} > {M0_MAX_DAYS})"
    )


def sql_m0_plus_filter(
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    return sql_overdue_asset_filter(
        overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param
    )


def sql_exposure_asset_filter(
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    return (
        f"({sql_es_filter(remaining_amount_expr, tolerance_param=tolerance_param)} "
        f"OR {sql_m0_filter(overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param)} "
        f"OR {sql_m0_5_filter(overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param)} "
        f"OR {sql_m1_filter(overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param)} "
        f"OR {sql_m1_plus_filter(overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param)})"
    )


def sql_custody_list_sort_priority(
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    """ORDER BY priority: M1+ first, then M1, M0.5, M0, ES, unknown."""
    od = overdue_days_expr
    return f"""CASE
                    WHEN {remaining_amount_expr} <= {tolerance_param} THEN 4
                    WHEN {od} IS NULL THEN 5
                    WHEN {od} > {M1_MAX_DAYS} THEN 0
                    WHEN {od} > {M0_5_MAX_DAYS} THEN 1
                    WHEN {od} > {M0_MAX_DAYS} THEN 2
                    WHEN {remaining_amount_expr} > {tolerance_param} THEN 3
                    ELSE 5
                END"""


def sql_risk_score_overdue_component(
    overdue_days_expr: str = "m.overdue_days",
    *,
    remaining_expr: str = "m.remaining_amount",
    tolerance_param: str = ":tolerance",
) -> str:
    return f"""CASE
                WHEN {remaining_expr} <= {tolerance_param} THEN 0
                WHEN {overdue_days_expr} IS NULL THEN 5
                WHEN {overdue_days_expr} > {M1_MAX_DAYS} THEN 50
                WHEN {overdue_days_expr} > {M0_5_MAX_DAYS} THEN 35
                WHEN {overdue_days_expr} > {M0_MAX_DAYS} THEN 20
                ELSE 5
            END"""


def sql_risk_payment_gap_component(
    overdue_days_expr: str = "m.overdue_days",
    *,
    remaining_expr: str = "m.remaining_amount",
    tolerance_param: str = ":tolerance",
) -> str:
    return f"""CASE
                WHEN {remaining_expr} <= {tolerance_param} THEN 0
                WHEN {overdue_days_expr} > {M0_MAX_DAYS} AND (
                    m.last_payment_date IS NULL
                    OR (m.data_date - m.last_payment_date) > 45
                ) THEN 20
                ELSE 0
            END"""


def calc_delinquency_bucket(
    overdue_days: int | None,
    remaining_amount: float,
    *,
    tolerance: float = RECONCILIATION_TOLERANCE_DEFAULT,
) -> str | None:
    """ES / M0 / M0_5 / M1 / M1_PLUS; None when days unknown (not ES)."""
    if remaining_amount <= tolerance:
        return "ES"
    if overdue_days is None:
        return None
    od = int(overdue_days)
    if od <= M0_MAX_DAYS:
        return "M0"
    if od <= M0_5_MAX_DAYS:
        return "M0_5"
    if od <= M1_MAX_DAYS:
        return "M1"
    return "M1_PLUS"


def calc_risk_level(
    overdue_days: int | None,
    remaining_amount: float,
    *,
    tolerance: float = RECONCILIATION_TOLERANCE_DEFAULT,
) -> str | None:
    return calc_delinquency_bucket(overdue_days, remaining_amount, tolerance=tolerance)


def delinquency_bucket(
    overdue_days: int | None,
    remaining_amount: float | None = None,
    *,
    tolerance: float = RECONCILIATION_TOLERANCE_DEFAULT,
) -> str | None:
    if remaining_amount is not None:
        return calc_delinquency_bucket(
            overdue_days, remaining_amount, tolerance=tolerance
        )
    if overdue_days is None:
        return None
    od = int(overdue_days)
    if od <= M0_MAX_DAYS:
        return "M0"
    if od <= M0_5_MAX_DAYS:
        return "M0_5"
    if od <= M1_MAX_DAYS:
        return "M1"
    return "M1_PLUS"


def stage_from_overdue_days(overdue_days: int | None) -> str | None:
    """Ops stage from overdue_days; None when not overdue (days <= 0 or unknown)."""
    if overdue_days is None:
        return None
    od = int(overdue_days)
    if od <= M0_MAX_DAYS:
        return None
    if od <= M0_5_MAX_DAYS:
        return "M0.5"
    if od <= M1_MAX_DAYS:
        return "M1"
    return "M1+"


def is_overdue_asset(
    overdue_days: int | None,
    remaining_amount: float,
    *,
    tolerance: float = RECONCILIATION_TOLERANCE_DEFAULT,
) -> bool:
    if remaining_amount <= tolerance:
        return False
    if overdue_days is None:
        return False
    return int(overdue_days) > M0_MAX_DAYS


def is_m1_plus_alert(overdue_days: int | None) -> bool:
    if overdue_days is None:
        return False
    return int(overdue_days) > M1_MAX_DAYS


# Transition alias
is_m3_plus_alert = is_m1_plus_alert


def is_payment_gap_risk(overdue_days: int | None) -> bool:
    if overdue_days is None:
        return False
    return int(overdue_days) > M0_MAX_DAYS


def matches_delinquency_bucket_filter(item_bucket: str | None, filter_bucket: str) -> bool:
    """Whether an asset's computed bucket matches a UI filter (incl. composite M0_PLUS)."""
    if not filter_bucket:
        return True
    fb = normalize_delinquency_bucket_filter(filter_bucket) or filter_bucket
    if fb == "M0_PLUS":
        return item_bucket in ("M0_5", "M1", "M1_PLUS")
    return item_bucket == fb


def sql_agg_delinquency_filter(
    filter_bucket: str,
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    """HAVING fragment for asset_code-aggregated monitor rows."""
    fb = normalize_delinquency_bucket_filter(filter_bucket) or filter_bucket
    if fb == "M0_PLUS":
        return sql_overdue_asset_filter(
            overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param
        )
    if fb == "ES":
        return sql_es_filter(remaining_amount_expr, tolerance_param=tolerance_param)
    if fb == "M0":
        return sql_m0_filter(
            overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param
        )
    if fb == "M0_5":
        return sql_m0_5_filter(
            overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param
        )
    if fb == "M1":
        return sql_m1_filter(
            overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param
        )
    if fb == "M1_PLUS":
        return sql_m1_plus_filter(
            overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param
        )
    return sql_overdue_asset_filter(
        overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param
    )


def sql_agg_delinquency_filter_any(
    filter_buckets: list[str] | None,
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    """HAVING：None/空=不过滤；多值=任一等级命中。"""
    normalized = normalize_delinquency_bucket_filters(filter_buckets)
    if not normalized:
        return "TRUE"
    if len(normalized) == 1:
        return sql_agg_delinquency_filter(
            normalized[0],
            overdue_days_expr,
            remaining_amount_expr,
            tolerance_param=tolerance_param,
        )
    parts = [
        f"({sql_agg_delinquency_filter(b, overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param)})"
        for b in normalized
    ]
    return "(" + " OR ".join(parts) + ")"


def matches_any_delinquency_bucket_filter(
    item_bucket: str | None, filter_buckets: list[str] | None
) -> bool:
    if not filter_buckets:
        return True
    normalized = normalize_delinquency_bucket_filters(filter_buckets)
    return any(
        matches_delinquency_bucket_filter(item_bucket, b) for b in (normalized or [])
    )
