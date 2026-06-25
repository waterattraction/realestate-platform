from html import escape


def fmt_money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"¥{value:,.2f}"


def fmt_delinquency_badge(bucket: str | None) -> str:
    from app.overdue.ui_constants import DELINQUENCY_BUCKET_COLORS, DELINQUENCY_BUCKET_LABELS

    if bucket is None:
        return '<span class="badge">正常</span>'
    label = DELINQUENCY_BUCKET_LABELS.get(bucket, bucket)
    color = DELINQUENCY_BUCKET_COLORS.get(bucket, "#94a3b8")
    return (
        f'<span class="badge" style="background: {color}22; color: {color}; '
        f'border-color: {color}55;">{escape(label)}</span>'
    )


def fmt_risk_badge(level: str | None) -> str:
    colors = {
        "A": "#22c55e",
        "B": "#38bdf8",
        "C": "#f59e0b",
        "D": "#f97316",
        "E": "#ef4444",
        "ES": "#22c55e",
    }
    if not level:
        return '<span class="badge unrated-badge">未评分</span>'
    color = colors.get(level, "#94a3b8")
    return (
        f'<span class="badge" style="background: {color}22; color: {color}; '
        f'border-color: {color}55;">{escape(level)}</span>'
    )


def fmt_check_result(passed: bool, label: str = "") -> str:
    if passed:
        return f'<span class="badge ok-badge">{escape(label)}通过</span>'
    return f'<span class="badge fail-badge">{escape(label)}异常</span>'
