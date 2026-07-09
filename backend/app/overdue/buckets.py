"""Single source of truth for M-level delinquency buckets and related SQL helpers."""

M1_MAX_DAYS = 35
M2_MIN_DAYS = 36
M2_MAX_DAYS = 63
M3_MIN_DAYS = 64
M3_MAX_DAYS = 91
M3_PLUS_MIN_DAYS = 92
OVERDUE_ASSET_MIN_DAYS = 36

# Backward-compatible alias
PERFORMING_MAX_DAYS = M1_MAX_DAYS

# Risk score / sort tier thresholds (> N means bucket starts at N+1)
RISK_SCORE_M1_MAX_DAYS = M1_MAX_DAYS
RISK_SCORE_M2_MAX_DAYS = M2_MAX_DAYS
RISK_SCORE_M3_MAX_DAYS = M3_MAX_DAYS
RISK_SCORE_M3_PLUS_MIN_DAYS = M3_PLUS_MIN_DAYS

RECONCILIATION_TOLERANCE_DEFAULT = 0.01

DELINQUENCY_BUCKET_LABELS = {
    "ES": "ES（提前结清）",
    "M1": "M1",
    "M2": "M2",
    "M3": "M3",
    "M3_PLUS": "M3+",
}

DELINQUENCY_BUCKET_COLORS = {
    "ES": "#38bdf8",
    "M1": "#34d399",
    "M2": "#fbbf24",
    "M3": "#fbbf24",
    "M3_PLUS": "#f87171",
}


def _coalesce_overdue_days(overdue_days_expr: str) -> str:
    return f"COALESCE({overdue_days_expr}, 0)"


def sql_es_filter(
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    return f"({remaining_amount_expr} <= {tolerance_param})"


def sql_m1_filter(
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    od = _coalesce_overdue_days(overdue_days_expr)
    return (
        f"({remaining_amount_expr} > {tolerance_param} "
        f"AND {od} <= {M1_MAX_DAYS})"
    )


def sql_m2_filter(
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    od = _coalesce_overdue_days(overdue_days_expr)
    return (
        f"({remaining_amount_expr} > {tolerance_param} "
        f"AND {od} BETWEEN {M2_MIN_DAYS} AND {M2_MAX_DAYS})"
    )


def sql_m3_filter(
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    od = _coalesce_overdue_days(overdue_days_expr)
    return (
        f"({remaining_amount_expr} > {tolerance_param} "
        f"AND {od} BETWEEN {M3_MIN_DAYS} AND {M3_MAX_DAYS})"
    )


def sql_m3_plus_filter(
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    od = _coalesce_overdue_days(overdue_days_expr)
    return (
        f"({remaining_amount_expr} > {tolerance_param} "
        f"AND {od} >= {M3_PLUS_MIN_DAYS})"
    )


def sql_overdue_asset_filter(
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    """SQL fragment: M2/M3/M3+ only (excludes ES, M1)."""
    od = _coalesce_overdue_days(overdue_days_expr)
    return (
        f"({remaining_amount_expr} > {tolerance_param} "
        f"AND {od} >= {OVERDUE_ASSET_MIN_DAYS})"
    )


def sql_exposure_asset_filter(
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    return (
        f"({sql_es_filter(remaining_amount_expr, tolerance_param=tolerance_param)} "
        f"OR {sql_m1_filter(overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param)} "
        f"OR {sql_m2_filter(overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param)} "
        f"OR {sql_m3_filter(overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param)} "
        f"OR {sql_m3_plus_filter(overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param)})"
    )


def sql_custody_list_sort_priority(
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    """ORDER BY priority: M3+ first, then M3, M2, M1, ES."""
    od = _coalesce_overdue_days(overdue_days_expr)
    return f"""CASE
                    WHEN {remaining_amount_expr} <= {tolerance_param} THEN 4
                    WHEN {od} >= {M3_PLUS_MIN_DAYS} THEN 0
                    WHEN {od} > {M2_MAX_DAYS} THEN 1
                    WHEN {od} > {M1_MAX_DAYS} THEN 2
                    WHEN {remaining_amount_expr} > {tolerance_param} THEN 3
                    ELSE 5
                END"""


def sql_risk_score_overdue_component(
    overdue_days_expr: str = "COALESCE(m.overdue_days, 0)",
    *,
    remaining_expr: str = "m.remaining_amount",
    tolerance_param: str = ":tolerance",
) -> str:
    return f"""CASE
                WHEN {remaining_expr} <= {tolerance_param} THEN 0
                WHEN {overdue_days_expr} >= {M3_PLUS_MIN_DAYS} THEN 50
                WHEN {overdue_days_expr} > {M2_MAX_DAYS} THEN 35
                WHEN {overdue_days_expr} > {M1_MAX_DAYS} THEN 20
                ELSE 5
            END"""


def sql_risk_payment_gap_component(
    overdue_days_expr: str = "COALESCE(m.overdue_days, 0)",
    *,
    remaining_expr: str = "m.remaining_amount",
    tolerance_param: str = ":tolerance",
) -> str:
    return f"""CASE
                WHEN {remaining_expr} <= {tolerance_param} THEN 0
                WHEN {overdue_days_expr} > {M1_MAX_DAYS} AND (
                    m.last_payment_date IS NULL
                    OR (m.data_date - m.last_payment_date) > 45
                ) THEN 20
                ELSE 0
            END"""


def calc_delinquency_bucket(
    overdue_days: int,
    remaining_amount: float,
    *,
    tolerance: float = RECONCILIATION_TOLERANCE_DEFAULT,
) -> str:
    """ES / M1 / M2 / M3 / M3_PLUS; M1 includes overdue_days=0 when balance > 0."""
    if remaining_amount <= tolerance:
        return "ES"
    od = max(0, int(overdue_days))
    if od <= M1_MAX_DAYS:
        return "M1"
    if od <= M2_MAX_DAYS:
        return "M2"
    if od <= M3_MAX_DAYS:
        return "M3"
    return "M3_PLUS"


def calc_risk_level(
    overdue_days: int,
    remaining_amount: float,
    *,
    tolerance: float = RECONCILIATION_TOLERANCE_DEFAULT,
) -> str:
    return calc_delinquency_bucket(overdue_days, remaining_amount, tolerance=tolerance)


def delinquency_bucket(
    overdue_days: int,
    remaining_amount: float | None = None,
    *,
    tolerance: float = RECONCILIATION_TOLERANCE_DEFAULT,
) -> str | None:
    if remaining_amount is not None:
        return calc_delinquency_bucket(overdue_days, remaining_amount, tolerance=tolerance)
    od = max(0, int(overdue_days))
    if od <= M1_MAX_DAYS:
        return "M1"
    if od <= M2_MAX_DAYS:
        return "M2"
    if od <= M3_MAX_DAYS:
        return "M3"
    return "M3_PLUS"


def stage_from_overdue_days(overdue_days: int) -> str | None:
    """Ops stage from overdue_days; None when not yet overdue (<=0)."""
    if overdue_days <= 0:
        return None
    od = int(overdue_days)
    if od <= M1_MAX_DAYS:
        return "M1"
    if od <= M2_MAX_DAYS:
        return "M2"
    if od <= M3_MAX_DAYS:
        return "M3"
    return "M3+"


def is_overdue_asset(
    overdue_days: int | None,
    remaining_amount: float,
    *,
    tolerance: float = RECONCILIATION_TOLERANCE_DEFAULT,
) -> bool:
    if remaining_amount <= tolerance:
        return False
    od = 0 if overdue_days is None else int(overdue_days)
    return od >= OVERDUE_ASSET_MIN_DAYS


def is_m3_plus_alert(overdue_days: int | None) -> bool:
    od = 0 if overdue_days is None else int(overdue_days)
    return od >= M3_PLUS_MIN_DAYS


def is_payment_gap_risk(overdue_days: int | None) -> bool:
    od = 0 if overdue_days is None else int(overdue_days)
    return od > M1_MAX_DAYS


def matches_delinquency_bucket_filter(item_bucket: str, filter_bucket: str) -> bool:
    """Whether an asset's computed bucket matches a UI filter (incl. composite M2_PLUS)."""
    if not filter_bucket:
        return True
    if filter_bucket == "M2_PLUS":
        return item_bucket in ("M2", "M3", "M3_PLUS")
    return item_bucket == filter_bucket


def sql_agg_delinquency_filter(
    filter_bucket: str,
    overdue_days_expr: str,
    remaining_amount_expr: str,
    *,
    tolerance_param: str = ":tolerance",
) -> str:
    """HAVING fragment for asset_code-aggregated monitor rows."""
    if filter_bucket == "M2_PLUS":
        return sql_overdue_asset_filter(
            overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param
        )
    if filter_bucket == "ES":
        return sql_es_filter(remaining_amount_expr, tolerance_param=tolerance_param)
    if filter_bucket == "M1":
        return sql_m1_filter(
            overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param
        )
    if filter_bucket == "M2":
        return sql_m2_filter(
            overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param
        )
    if filter_bucket == "M3":
        return sql_m3_filter(
            overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param
        )
    if filter_bucket == "M3_PLUS":
        return sql_m3_plus_filter(
            overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param
        )
    return sql_overdue_asset_filter(
        overdue_days_expr, remaining_amount_expr, tolerance_param=tolerance_param
    )
