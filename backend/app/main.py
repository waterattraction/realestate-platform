import os
import re
import uuid
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo
from html import escape
from typing import Annotated
from urllib.parse import quote, urlencode

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import create_engine, text

from app import auth
from app import auth_html
from app.api import asset_workbench
from app.api import overdue_ops
from app.api import overdue_workbench
from app.api import followups
from app.api.spatial import build_spatial_router
from app import assetinfo_html
from app import assetinfo_pipeline
from app import assetinfo_upload
from app import asset_swap
from app import asset_swap_html
from app import disclosure
from app import disclosure_html
from app import issuance_html
from app import issuance_upload
from app import query_utils
from app import repayment_analytics
from app import repayment_analytics_html
from app import trust_products as trust_products_svc
from app import trust_products_html
from app import risk_hub
from app.overdue import buckets as overdue_buckets
from app.overdue.buckets import (
    DELINQUENCY_BUCKET_COLORS,
    DELINQUENCY_BUCKET_LABELS,
    M0_MAX_DAYS as PERFORMING_MAX_DAYS,
    OVERDUE_ASSET_MIN_DAYS,
    RECONCILIATION_TOLERANCE_DEFAULT,
    calc_delinquency_bucket as calc_risk_level,
    delinquency_bucket,
    is_overdue_asset,
    normalize_delinquency_bucket_filters,
    sql_es_filter as sql_es_asset_filter,
    sql_exposure_asset_filter,
    sql_m0_filter as sql_m0_asset_filter,
    sql_m0_5_filter as sql_m0_5_asset_filter,
    sql_m1_filter as sql_m1_asset_filter,
    sql_m1_plus_filter as sql_m1_plus_asset_filter,
    sql_overdue_asset_filter,
)
from app.ui_css import BTN_CSS, DASHBOARD_BODY_CSS, PAGE_CHROME_CSS, STANDARD_HEADER_CSS, TABLE_SCROLL_CSS

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)

app = FastAPI(title="Real Estate Securitization Platform")

app.include_router(asset_workbench.router)
app.include_router(overdue_ops.router)
app.include_router(overdue_workbench.router)
app.include_router(followups.router)

get_current_user = auth.make_current_user_dependency(engine)
get_page_user = auth.make_page_user_dependency(engine)
app.include_router(build_spatial_router(engine, get_page_user, get_current_user))


def _safe_next_path(next_url: str) -> str:
    if not next_url or not next_url.startswith("/") or next_url.startswith("//"):
        return "/"
    return next_url


@app.exception_handler(auth.LoginRedirect)
async def handle_login_redirect(_request: Request, exc: auth.LoginRedirect):
    return RedirectResponse(url=f"/login?next={quote(exc.next_path)}", status_code=302)


@app.on_event("startup")
def on_startup():
    auth.init_auth(engine)

STATUS_LABELS = {
    "pending": "待激活",
    "active": "生效中",
    "draft": "草稿",
    "in_progress": "进行中",
    "completed": "已完成",
    "raising": "募集中",
    "confirmed": "已确认",
}

FOLLOWUP_STATUS_LABELS = {
    "open": "待跟进",
    "in_progress": "跟进中",
    "settled_week": "本周结算",
    "resolved": "已解决",
    "closed": "已关闭",
}

TRIGGER_SOURCE_LABELS = {
    "system": "系统自检",
    "trust": "信托要求",
}

TRUST_MARKER_OPTIONS = [
    "无标记",
    "已关注",
    "重点关注",
]
INTERNAL_STATUS_OPTIONS = ["正常", "待跟进", "本周结算"]
TRUST_MARKER_DEFAULT = "无标记"
INTERNAL_STATUS_DEFAULT = "正常"
FOLLOWUP_CASE_CATEGORIES = [
    "轻度逾期",
    "重度逾期",
    "回购",
    "置换",
    "潜在风险",
]

ISSUANCE_CITY_UNKNOWN = "未知"

PORTFOLIO_LIST_COLUMNS: list[tuple[str | None, str, str | None]] = [
    ("asset_code", "资产主编号", "text"),
    ("custody_asset_code", "托管房源号", "text"),
    ("trust_product_name", "信托产品", "text"),
    ("city", "城市", "text"),
    ("delinquency_bucket", "等级", "text"),
    ("overdue_sort", "逾期天数", "text"),
    ("last_payment_date", "最后回款日", "text"),
    ("trust_marker", "信托标记", "text"),
    ("internal_status", "内部状态", "text"),
    ("data_date", "数据日期", "text"),
    ("initial_transfer_amount", "初始受让金额", "number"),
    ("repaid_amount", "已还款金额", "number"),
    ("remaining_amount", "剩余还款金额", "number"),
]
PORTFOLIO_COL_COUNT = len(PORTFOLIO_LIST_COLUMNS)
PORTFOLIO_AMOUNT_COL_COUNT = 3
PORTFOLIO_LABEL_COL_COUNT = PORTFOLIO_COL_COUNT - PORTFOLIO_AMOUNT_COL_COUNT

CUSTODY_LIST_HEADERS = [label for _, label, _ in PORTFOLIO_LIST_COLUMNS]

RECONCILIATION_TOLERANCE = RECONCILIATION_TOLERANCE_DEFAULT


def fmt_money(value: float) -> str:
    return f"¥{value:,.2f}"


def fmt_recon_money(value: float, *, passed: bool) -> str:
    css = "num ok" if passed else "num warn"
    return f'<span class="{css}">{fmt_money(value)}</span>'


def fmt_cross_check_badge(
    passed: bool,
    *,
    pass_label: str = "通过",
    fail_label: str = "不通过",
) -> str:
    if passed:
        return f'<span class="badge ok-badge">{escape(pass_label)}</span>'
    return f'<span class="badge fail-badge">{escape(fail_label)}</span>'


def fmt_rate(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.2f}%"


def fmt_status(status: str) -> str:
    label = STATUS_LABELS.get(status, status)
    return f'<span class="badge">{escape(label)}</span>'


def build_overdue_kpi_metrics(
    es: int,
    m0: int,
    m0_5: int,
    m1: int,
    m1_plus: int,
) -> dict:
    """exposure_total = ES+M0+M0.5+M1+M1+；overdue_total = M0+ (= M0.5+M1+M1+)。"""
    exposure_total = es + m0 + m0_5 + m1 + m1_plus
    overdue_total = m0_5 + m1 + m1_plus
    return {
        "exposure_total": exposure_total,
        "overdue_total": overdue_total,
        "es_count": es,
        "breakdown": {
            "ES": es,
            "M0": m0,
            "M0.5": m0_5,
            "M1": m1,
            "M1+": m1_plus,
        },
    }


def _zero_overdue_kpi_amounts() -> dict:
    pair = {"remaining_amount": 0.0, "initial_transfer_amount": 0.0}
    return {
        "exposure": dict(pair),
        "ES": {"repaid_amount": 0.0, "initial_transfer_amount": 0.0},
        "M0": dict(pair),
        "overdue": dict(pair),
        "M0_5": dict(pair),
        "M1": dict(pair),
        "M1_PLUS": dict(pair),
    }


def _overdue_kpi_amounts_from_row(row) -> dict:
    def _f(name: str) -> float:
        return float(getattr(row, name, 0) or 0)

    return {
        "exposure": {
            "remaining_amount": _f("exposure_remaining_sum"),
            "initial_transfer_amount": _f("exposure_initial_sum"),
        },
        "ES": {
            "repaid_amount": _f("es_repaid_sum"),
            "initial_transfer_amount": _f("es_initial_sum"),
        },
        "M0": {
            "remaining_amount": _f("m0_remaining_sum"),
            "initial_transfer_amount": _f("m0_initial_sum"),
        },
        "overdue": {
            "remaining_amount": _f("overdue_remaining_sum"),
            "initial_transfer_amount": _f("overdue_initial_sum"),
        },
        "M0_5": {
            "remaining_amount": _f("m0_5_remaining_sum"),
            "initial_transfer_amount": _f("m0_5_initial_sum"),
        },
        "M1": {
            "remaining_amount": _f("m1_remaining_sum"),
            "initial_transfer_amount": _f("m1_initial_sum"),
        },
        "M1_PLUS": {
            "remaining_amount": _f("m1_plus_remaining_sum"),
            "initial_transfer_amount": _f("m1_plus_initial_sum"),
        },
    }


def _fmt_overdue_card_amounts(amounts: dict, *, use_repaid: bool = False) -> str:
    initial = float(amounts.get("initial_transfer_amount") or 0)
    if use_repaid:
        repaid = float(amounts.get("repaid_amount") or 0)
        return f"已还 {fmt_money(repaid)} / 初始 {fmt_money(initial)}"
    remaining = float(amounts.get("remaining_amount") or 0)
    return f"剩余 {fmt_money(remaining)} / 初始 {fmt_money(initial)}"


def _render_overdue_bucket_kpi_card(
    label: str,
    count: int,
    amounts: dict,
    *,
    value_css: str = "",
    hint: str = "",
    use_repaid: bool = False,
) -> str:
    css_cls = f" {value_css}" if value_css else ""
    amounts_html = _fmt_overdue_card_amounts(amounts, use_repaid=use_repaid)
    hint_html = f'<div class="card-hint">{escape(hint)}</div>' if hint else ""
    return f"""
            <div class="card">
                <div class="card-label">{escape(label)}</div>
                <div class="card-value{css_cls}">{count}</div>
                <div class="card-amounts">{amounts_html}</div>
                {hint_html}
            </div>
        """


def fmt_delinquency_badge(bucket: str | None) -> str:
    if bucket is None:
        return '<span class="badge">—</span>'
    label = DELINQUENCY_BUCKET_LABELS.get(bucket, bucket)
    color = DELINQUENCY_BUCKET_COLORS.get(bucket, "#94a3b8")
    return (
        f'<span class="badge" style="background: {color}22; color: {color}; '
        f'border-color: {color}55;">{escape(label)}</span>'
    )


def _format_display_timestamp(value: str | None) -> str:
    """展示用时间：统一转为北京/上海时间 YYYY-MM-DD HH:MM。"""
    if not value:
        return "—"
    text_val = str(value).strip()
    if not text_val:
        return "—"
    try:
        from datetime import timezone

        dt = datetime.fromisoformat(text_val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text_val[:16].replace("T", " ")


def _render_overdue_header_meta(overview: dict) -> str:
    snapshot = escape(str(overview.get("data_date") or "—"))
    as_of = overview.get("overdue_days_as_of")
    last_recalc = _format_display_timestamp(overview.get("last_recalculated_at"))
    as_of_html = (
        f'<strong>逾期天数截至：{escape(as_of)}</strong>'
        if as_of
        else '<span class="meta-warn">逾期天数截至：—（请先点击「重新计算逾期天数」）</span>'
    )
    stale_note = ""
    if overview.get("overdue_recalc_stale") and as_of:
        stale_note = (
            '<br><span class="meta-hint">提示：部分监控记录尚未写入重算基准日，'
            "建议再次执行重算。</span>"
        )
    elif overview.get("overdue_recalc_stale") and not as_of:
        stale_note = (
            '<br><span class="meta-hint">提示：当前逾期天数可能仍按监控快照日导入时计算，'
            "与快照日不同，请以重算后「逾期天数截至」为准。</span>"
        )
    multi_product_note = ""
    selected_ids = overview.get("trust_product_ids")
    if selected_ids and len(selected_ids) > 1:
        multi_product_note = (
            '<br><span class="meta-hint">已选多个信托产品，各产品监控快照日可能不一致；'
            "重算时按各产品最新快照日分别更新。</span>"
        )
    return f"""
        <p>
            监控快照日期：<strong>{snapshot}</strong>
            · {as_of_html}
            · 最近重算：{escape(last_recalc)}
            <br><span class="meta-hint">监控快照日期为资产表数据截止日；逾期天数 = 重算日 −（最后付款日或最早发行日的下月同日）。</span>
            {stale_note}
            {multi_product_note}
            · <a href="/overdue/workbench">逾期工作台 →</a>
        </p>
    """


def _monitor_custody_ctes(monitor_filter: str) -> str:
    """按托管房源聚合 monitor 全量行（不去重，使用 SUM/MAX/COUNT）。"""
    return f"""
        monitor_enriched AS (
            SELECT
                m.id,
                m.trust_product_id,
                m.trust_asset_id,
                m.data_date,
                m.source_sheet_name,
                m.initial_transfer_amount,
                m.repaid_amount,
                m.remaining_amount,
                m.overdue_days,
                m.last_payment_date,
                m.max_payment_date,
                m.asset_code,
                COALESCE(m.custody_asset_code, ta.custody_asset_code, m.asset_code) AS custody_asset_code,
                COALESCE(m.source_asset_code, ta.source_asset_code, m.asset_code) AS source_asset_code
            FROM trust_asset_monitor_records m
            INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
            WHERE {monitor_filter}
        ),
        monitor_custody AS (
            SELECT
                d.trust_product_id,
                d.data_date,
                d.custody_asset_code,
                MIN(d.asset_code) AS asset_code,
                COUNT(*) AS row_count,
                COUNT(DISTINCT d.source_asset_code) AS source_asset_count,
                SUM(d.initial_transfer_amount) AS initial_transfer_amount,
                SUM(d.repaid_amount) AS repaid_amount,
                SUM(d.remaining_amount) AS remaining_amount,
                CASE
                    WHEN SUM(d.remaining_amount) <= {RECONCILIATION_TOLERANCE}
                    THEN NULL
                    ELSE MAX(d.overdue_days)
                END AS overdue_days,
                MAX(d.last_payment_date) AS last_payment_date,
                MAX(d.max_payment_date) AS max_payment_date,
                array_agg(DISTINCT d.source_asset_code ORDER BY d.source_asset_code) AS source_asset_codes
            FROM monitor_enriched d
            GROUP BY d.trust_product_id, d.data_date, d.custody_asset_code
        )
    """


def _custody_has_follow_up_sql() -> str:
    return """
        EXISTS (
            SELECT 1
            FROM trust_overdue_followup_cases c
            WHERE c.trust_product_id = mc.trust_product_id
              AND c.asset_code = mc.asset_code
              AND c.status IN ('open', 'in_progress')
        )
    """


def _custody_followup_count_sql() -> str:
    return """
        (
            SELECT COUNT(e.id)
            FROM trust_overdue_followup_entries e
            INNER JOIN trust_overdue_followup_cases c ON c.id = e.case_id
            WHERE c.trust_product_id = mc.trust_product_id
              AND c.asset_code = mc.asset_code
        )
    """


def _custody_marks_join_sql() -> str:
    """标记/内部状态按资产主编号，与监控 data_date 无关。"""
    return """
        LEFT JOIN trust_asset_trust_marks tm
            ON tm.trust_product_id = mc.trust_product_id
           AND tm.asset_code = mc.asset_code
    """


def _sort_custody_items_in_bucket(items: list, bucket: str) -> list:
    """Tab 内显式次级键：天数/回款日 DESC → 资产主编号 ASC（托管号仅防抖）。

    先按主编号升序，再按主排序键降序（稳定排序保留同天数下的主编号序）。
    """
    tied = sorted(
        items,
        key=lambda it: (
            str(it.get("asset_code") or ""),
            str(it.get("custody_asset_code") or ""),
        ),
    )
    if bucket == "ES":
        return sorted(
            tied,
            key=lambda it: it.get("last_payment_date") or "",
            reverse=True,
        )
    return sorted(
        tied,
        key=lambda it: (
            it.get("overdue_days") if it.get("overdue_days") is not None else -1
        ),
        reverse=True,
    )


def _match_internal_status_filter(got: str, wants: list[str] | None) -> bool:
    if not wants:
        return True
    got_s = str(got or "")
    for want in wants:
        if want == "正常" and got_s == "正常":
            return True
        if want == "待跟进" and got_s.startswith("待跟进"):
            return True
        if want == "本周结算" and got_s.startswith("本周结算"):
            return True
        if got_s == want:
            return True
    return False


def _apply_custody_list_filters(item: dict, filters: dict | None) -> bool:
    if not filters:
        return True
    trust_product_ids = filters.get("trust_product_ids")
    if trust_product_ids is not None:
        if item["trust_product_id"] not in trust_product_ids:
            return False
    buckets = filters.get("delinquency_buckets")
    if buckets is None and filters.get("delinquency_bucket"):
        buckets = [filters["delinquency_bucket"]]
    if buckets:
        from app.overdue.buckets import matches_delinquency_bucket_filter

        if not any(
            matches_delinquency_bucket_filter(item["delinquency_bucket"], b)
            for b in buckets
        ):
            return False
    markers = filters.get("trust_markers")
    if markers is None and filters.get("trust_marker"):
        markers = [filters["trust_marker"]]
    if markers and item.get("trust_marker") not in markers:
        return False
    statuses = filters.get("internal_statuses")
    if statuses is None and filters.get("internal_status"):
        statuses = [filters["internal_status"]]
    if not _match_internal_status_filter(item.get("internal_status") or "", statuses):
        return False
    has_followup = filters.get("has_followup")
    if has_followup == "yes" and int(item.get("followup_count") or 0) <= 0:
        return False
    if has_followup == "no" and int(item.get("followup_count") or 0) > 0:
        return False
    asset_q = (filters.get("asset_code") or "").strip().lower()
    if asset_q and asset_q not in (item.get("asset_code") or "").lower():
        return False
    custody_q = (filters.get("custody_asset_code") or "").strip().lower()
    if custody_q and custody_q not in item["custody_asset_code"].lower():
        return False
    cities = filters.get("cities")
    if cities is None and filters.get("city"):
        cities = [filters["city"]]
    if cities and item.get("city_filter") not in cities:
        return False
    return True


def _issuance_city_lateral_join_sql() -> str:
    return """
            LEFT JOIN LATERAL (
                SELECT i.city
                FROM trust_product_issuance_asset_records i
                WHERE i.trust_product_id = mc.trust_product_id
                  AND (
                      i.custody_asset_code = mc.custody_asset_code
                      OR split_part(i.custody_asset_code, '-', 1) = mc.asset_code
                  )
                ORDER BY i.issue_date DESC NULLS LAST, i.id DESC
                LIMIT 1
            ) iss ON TRUE
    """


def _normalize_portfolio_city(raw) -> tuple[str, str]:
    if raw is None:
        return "—", ISSUANCE_CITY_UNKNOWN
    text = str(raw).strip()
    if not text:
        return "—", ISSUANCE_CITY_UNKNOWN
    return text, text


def fetch_overdue_issuance_cities(conn, trust_product_ids: list[int] | None = None) -> list[str]:
    sql = """
        SELECT DISTINCT COALESCE(NULLIF(TRIM(city), ''), :unknown) AS city
        FROM trust_product_issuance_asset_records
        WHERE 1 = 1
    """
    params: dict = {"unknown": ISSUANCE_CITY_UNKNOWN}
    product_sql, product_params = query_utils.sql_in_int_column(
        "trust_product_id", trust_product_ids, param_prefix="icity"
    )
    sql += product_sql
    params.update(product_params)
    sql += " ORDER BY city"
    rows = conn.execute(text(sql), params)
    return [str(row.city) for row in rows]


def _bucket_amount_totals(items: list) -> dict:
    return {
        "count": len(items),
        "initial_transfer_amount": sum(float(i["initial_transfer_amount"]) for i in items),
        "repaid_amount": sum(float(i["repaid_amount"]) for i in items),
        "remaining_amount": sum(float(i["remaining_amount"]) for i in items),
    }


def _portfolio_city_fields(row) -> dict:
    display, filter_key = _normalize_portfolio_city(getattr(row, "issuance_city", None))
    return {"city": display, "city_filter": filter_key}


def is_es_closed(remaining_amount: float, *, tolerance: float = RECONCILIATION_TOLERANCE) -> bool:
    return remaining_amount <= tolerance


def _settlement_date_from_row(row) -> str | None:
    """提前结清日期：优先 max_payment_date，否则 last_payment_date."""
    if getattr(row, "max_payment_date", None):
        return str(row.max_payment_date)
    raw = getattr(row, "raw_last_payment_date", None) or getattr(row, "last_payment_date", None)
    if raw:
        return str(raw)
    return None


def _custody_item_from_row(row) -> dict:
    remaining = float(row.remaining_amount)
    source_codes = list(row.source_asset_codes) if row.source_asset_codes else []
    asset_code = getattr(row, "asset_code", None) or row.custody_asset_code
    settlement_date = _settlement_date_from_row(row)
    raw_last_payment = (
        str(row.raw_last_payment_date)
        if getattr(row, "raw_last_payment_date", None)
        else None
    )
    trust_marker = getattr(row, "trust_marker", None) or TRUST_MARKER_DEFAULT
    internal_status = getattr(row, "internal_status", None) or INTERNAL_STATUS_DEFAULT
    followup_count = int(getattr(row, "followup_count", 0) or 0)
    city_fields = _portfolio_city_fields(row)
    base = {
        "trust_product_id": row.trust_product_id,
        "trust_product_name": row.trust_product_name,
        "data_date": str(row.data_date),
        "custody_asset_code": row.custody_asset_code,
        "asset_code": asset_code,
        "source_asset_count": int(row.source_asset_count),
        "source_asset_codes": source_codes,
        "initial_transfer_amount": float(row.initial_transfer_amount),
        "repaid_amount": float(row.repaid_amount),
        "remaining_amount": remaining,
        "trust_marker": trust_marker,
        "internal_status": internal_status,
        "followup_count": followup_count,
        "has_follow_up": bool(getattr(row, "has_follow_up", False)),
        **city_fields,
    }
    if is_es_closed(remaining):
        settlement = settlement_date
        return {
            **base,
            "risk_level": "ES",
            "delinquency_bucket": "ES",
            "status": "closed",
            "overdue_days": None,
            "last_payment_date": settlement,
            "settlement_date": settlement,
            "overdue_sort": settlement or "",
        }
    raw_od = row.overdue_days
    overdue_days = int(raw_od) if raw_od is not None else None
    bucket = calc_risk_level(overdue_days, remaining)
    if bucket == "M0":
        status = "performing"
    elif bucket is None:
        status = "unknown"
    else:
        status = "overdue"
    if overdue_days is None:
        overdue_sort = ""
    else:
        overdue_sort = f"{overdue_days:+07d}"
    return {
        **base,
        "risk_level": bucket,
        "delinquency_bucket": bucket,
        "status": status,
        "overdue_days": overdue_days,
        "last_payment_date": raw_last_payment,
        "settlement_date": None,
        "overdue_sort": overdue_sort,
    }


def _reconciliation_query_sql(monitor_filter: str, trust_product_ids: list[int] | None) -> str:
    custody_ctes = _monitor_custody_ctes(monitor_filter)
    product_filter, _ = query_utils.sql_in_int_column(
        "r.trust_product_id", trust_product_ids, param_prefix="tp"
    )
    return f"""
        WITH {custody_ctes},
        repayment_custody AS (
            SELECT
                r.trust_product_id,
                COALESCE(r.custody_asset_code, r.asset_code) AS custody_asset_code,
                COALESCE(SUM(r.actual_repayment_amount), 0) AS repayment_detail_total
            FROM trust_repayment_detail_records r
            WHERE 1=1
            {product_filter}
            GROUP BY r.trust_product_id, COALESCE(r.custody_asset_code, r.asset_code)
        )
        SELECT
            mc.trust_product_id,
            tp.name AS trust_product_name,
            mc.data_date,
            mc.custody_asset_code,
            mc.initial_transfer_amount,
            mc.repaid_amount,
            mc.remaining_amount,
            (mc.remaining_amount - mc.initial_transfer_amount + mc.repaid_amount) AS balance_remainder,
            COALESCE(rc.repayment_detail_total, 0) AS repayment_detail_total,
            (mc.repaid_amount - COALESCE(rc.repayment_detail_total, 0)) AS cross_diff
        FROM monitor_custody mc
        INNER JOIN trust_products tp ON tp.id = mc.trust_product_id
        LEFT JOIN repayment_custody rc
            ON rc.trust_product_id = mc.trust_product_id
           AND rc.custody_asset_code = mc.custody_asset_code
        ORDER BY mc.trust_product_id, mc.custody_asset_code
    """


def _reconciliation_query_sql_by_asset(monitor_filter: str, trust_product_ids: list[int] | None) -> str:
    """金额核对 SQL —— 按资产主编号（asset_code）粒度聚合，替代 custody_asset_code 版本。"""
    custody_ctes = _monitor_custody_ctes(monitor_filter)
    product_filter, _ = query_utils.sql_in_int_column(
        "r.trust_product_id", trust_product_ids, param_prefix="tp"
    )
    return f"""
        WITH {custody_ctes},
        monitor_asset AS (
            SELECT
                d.trust_product_id,
                d.data_date,
                d.asset_code,
                COUNT(DISTINCT d.custody_asset_code) AS custody_count,
                SUM(d.initial_transfer_amount) AS initial_transfer_amount,
                SUM(d.repaid_amount)            AS repaid_amount,
                SUM(d.remaining_amount)         AS remaining_amount,
                CASE
                    WHEN SUM(d.remaining_amount) <= {RECONCILIATION_TOLERANCE}
                    THEN NULL
                    ELSE MAX(d.overdue_days)
                END AS overdue_days,
                MAX(d.last_payment_date) AS last_payment_date,
                MAX(d.max_payment_date)  AS max_payment_date
            FROM monitor_enriched d
            GROUP BY d.trust_product_id, d.data_date, d.asset_code
        ),
        repayment_asset AS (
            SELECT
                r.trust_product_id,
                r.asset_code,
                COALESCE(SUM(r.actual_repayment_amount), 0) AS repayment_detail_total
            FROM trust_repayment_detail_records r
            WHERE r.asset_code IS NOT NULL
            {product_filter}
            GROUP BY r.trust_product_id, r.asset_code
        ),
        code_mismatch_asset AS (
            SELECT
                r.trust_product_id,
                ta.asset_code AS canonical_asset_code,
                COUNT(*) AS code_mismatch_count,
                COALESCE(SUM(r.actual_repayment_amount), 0) AS code_mismatch_amount
            FROM trust_repayment_detail_records r
            INNER JOIN trust_assets ta ON ta.id = r.trust_asset_id
            WHERE r.asset_code IS DISTINCT FROM ta.asset_code
            {product_filter}
            GROUP BY r.trust_product_id, ta.asset_code
        )
        SELECT
            ma.trust_product_id,
            tp.name AS trust_product_name,
            ma.data_date,
            ma.asset_code,
            ma.custody_count,
            ma.initial_transfer_amount,
            ma.repaid_amount,
            ma.remaining_amount,
            (ma.remaining_amount - ma.initial_transfer_amount + ma.repaid_amount) AS balance_remainder,
            COALESCE(ra.repayment_detail_total, 0) AS repayment_detail_total,
            (ma.repaid_amount - COALESCE(ra.repayment_detail_total, 0)) AS cross_diff,
            COALESCE(cm.code_mismatch_count, 0) AS code_mismatch_count,
            COALESCE(cm.code_mismatch_amount, 0) AS code_mismatch_amount
        FROM monitor_asset ma
        INNER JOIN trust_products tp ON tp.id = ma.trust_product_id
        LEFT JOIN repayment_asset ra
            ON ra.trust_product_id = ma.trust_product_id
           AND ra.asset_code = ma.asset_code
        LEFT JOIN code_mismatch_asset cm
            ON cm.trust_product_id = ma.trust_product_id
           AND cm.canonical_asset_code = ma.asset_code
        ORDER BY ma.trust_product_id, ma.asset_code
    """


def _reconciliation_item_from_row(row) -> dict:
    balance_remainder = float(row.balance_remainder)
    cross_diff = float(row.cross_diff)
    repaid_amount = float(row.repaid_amount)
    balance_passed = abs(balance_remainder) <= RECONCILIATION_TOLERANCE
    cross_passed = abs(cross_diff) <= RECONCILIATION_TOLERANCE
    code_mismatch_count = int(getattr(row, "code_mismatch_count", 0) or 0)
    code_mismatch_passed = code_mismatch_count == 0
    return {
        "trust_product_id": row.trust_product_id,
        "trust_product_name": row.trust_product_name,
        "data_date": str(row.data_date),
        "asset_code": row.asset_code,
        "custody_count": int(row.custody_count),
        "initial_transfer_amount": float(row.initial_transfer_amount),
        "repaid_amount": repaid_amount,
        "remaining_amount": float(row.remaining_amount),
        "balance_remainder": balance_remainder,
        "balance_passed": balance_passed,
        "cross_diff": cross_diff,
        "cross_passed": cross_passed,
        "code_mismatch_count": code_mismatch_count,
        "code_mismatch_amount": float(getattr(row, "code_mismatch_amount", 0) or 0),
        "code_mismatch_passed": code_mismatch_passed,
        "monitor_repaid_amount": repaid_amount,
        "repayment_detail_total": float(row.repayment_detail_total),
        "has_anomaly": not balance_passed or not cross_passed or not code_mismatch_passed,
    }


def _reconciliation_summary(items: list[dict]) -> dict[str, int]:
    return {
        "balance_pass_count": sum(1 for item in items if item["balance_passed"]),
        "balance_fail_count": sum(1 for item in items if not item["balance_passed"]),
        "cross_pass_count": sum(1 for item in items if item["cross_passed"]),
        "cross_fail_count": sum(1 for item in items if not item["cross_passed"]),
        "code_mismatch_pass_count": sum(1 for item in items if item["code_mismatch_passed"]),
        "code_mismatch_fail_count": sum(1 for item in items if not item["code_mismatch_passed"]),
    }


def _fetch_repayment_code_mismatch_alerts(
    conn,
    trust_product_ids: list[int] | None = None,
) -> list[dict]:
    """还款事实表 asset_code 与 trust_assets 权威主编号不一致的独立告警。"""
    product_filter, params = query_utils.sql_in_int_column(
        "r.trust_product_id", trust_product_ids, param_prefix="rpid"
    )
    rows = conn.execute(
        text(f"""
            SELECT
                r.trust_product_id,
                tp.name AS trust_product_name,
                ta.asset_code AS canonical_asset_code,
                r.asset_code AS stored_asset_code,
                COUNT(*) AS row_count,
                COALESCE(SUM(r.actual_repayment_amount), 0) AS amount_sum
            FROM trust_repayment_detail_records r
            INNER JOIN trust_assets ta ON ta.id = r.trust_asset_id
            INNER JOIN trust_products tp ON tp.id = r.trust_product_id
            WHERE r.asset_code IS DISTINCT FROM ta.asset_code
            {product_filter}
            GROUP BY r.trust_product_id, tp.name, ta.asset_code, r.asset_code
            ORDER BY r.trust_product_id, ta.asset_code, r.asset_code
        """),
        params,
    )
    return [
        {
            "trust_product_id": row.trust_product_id,
            "trust_product_name": row.trust_product_name,
            "canonical_asset_code": row.canonical_asset_code,
            "stored_asset_code": row.stored_asset_code,
            "row_count": int(row.row_count),
            "amount_sum": float(row.amount_sum),
        }
        for row in rows
    ]


RECONCILIATION_BASIS_LABEL = "监控快照日 + 全量还款明细"


def _latest_monitor_filter(
    trust_product_ids: list[int] | None,
    data_date: str | None,
) -> tuple[str, dict]:
    params: dict = {}
    if data_date:
        product_sql, product_params = query_utils.sql_in_int_column(
            "m.trust_product_id", trust_product_ids, param_prefix="tp"
        )
        params.update(product_params)
        return (
            f"m.data_date = :data_date{product_sql}",
            {**params, "data_date": data_date},
        )

    if trust_product_ids is not None:
        product_sql, product_params = query_utils.sql_in_int_column(
            "m.trust_product_id", trust_product_ids, param_prefix="tp"
        )
        params.update(product_params)
        if len(trust_product_ids) == 1:
            return (
                f"""
                m.trust_product_id = :tp_0
                AND m.data_date = (
                    SELECT MAX(data_date)
                    FROM trust_asset_monitor_records
                    WHERE trust_product_id = :tp_0
                )
                """.strip(),
                product_params,
            )
        return (
            f"""
            1=1{product_sql}
            AND m.data_date = (
                SELECT MAX(data_date)
                FROM trust_asset_monitor_records m2
                WHERE m2.trust_product_id = m.trust_product_id
            )
            """.strip(),
            product_params,
        )

    return (
        """
        m.data_date = (
            SELECT MAX(data_date) FROM trust_asset_monitor_records
        )
        """,
        {},
    )


def _fetch_overdue_recalc_meta(
    conn,
    trust_product_ids: list[int] | None,
    data_date: str | None,
) -> dict:
    monitor_filter, params = _latest_monitor_filter(trust_product_ids, data_date)
    row = conn.execute(
        text(f"""
            SELECT
                MAX(m.overdue_days_as_of) AS overdue_days_as_of,
                MAX(m.updated_at) AS last_recalculated_at,
                COUNT(*) FILTER (WHERE m.overdue_days_as_of IS NOT NULL) AS as_of_set_count,
                COUNT(*) AS record_count
            FROM trust_asset_monitor_records m
            WHERE {monitor_filter}
        """),
        params,
    ).fetchone()
    if row is None or int(row.record_count or 0) == 0:
        return {
            "overdue_days_as_of": None,
            "last_recalculated_at": None,
            "overdue_recalc_stale": True,
        }
    as_of_set = int(row.as_of_set_count or 0)
    total = int(row.record_count or 0)
    return {
        "overdue_days_as_of": str(row.overdue_days_as_of) if row.overdue_days_as_of else None,
        "last_recalculated_at": (
            str(row.last_recalculated_at) if row.last_recalculated_at else None
        ),
        "overdue_recalc_stale": as_of_set < total,
    }


def _recon_monitor_filter(
    monitor_filter: str,
    trust_product_ids: list[int] | None,
    params: dict,
) -> str:
    if "data_date" in params:
        return monitor_filter
    if trust_product_ids is None:
        return "m.data_date = :data_date"
    if len(trust_product_ids) == 1:
        return "m.trust_product_id = :tp_0 AND m.data_date = :data_date"
    return monitor_filter


def fetch_overdue_overview(
    conn,
    trust_product_ids: list[int] | None = None,
    data_date: str | None = None,
    *,
    delinquency_bucket: str | None = None,
    delinquency_buckets: list[str] | None = None,
    trust_marker: str | None = None,
    trust_markers: list[str] | None = None,
    internal_status: str | None = None,
    internal_statuses: list[str] | None = None,
    has_followup: str | None = None,
    asset_code: str | None = None,
    custody_asset_code: str | None = None,
    city: str | None = None,
    cities: list[str] | None = None,
):
    list_filters = {
        "trust_product_ids": trust_product_ids,
        "delinquency_bucket": delinquency_bucket,
        "delinquency_buckets": delinquency_buckets,
        "trust_marker": trust_marker,
        "trust_markers": trust_markers,
        "internal_status": internal_status,
        "internal_statuses": internal_statuses,
        "has_followup": has_followup,
        "asset_code": asset_code,
        "custody_asset_code": custody_asset_code,
        "city": city,
        "cities": cities,
    }
    monitor_filter, params = _latest_monitor_filter(trust_product_ids, data_date)
    custody_ctes = _monitor_custody_ctes(monitor_filter)

    query_params = dict(params)
    if "tolerance" not in query_params:
        query_params["tolerance"] = RECONCILIATION_TOLERANCE

    row = conn.execute(
        text(f"""
            WITH {custody_ctes}
            SELECT
                MAX(mc.data_date) AS data_date,
                COUNT(*) FILTER (
                    WHERE {sql_exposure_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS exposure_count,
                COUNT(*) FILTER (
                    WHERE {sql_es_asset_filter("mc.remaining_amount")}
                ) AS es_count,
                COUNT(*) FILTER (
                    WHERE {sql_m0_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS m0_count,
                COUNT(*) FILTER (
                    WHERE {sql_m0_5_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS m0_5_count,
                COUNT(*) FILTER (
                    WHERE {sql_m1_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS m1_count,
                COUNT(*) FILTER (
                    WHERE {sql_m1_plus_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS m1_plus_count,
                SUM(mc.remaining_amount) FILTER (
                    WHERE {sql_exposure_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS exposure_remaining_sum,
                SUM(mc.initial_transfer_amount) FILTER (
                    WHERE {sql_exposure_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS exposure_initial_sum,
                SUM(mc.repaid_amount) FILTER (
                    WHERE {sql_es_asset_filter("mc.remaining_amount")}
                ) AS es_repaid_sum,
                SUM(mc.initial_transfer_amount) FILTER (
                    WHERE {sql_es_asset_filter("mc.remaining_amount")}
                ) AS es_initial_sum,
                SUM(mc.remaining_amount) FILTER (
                    WHERE {sql_m0_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS m0_remaining_sum,
                SUM(mc.initial_transfer_amount) FILTER (
                    WHERE {sql_m0_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS m0_initial_sum,
                SUM(mc.remaining_amount) FILTER (
                    WHERE {sql_overdue_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS overdue_remaining_sum,
                SUM(mc.initial_transfer_amount) FILTER (
                    WHERE {sql_overdue_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS overdue_initial_sum,
                SUM(mc.remaining_amount) FILTER (
                    WHERE {sql_m0_5_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS m0_5_remaining_sum,
                SUM(mc.initial_transfer_amount) FILTER (
                    WHERE {sql_m0_5_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS m0_5_initial_sum,
                SUM(mc.remaining_amount) FILTER (
                    WHERE {sql_m1_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS m1_remaining_sum,
                SUM(mc.initial_transfer_amount) FILTER (
                    WHERE {sql_m1_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS m1_initial_sum,
                SUM(mc.remaining_amount) FILTER (
                    WHERE {sql_m1_plus_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS m1_plus_remaining_sum,
                SUM(mc.initial_transfer_amount) FILTER (
                    WHERE {sql_m1_plus_asset_filter("mc.overdue_days", "mc.remaining_amount")}
                ) AS m1_plus_initial_sum,
                COUNT(*) AS total_asset_count,
                COUNT(DISTINCT mc.asset_code) AS total_asset_code_count
            FROM monitor_custody mc
        """),
        query_params,
    ).fetchone()

    empty_buckets = {"ES": [], "M0": [], "M0_5": [], "M1": [], "M1_PLUS": []}

    if row is None:
        kpi = build_overdue_kpi_metrics(0, 0, 0, 0, 0)
        return {
            "data_date": data_date,
            "trust_product_ids": trust_product_ids,
            "overdue_count": 0,
            "overdue_count_deprecated": True,
            "es_count": 0,
            "m0_count": 0,
            "m0_5_count": 0,
            "m1_count": 0,
            "m1_plus_count": 0,
            **kpi,
            "amounts": _zero_overdue_kpi_amounts(),
            "total_asset_count": 0,
            "total_asset_code_count": 0,
            "reconciliation_failed_count": 0,
            "reconciliation_count_basis": "asset_code",
            "active_followup_count": 0,
            "top_overdue_by_bucket": empty_buckets,
            "bucket_totals": {k: _bucket_amount_totals([]) for k in empty_buckets},
            "issuance_city_options": fetch_overdue_issuance_cities(conn, trust_product_ids),
            "list_filters": list_filters,
            **_fetch_overdue_recalc_meta(conn, trust_product_ids, data_date),
        }

    resolved_data_date = str(row.data_date) if row.data_date else data_date
    recon_params = dict(params)
    if "data_date" not in recon_params and resolved_data_date:
        recon_params["data_date"] = resolved_data_date

    recon_filter = _recon_monitor_filter(monitor_filter, trust_product_ids, recon_params)

    recon_row = conn.execute(
        text(f"""
            SELECT COUNT(*) AS failed_count
            FROM ({_reconciliation_query_sql_by_asset(recon_filter, trust_product_ids)}) recon
            WHERE ABS(recon.balance_remainder) > :tolerance
               OR ABS(recon.cross_diff) > :tolerance
               OR recon.code_mismatch_count > 0
        """),
        {**recon_params, "tolerance": RECONCILIATION_TOLERANCE},
    ).fetchone()

    followup_sql = """
        SELECT COUNT(*) AS cnt
        FROM trust_overdue_followup_cases
        WHERE status IN ('open', 'in_progress')
    """
    followup_params: dict = {}
    followup_product_sql, followup_product_params = query_utils.sql_in_int_column(
        "trust_product_id", trust_product_ids, param_prefix="fpid"
    )
    followup_sql += followup_product_sql
    followup_params.update(followup_product_params)

    followup_row = conn.execute(text(followup_sql), followup_params).fetchone()

    overdue_rows = conn.execute(
        text(f"""
            WITH {custody_ctes}
            SELECT
                mc.trust_product_id,
                tp.name AS trust_product_name,
                mc.data_date,
                mc.asset_code,
                mc.custody_asset_code,
                mc.source_asset_count,
                mc.initial_transfer_amount,
                mc.repaid_amount,
                mc.remaining_amount,
                mc.last_payment_date AS raw_last_payment_date,
                mc.max_payment_date,
                mc.overdue_days,
                mc.source_asset_codes,
                iss.city AS issuance_city,
                COALESCE(tm.trust_marker, :default_trust_marker) AS trust_marker,
                COALESCE(tm.internal_status, :default_internal_status) AS internal_status,
                {_custody_followup_count_sql()} AS followup_count,
                {_custody_has_follow_up_sql()} AS has_follow_up
            FROM monitor_custody mc
            INNER JOIN trust_products tp ON tp.id = mc.trust_product_id
            {_issuance_city_lateral_join_sql()}
            {_custody_marks_join_sql()}
            ORDER BY
                {overdue_buckets.sql_custody_list_sort_priority("mc.overdue_days", "mc.remaining_amount")},
                COALESCE(mc.overdue_days, 0) DESC,
                mc.asset_code ASC,
                mc.custody_asset_code ASC
        """),
        {
            **query_params,
            "default_trust_marker": TRUST_MARKER_DEFAULT,
            "default_internal_status": INTERNAL_STATUS_DEFAULT,
        },
    )

    top_overdue_by_bucket: dict[str, list] = {k: [] for k in empty_buckets}
    for r in overdue_rows:
        item = _custody_item_from_row(r)
        if not _apply_custody_list_filters(item, list_filters):
            continue
        bucket = item["delinquency_bucket"]
        if bucket in top_overdue_by_bucket:
            top_overdue_by_bucket[bucket].append(item)

    for bucket, items in top_overdue_by_bucket.items():
        top_overdue_by_bucket[bucket] = _sort_custody_items_in_bucket(items, bucket)

    bucket_totals = {
        bucket: _bucket_amount_totals(items)
        for bucket, items in top_overdue_by_bucket.items()
    }

    es = int(row.es_count)
    m0 = int(row.m0_count)
    m0_5 = int(row.m0_5_count)
    m1 = int(row.m1_count)
    m1_plus = int(row.m1_plus_count)
    kpi = build_overdue_kpi_metrics(es, m0, m0_5, m1, m1_plus)

    return {
        "data_date": resolved_data_date,
        "trust_product_ids": trust_product_ids,
        "overdue_count": kpi["exposure_total"],
        "overdue_count_deprecated": True,
        "es_count": es,
        "m0_count": m0,
        "m0_5_count": m0_5,
        "m1_count": m1,
        "m1_plus_count": m1_plus,
        **kpi,
        "amounts": _overdue_kpi_amounts_from_row(row),
        "total_asset_count": int(row.total_asset_count),
        "total_asset_code_count": int(row.total_asset_code_count),
        "reconciliation_failed_count": int(recon_row.failed_count) if recon_row else 0,
        "reconciliation_count_basis": "asset_code",
        "active_followup_count": int(followup_row.cnt) if followup_row else 0,
        "top_overdue_by_bucket": top_overdue_by_bucket,
        "bucket_totals": bucket_totals,
        "issuance_city_options": fetch_overdue_issuance_cities(conn, trust_product_ids),
        "list_filters": list_filters,
        **_fetch_overdue_recalc_meta(conn, trust_product_ids, data_date),
    }


def upsert_asset_trust_mark(
    conn,
    trust_product_id: int,
    asset_code: str,
    data_date: str,
    *,
    trust_marker: str | None = None,
    internal_status: str | None = None,
    updated_by: str | None = None,
) -> dict:
    if trust_marker is not None and trust_marker not in TRUST_MARKER_OPTIONS:
        raise HTTPException(status_code=400, detail="Invalid trust_marker")
    # internal_status 由跟进事项派生，禁止人工写入
    if internal_status is not None:
        raise HTTPException(status_code=400, detail="内部状态只读，请通过跟进事项维护")
    if trust_marker is None:
        raise HTTPException(status_code=400, detail="No fields to update")

    existing = conn.execute(
        text("""
            SELECT id, trust_marker, internal_status, data_date
            FROM trust_asset_trust_marks
            WHERE trust_product_id = :trust_product_id
              AND asset_code = :asset_code
            LIMIT 1
        """),
        {
            "trust_product_id": trust_product_id,
            "asset_code": asset_code,
        },
    ).fetchone()

    if existing:
        new_marker = trust_marker if trust_marker is not None else existing.trust_marker
        new_status = (
            internal_status if internal_status is not None else existing.internal_status
        )
        conn.execute(
            text("""
                UPDATE trust_asset_trust_marks
                SET trust_marker = :trust_marker,
                    internal_status = :internal_status,
                    data_date = COALESCE(:data_date, data_date),
                    updated_by = :updated_by,
                    updated_at = NOW()
                WHERE id = :id
            """),
            {
                "id": existing.id,
                "trust_marker": new_marker,
                "internal_status": new_status,
                "data_date": data_date,
                "updated_by": updated_by,
            },
        )
        return {
            "id": existing.id,
            "trust_product_id": trust_product_id,
            "asset_code": asset_code,
            "data_date": data_date or str(existing.data_date),
            "trust_marker": new_marker,
            "internal_status": new_status,
        }

    new_marker = trust_marker or TRUST_MARKER_DEFAULT
    new_status = internal_status or INTERNAL_STATUS_DEFAULT
    row = conn.execute(
        text("""
            INSERT INTO trust_asset_trust_marks (
                trust_product_id, asset_code, custody_asset_code, data_date,
                trust_marker, internal_status, created_by, updated_by
            ) VALUES (
                :trust_product_id, :asset_code, :asset_code, :data_date,
                :trust_marker, :internal_status, :updated_by, :updated_by
            )
            RETURNING id
        """),
        {
            "trust_product_id": trust_product_id,
            "asset_code": asset_code,
            "data_date": data_date,
            "trust_marker": new_marker,
            "internal_status": new_status,
            "updated_by": updated_by,
        },
    ).fetchone()
    return {
        "id": row.id,
        "trust_product_id": trust_product_id,
        "asset_code": asset_code,
        "data_date": data_date,
        "trust_marker": new_marker,
        "internal_status": new_status,
    }


def upsert_custody_trust_mark(
    conn,
    trust_product_id: int,
    custody_asset_code: str,
    data_date: str,
    *,
    trust_marker: str | None = None,
    internal_status: str | None = None,
    updated_by: str | None = None,
) -> dict:
    """Legacy: resolve custody to asset_code then upsert."""
    row = conn.execute(
        text("""
            SELECT m.asset_code
            FROM trust_asset_monitor_records m
            INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
            WHERE m.trust_product_id = :trust_product_id
              AND m.data_date = :data_date
              AND COALESCE(m.custody_asset_code, ta.custody_asset_code, m.asset_code)
                  = :custody_asset_code
            LIMIT 1
        """),
        {
            "trust_product_id": trust_product_id,
            "custody_asset_code": custody_asset_code,
            "data_date": data_date,
        },
    ).fetchone()
    asset_code = str(row.asset_code) if row and row.asset_code else custody_asset_code
    return upsert_asset_trust_mark(
        conn,
        trust_product_id,
        asset_code,
        data_date,
        trust_marker=trust_marker,
        internal_status=internal_status,
        updated_by=updated_by,
    )


def fetch_trust_products(conn) -> list[dict]:
    rows = conn.execute(text("SELECT id, name FROM trust_products ORDER BY id"))
    return [{"id": r.id, "name": r.name} for r in rows]


def fetch_overdue_checks(conn, trust_product_ids: list[int] | None = None, data_date: str | None = None):
    monitor_filter, params = _latest_monitor_filter(trust_product_ids, data_date)
    custody_ctes = _monitor_custody_ctes(monitor_filter)

    rows = conn.execute(
        text(f"""
            WITH {custody_ctes}
            SELECT
                mc.trust_product_id,
                tp.name AS trust_product_name,
                mc.data_date,
                mc.asset_code,
                mc.custody_asset_code,
                mc.source_asset_count,
                mc.initial_transfer_amount,
                mc.repaid_amount,
                mc.remaining_amount,
                mc.last_payment_date,
                mc.max_payment_date,
                mc.overdue_days,
                mc.source_asset_codes,
                {_custody_has_follow_up_sql()} AS has_follow_up
            FROM monitor_custody mc
            INNER JOIN trust_products tp ON tp.id = mc.trust_product_id
            WHERE {sql_overdue_asset_filter("mc.overdue_days", "mc.remaining_amount")}
            ORDER BY mc.overdue_days DESC, mc.custody_asset_code
        """),
        {**params, "tolerance": RECONCILIATION_TOLERANCE},
    )

    items = []
    resolved_date = data_date
    for row in rows:
        if resolved_date is None:
            resolved_date = str(row.data_date)
        items.append(_custody_item_from_row(row))

    return {"data_date": resolved_date, "items": items}


def fetch_reconciliation(conn, trust_product_ids: list[int] | None = None, data_date: str | None = None):
    monitor_filter, params = _latest_monitor_filter(trust_product_ids, data_date)

    row = conn.execute(
        text(f"""
            SELECT m.data_date
            FROM trust_asset_monitor_records m
            WHERE {monitor_filter}
            LIMIT 1
        """),
        params,
    ).fetchone()

    if row is None:
        return {
            "data_date": data_date,
            "items": [],
            "total_count": 0,
            "anomaly_count": 0,
            "basis": RECONCILIATION_BASIS_LABEL,
            "balance_pass_count": 0,
            "balance_fail_count": 0,
            "cross_pass_count": 0,
            "cross_fail_count": 0,
            "code_mismatch_pass_count": 0,
            "code_mismatch_fail_count": 0,
            "code_mismatch_alerts": _fetch_repayment_code_mismatch_alerts(conn, trust_product_ids),
        }

    resolved_data_date = str(row.data_date)
    query_params = dict(params)
    if "data_date" not in query_params:
        query_params["data_date"] = resolved_data_date

    recon_filter = _recon_monitor_filter(monitor_filter, trust_product_ids, query_params)

    rows = conn.execute(
        text(_reconciliation_query_sql_by_asset(recon_filter, trust_product_ids)),
        query_params,
    )

    items = [_reconciliation_item_from_row(r) for r in rows]
    anomaly_count = sum(1 for item in items if item["has_anomaly"])
    summary = _reconciliation_summary(items)
    code_mismatch_alerts = _fetch_repayment_code_mismatch_alerts(conn, trust_product_ids)

    return {
        "data_date": resolved_data_date,
        "items": items,
        "total_count": len(items),
        "anomaly_count": anomaly_count,
        "basis": RECONCILIATION_BASIS_LABEL,
        "code_mismatch_alerts": code_mismatch_alerts,
        **summary,
    }


def recalculate_reconciliation(
    conn,
    trust_product_ids: list[int] | None = None,
    data_date: str | None = None,
) -> dict:
    """基于当前监控快照与全量还款明细重算金额核对统计（不落库）。"""
    from datetime import datetime, timezone

    payload = fetch_reconciliation(conn, trust_product_ids, data_date)
    as_of = datetime.now(timezone.utc).isoformat()
    total = int(payload["total_count"])
    balance_fail = int(payload["balance_fail_count"])
    cross_fail = int(payload["cross_fail_count"])
    code_mismatch_fail = int(payload["code_mismatch_fail_count"])
    return {
        "data_date": payload.get("data_date"),
        "trust_product_ids": trust_product_ids,
        "as_of": as_of,
        "basis": RECONCILIATION_BASIS_LABEL,
        "recalculated_count": total,
        "balance_pass_count": int(payload["balance_pass_count"]),
        "balance_fail_count": balance_fail,
        "cross_pass_count": int(payload["cross_pass_count"]),
        "cross_fail_count": cross_fail,
        "code_mismatch_pass_count": int(payload["code_mismatch_pass_count"]),
        "code_mismatch_fail_count": code_mismatch_fail,
        "code_mismatch_alerts": payload.get("code_mismatch_alerts") or [],
        "message": (
            f"已重新计算 {total} 条资产主编号金额核对"
            f"，剩余差额异常：{balance_fail} 条"
            f"，跨表检查不通过：{cross_fail} 条"
            f"，编码不一致：{code_mismatch_fail} 条"
        ),
    }


def _resolve_monitor_data_date(
    conn,
    trust_product_id: int | None,
    data_date: str | None,
) -> date | None:
    if data_date:
        return date.fromisoformat(data_date)
    sql = "SELECT MAX(data_date) AS dd FROM trust_asset_monitor_records WHERE 1=1"
    params: dict = {}
    if trust_product_id is not None:
        sql += " AND trust_product_id = :trust_product_id"
        params["trust_product_id"] = trust_product_id
    row = conn.execute(text(sql), params).fetchone()
    return row.dd if row and row.dd else None


def recalculate_overdue_days(
    conn,
    trust_product_id: int | None = None,
    data_date: str | None = None,
    as_of: date | None = None,
    trust_product_ids: list[int] | None = None,
) -> dict:
    """按重算日重算各产品最新监控快照层的 overdue_days。

    - as_of 默认当天，全产品统一
    - 多产品：每个产品取各自 MAX(data_date) 再 UPDATE
    - 公式：as_of − (锚点日 + 1 calendar month)；锚点=最后付款日或最早发行日
    """
    today = as_of or date.today()
    product_ids: list[int] | None
    if trust_product_ids is not None:
        product_ids = [int(x) for x in trust_product_ids]
    elif trust_product_id is not None:
        product_ids = [int(trust_product_id)]
    else:
        product_ids = None  # all products

    # Single-product + explicit data_date override (legacy)
    if (
        product_ids is not None
        and len(product_ids) == 1
        and data_date
    ):
        scopes = [(product_ids[0], date.fromisoformat(str(data_date)))]
    else:
        scope_sql = """
            SELECT trust_product_id, MAX(data_date) AS data_date
            FROM trust_asset_monitor_records
            WHERE 1=1
        """
        params: dict = {}
        if product_ids is not None:
            if not product_ids:
                raise HTTPException(status_code=400, detail="trust_product_ids 为空")
            scope_sql += " AND trust_product_id = ANY(:pids)"
            params["pids"] = product_ids
        scope_sql += " GROUP BY trust_product_id ORDER BY trust_product_id"
        rows = conn.execute(text(scope_sql), params).fetchall()
        scopes = [(int(r.trust_product_id), r.data_date) for r in rows if r.data_date]

    if not scopes:
        raise HTTPException(status_code=400, detail="无可用监控快照 data_date")

    total_updated = 0
    total_with_repay = 0
    total_from_issue = 0
    total_missing = 0
    per_product: list[dict] = []
    warnings: list[str] = []

    for pid, resolved_dd in scopes:
        scope_parts = [
            "m.trust_product_id = :trust_product_id",
            "m.data_date = :data_date",
        ]
        params = {
            "trust_product_id": pid,
            "data_date": resolved_dd,
            "as_of": today,
            "tolerance": RECONCILIATION_TOLERANCE,
        }
        scope_sql = " AND ".join(scope_parts)

        with_repayment = conn.execute(
            text(f"""
                UPDATE trust_asset_monitor_records m
                SET
                    last_payment_date = rp.max_rd,
                    max_payment_date = rp.max_rd,
                    overdue_days = CASE
                        WHEN m.remaining_amount <= :tolerance THEN NULL
                        ELSE (CAST(:as_of AS date) - (rp.max_rd + INTERVAL '1 month')::date)
                    END,
                    overdue_days_as_of = :as_of,
                    updated_at = NOW()
                FROM (
                    SELECT r.trust_product_id, ta.asset_code, MAX(r.repayment_date) AS max_rd
                    FROM trust_repayment_detail_records r
                    INNER JOIN trust_assets ta ON ta.id = r.trust_asset_id
                    WHERE r.trust_product_id = :trust_product_id
                    GROUP BY r.trust_product_id, ta.asset_code
                ) rp
                WHERE m.trust_product_id = rp.trust_product_id
                  AND m.asset_code = rp.asset_code
                  AND {scope_sql}
            """),
            params,
        )

        without_repayment_from_issue = conn.execute(
            text(f"""
                UPDATE trust_asset_monitor_records m
                SET
                    last_payment_date = NULL,
                    max_payment_date = NULL,
                    overdue_days = CASE
                        WHEN m.remaining_amount <= :tolerance THEN NULL
                        ELSE (CAST(:as_of AS date) - (iss.min_issue_date + INTERVAL '1 month')::date)
                    END,
                    overdue_days_as_of = :as_of,
                    updated_at = NOW()
                FROM (
                    SELECT
                        m2.id AS monitor_id,
                        COALESCE(ip.min_issue_date, ia.min_issue_date) AS min_issue_date
                    FROM trust_asset_monitor_records m2
                    LEFT JOIN (
                        SELECT
                            i.trust_product_id,
                            regexp_replace(COALESCE(i.custody_asset_code, ''), '\.0$', '') AS custody_norm,
                            MIN(i.issue_date) AS min_issue_date
                        FROM trust_product_issuance_asset_records i
                        WHERE i.trust_product_id = :trust_product_id
                        GROUP BY i.trust_product_id, custody_norm
                    ) ip
                      ON ip.trust_product_id = m2.trust_product_id
                     AND ip.custody_norm = regexp_replace(
                         COALESCE(m2.custody_asset_code, m2.asset_code, ''), '\.0$', ''
                     )
                    LEFT JOIN (
                        SELECT
                            regexp_replace(COALESCE(i.custody_asset_code, ''), '\.0$', '') AS custody_norm,
                            MIN(i.issue_date) AS min_issue_date
                        FROM trust_product_issuance_asset_records i
                        GROUP BY custody_norm
                    ) ia
                      ON ia.custody_norm = regexp_replace(
                          COALESCE(m2.custody_asset_code, m2.asset_code, ''), '\.0$', ''
                      )
                    WHERE m2.trust_product_id = :trust_product_id
                      AND m2.data_date = :data_date
                      AND COALESCE(ip.min_issue_date, ia.min_issue_date) IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1
                          FROM trust_repayment_detail_records r
                          INNER JOIN trust_assets ta ON ta.id = r.trust_asset_id
                          WHERE r.trust_product_id = m2.trust_product_id
                            AND ta.asset_code = m2.asset_code
                      )
                ) iss
                WHERE m.id = iss.monitor_id
            """),
            params,
        )

        missing_issuance = conn.execute(
            text(f"""
                UPDATE trust_asset_monitor_records m
                SET
                    last_payment_date = NULL,
                    max_payment_date = NULL,
                    overdue_days = NULL,
                    overdue_days_as_of = :as_of,
                    updated_at = NOW()
                WHERE {scope_sql}
                  AND NOT EXISTS (
                      SELECT 1
                      FROM trust_repayment_detail_records r
                      INNER JOIN trust_assets ta ON ta.id = r.trust_asset_id
                      WHERE r.trust_product_id = m.trust_product_id
                        AND ta.asset_code = m.asset_code
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM trust_product_issuance_asset_records i
                      WHERE regexp_replace(COALESCE(i.custody_asset_code, ''), '\.0$', '')
                          = regexp_replace(
                              COALESCE(m.custody_asset_code, m.asset_code, ''), '\.0$', ''
                          )
                  )
            """),
            params,
        )

        conn.execute(
            text(f"""
                UPDATE trust_asset_monitor_records m
                SET
                    overdue_days = NULL,
                    overdue_days_as_of = :as_of,
                    updated_at = NOW()
                WHERE {scope_sql}
                  AND m.remaining_amount <= :tolerance
                  AND m.overdue_days IS NOT NULL
            """),
            params,
        )

        total_row = conn.execute(
            text(f"SELECT COUNT(*) AS cnt FROM trust_asset_monitor_records m WHERE {scope_sql}"),
            params,
        ).fetchone()
        updated_count = int(total_row.cnt) if total_row else 0
        from_issue = int(without_repayment_from_issue.rowcount or 0)
        missing = int(missing_issuance.rowcount or 0)
        with_repay = int(with_repayment.rowcount or 0)

        total_updated += updated_count
        total_with_repay += with_repay
        total_from_issue += from_issue
        total_missing += missing
        per_product.append({
            "trust_product_id": pid,
            "data_date": str(resolved_dd),
            "updated_count": updated_count,
            "with_repayment_updated": with_repay,
            "no_repayment_from_issue_count": from_issue,
            "missing_issuance_count": missing,
        })

    if total_missing > 0:
        warnings.append(
            f"部分资产无还款明细且无发行日，逾期天数置空（{total_missing} 条）"
        )

    product_count = len(scopes)
    data_dates = sorted({p["data_date"] for p in per_product})
    single_dd = data_dates[0] if len(data_dates) == 1 else None

    return {
        "data_date": single_dd,
        "data_dates": data_dates,
        "products": per_product,
        "product_count": product_count,
        "trust_product_id": product_ids[0] if product_ids and len(product_ids) == 1 else None,
        "trust_product_ids": [p["trust_product_id"] for p in per_product],
        "as_of_date": str(today),
        "overdue_days_as_of": str(today),
        "updated_count": total_updated,
        "no_repayment_from_issue_count": total_from_issue,
        "missing_issuance_count": total_missing,
        "missing_repayment_count": total_from_issue + total_missing,
        "with_repayment_updated": total_with_repay,
        "warnings": warnings,
        "message": (
            f"已按重算日 {today} 重新计算 {product_count} 个产品共 {total_updated} 条监控记录"
            + (
                f"，无还款按发行日+1月计算 {total_from_issue} 条"
                if total_from_issue
                else ""
            )
            + (f"，无发行日置空 {total_missing} 条" if total_missing else "")
        ),
        "risk_hint": "逾期天数已更新，如需同步风险评分，请单独执行风险评分重算。",
    }



def fetch_overdue_followups(
    trust_product_ids: list[int] | None = None,
    status: str | None = None,
    *,
    include_latest_entry: bool = False,
    limit: int = 500,
):
    from app.repo.followup_repo import FollowupRepo

    return FollowupRepo(engine).fetch_cases_list(
        trust_product_ids,
        status,
        limit=limit,
        include_latest_entry=include_latest_entry,
    )


def _filtered_asset_keys_from_overview(overview: dict) -> set[tuple[int, str]]:
    keys: set[tuple[int, str]] = set()
    for items in (overview.get("top_overdue_by_bucket") or {}).values():
        for item in items or []:
            pid = item.get("trust_product_id")
            asset_code = item.get("asset_code")
            if pid is None or not asset_code:
                continue
            keys.add((int(pid), str(asset_code)))
    return keys


def _followup_entry_summary_display(item: dict, *, max_len: int = 48) -> str:
    text = str(
        item.get("latest_overdue_reason")
        or item.get("latest_follow_up_plan")
        or item.get("overdue_reason")
        or item.get("follow_up_plan")
        or ""
    ).strip()
    if not text:
        return "—"
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def fetch_portfolio_followup_cases(overview: dict) -> list[dict]:
    """当前筛选资产下的全部跟进事项（含最新跟进摘要），与台账计数同源。"""
    asset_keys = _filtered_asset_keys_from_overview(overview)
    if not asset_keys:
        return []
    pids = sorted({pid for pid, _ in asset_keys})
    cases = fetch_overdue_followups(
        pids,
        include_latest_entry=True,
        limit=5000,
    )
    return [
        item
        for item in cases
        if (int(item["trust_product_id"]), str(item.get("asset_code") or "")) in asset_keys
    ]


def fmt_asset_identity(item: dict) -> str:
    custody = item.get("custody_asset_code") or "—"
    source = item.get("source_asset_code") or item.get("asset_code") or "—"
    return (
        f'<span class="asset-id">'
        f'<span title="托管房源号">{escape(str(custody))}</span>'
        f' <span class="muted" title="资产分笔号">/ {escape(str(source))}</span>'
        f"</span>"
    )


def fmt_asset_identity_block(item: dict) -> str:
    custody = item.get("custody_asset_code") or "—"
    source = item.get("source_asset_code") or item.get("asset_code") or "—"
    return f"""
      <p><span class="lbl">托管房源号</span>{escape(str(custody))}</p>
      <p><span class="lbl">资产分笔号</span>{escape(str(source))}</p>
  """




_TRUST_MARKER_VISUAL = {
    "无标记": ("none", "无"),
    "已关注": ("watch", "已关注"),
    "重点关注": ("focus", "重点关注"),
}


def _render_custody_mark_select(field: str, value: str, options: list[str], item: dict) -> str:
    current = value if value in options else TRUST_MARKER_DEFAULT
    tone, short = _TRUST_MARKER_VISUAL.get(current, ("none", current))
    menu_items = ""
    for opt in options:
        opt_tone, opt_short = _TRUST_MARKER_VISUAL.get(opt, ("none", opt))
        active = " is-active" if opt == current else ""
        menu_items += (
            f'<button type="button" class="trust-marker-option{active}" '
            f'data-value="{escape(opt)}" role="option" '
            f'aria-selected="{"true" if opt == current else "false"}">'
            f'<span class="trust-marker-dot tone-{opt_tone}" aria-hidden="true"></span>'
            f'<span>{escape(opt)}</span>'
            f"</button>"
        )
    return f"""
        <div class="trust-marker-cell" data-field="{escape(field)}"
             data-trust-product-id="{item['trust_product_id']}"
             data-asset-code="{escape(item['asset_code'])}"
             data-data-date="{escape(item['data_date'])}"
             data-value="{escape(current)}">
            <button type="button" class="trust-marker-badge tone-{tone}"
                    title="信托标记：{escape(current)}"
                    aria-label="信托标记：{escape(current)}，点击修改"
                    aria-haspopup="listbox" aria-expanded="false">
                <span class="trust-marker-dot tone-{tone}" aria-hidden="true"></span>
                <span class="trust-marker-label">{escape(short)}</span>
            </button>
            <div class="trust-marker-menu" role="listbox" hidden>
                {menu_items}
            </div>
        </div>
    """


def _workbench_entry_href(
    item: dict,
    *,
    tab_bucket: str | None,
    filters: dict | None,
    new_case: bool = False,
    new_entry: bool = False,
) -> str:
    """从资产组合进工作台：一次性带入组合筛选与资产（不记录 return_to）。"""
    del tab_bucket  # Tab 仅用于组合页展示，不写入工作台筛选
    ac_raw = str(item.get("asset_code") or item["custody_asset_code"])
    pid = item["trust_product_id"]
    f = filters or {}
    parts = [
        f"asset_code={quote(ac_raw)}",
        f"trust_product_id={pid}",
        "followup_expanded=1",
    ]
    product_ids = f.get("trust_product_ids")
    if product_ids is None:
        parts.append("list_product_id=")
    elif len(product_ids) == 1:
        parts.append(f"list_product_id={int(product_ids[0])}")
    else:
        for p in product_ids:
            parts.append(f"list_product_ids={int(p)}")

    buckets = f.get("delinquency_buckets") or (
        [f["delinquency_bucket"]] if f.get("delinquency_bucket") else None
    )
    if buckets:
        for b in buckets:
            parts.append(f"delinquency_buckets={quote(str(b))}")
    else:
        parts.append("delinquency_bucket=")

    markers = f.get("trust_markers") or (
        [f["trust_marker"]] if f.get("trust_marker") else None
    )
    for m in markers or []:
        parts.append(f"trust_markers={quote(str(m))}")

    statuses = f.get("internal_statuses") or (
        [f["internal_status"]] if f.get("internal_status") else None
    )
    for s in statuses or []:
        parts.append(f"followup_statuses={quote(str(s))}")

    cities = f.get("cities") or ([f["city"]] if f.get("city") else None)
    for c in cities or []:
        parts.append(f"cities={quote(str(c))}")

    dd = item.get("data_date")
    if dd:
        parts.append(f"data_date={quote(str(dd))}")
    if new_case:
        parts.append("new_followup_case=1")
    if new_entry:
        parts.append("new_followup=1")
    return "/overdue/workbench?" + "&".join(parts)


def _render_internal_status_cell(
    item: dict,
    *,
    tab_bucket: str | None = None,
    filters: dict | None = None,
) -> str:
    """只读内部状态：绿灯 / 橙计数 / 黄绿渐变「本周结算」；悬停显眼的新增 +。"""
    status = str(item.get("internal_status") or INTERNAL_STATUS_DEFAULT)
    # 状态灯：查看该事项最近一条跟进记录
    view_latest = _workbench_entry_href(
        item, tab_bucket=tab_bucket, filters=filters, new_case=False, new_entry=False
    )
    # +：新建跟进记录（有事项则开新建记录页；无事项由工作台回落到新建事项）
    new_entry = _workbench_entry_href(
        item, tab_bucket=tab_bucket, filters=filters, new_case=False, new_entry=True
    )

    problem_match = re.fullmatch(r"待跟进\((\d+)\)", status)
    settled_match = re.fullmatch(r"本周结算\((\d+)\)", status)
    if problem_match:
        n = problem_match.group(1)
        status_html = (
            f'<a class="internal-status-link" href="{view_latest}" '
            f'title="待跟进({escape(n)})" aria-label="待跟进 {escape(n)} 件，查看最近跟进">'
            f'<span class="status-count">{escape(n)}</span></a>'
        )
    elif settled_match:
        m = settled_match.group(1)
        status_html = (
            f'<a class="internal-status-link" href="{view_latest}" '
            f'title="本周结算({escape(m)})" aria-label="本周结算 {escape(m)} 件，查看最近跟进">'
            f'<span class="status-count status-count--settled">{escape(m)}</span></a>'
        )
    else:
        status_html = (
            f'<a class="internal-status-link" href="{view_latest}" '
            f'title="正常" aria-label="正常，查看最近跟进">'
            f'<span class="status-dot" aria-hidden="true"></span></a>'
        )
    return (
        f'<div class="internal-status-cell">'
        f"{status_html}"
        f'<a class="internal-status-add" href="{new_entry}" '
        f'title="新建跟进记录" aria-label="新建跟进记录">+</a>'
        f"</div>"
    )


def _render_portfolio_table_head(*, overdue_col_label: str | None = None) -> str:
    cells = []
    for sort_key, label, sort_type in PORTFOLIO_LIST_COLUMNS:
        if sort_key == "overdue_sort" and overdue_col_label:
            label = overdue_col_label
        if sort_key and sort_type:
            cells.append(
                f'<th class="sortable" data-sort="{escape(sort_key)}" '
                f'data-sort-type="{escape(sort_type)}">{escape(label)}</th>'
            )
        else:
            cells.append(f"<th>{escape(label)}</th>")
    return "".join(cells)


def _portfolio_row_sort_attrs(item: dict) -> str:
    parts = []
    for sort_key, _, sort_type in PORTFOLIO_LIST_COLUMNS:
        if not sort_key:
            continue
        raw = item.get(sort_key)
        if sort_type == "number":
            val = "" if raw is None else str(float(raw))
        else:
            val = "" if raw is None else str(raw)
        parts.append(f'data-sort-{sort_key}="{escape(val)}"')
    return " ".join(parts)


def _render_portfolio_tfoot(totals: dict) -> str:
    count = int(totals.get("count") or 0)
    return f"""
        <tfoot>
            <tr class="portfolio-totals">
                <td colspan="{PORTFOLIO_LABEL_COL_COUNT}">
                    <strong>合计（本 Tab · {count} 条）</strong>
                </td>
                <td class="num">{fmt_money(float(totals.get("initial_transfer_amount") or 0))}</td>
                <td class="num">{fmt_money(float(totals.get("repaid_amount") or 0))}</td>
                <td class="num">{fmt_money(float(totals.get("remaining_amount") or 0))}</td>
            </tr>
        </tfoot>
    """


def _render_portfolio_table(
    items: list,
    *,
    totals: dict,
    empty_label: str = "暂无记录",
    overdue_col_label: str | None = None,
    tab_bucket: str | None = None,
    filters: dict | None = None,
) -> str:
    head = _render_portfolio_table_head(overdue_col_label=overdue_col_label)
    if not items:
        body = (
            f'<tr class="empty-row"><td colspan="{PORTFOLIO_COL_COUNT}" class="empty">'
            f"{escape(empty_label)}</td></tr>"
        )
    else:
        body = _render_overdue_custody_rows(
            items, tab_bucket=tab_bucket, filters=filters
        )
    foot = _render_portfolio_tfoot(totals)
    return f"""
        <table class="portfolio-table">
            <thead><tr>{head}</tr></thead>
            <tbody>{body}</tbody>
            {foot}
        </table>
    """


def _render_overdue_custody_rows(
    items: list,
    *,
    tab_bucket: str | None = None,
    filters: dict | None = None,
) -> str:
    rows = ""
    for item in items:
        is_es = item.get("delinquency_bucket") == "ES"
        if is_es:
            settlement = (
                item.get("settlement_date")
                or item.get("last_payment_date")
                or "—"
            )
            col5 = escape(str(settlement))
            col6 = escape(str(settlement))
        else:
            od = item.get("overdue_days")
            col5 = escape(str(od) if od is not None else "—")
            col6 = escape(item.get("last_payment_date") or "—")
        sort_attrs = _portfolio_row_sort_attrs(item)
        ac_attr = escape(str(item.get("asset_code") or item.get("custody_asset_code") or ""))
        rows += f"""
            <tr {sort_attrs} data-asset-code="{ac_attr}" id="portfolio-row-{ac_attr}">
                <td>{escape(item.get("asset_code") or "—")}</td>
                <td>{escape(item["custody_asset_code"])}</td>
                <td>{escape(item["trust_product_name"])}</td>
                <td>{escape(item.get("city") or "—")}</td>
                <td>{fmt_delinquency_badge(item["delinquency_bucket"])}</td>
                <td class="num">{col5}</td>
                <td>{col6}</td>
                <td>{_render_custody_mark_select("trust_marker", item.get("trust_marker", TRUST_MARKER_DEFAULT), TRUST_MARKER_OPTIONS, item)}</td>
                <td>{_render_internal_status_cell(item, tab_bucket=tab_bucket, filters=filters)}</td>
                <td>{escape(item.get("data_date") or "—")}</td>
                <td class="num">{fmt_money(item["initial_transfer_amount"])}</td>
                <td class="num">{fmt_money(item["repaid_amount"])}</td>
                <td class="num">{fmt_money(item["remaining_amount"])}</td>
            </tr>
        """
    return rows


def _render_custody_table_rows(items: list) -> str:
    return _render_overdue_custody_rows(items)


def _render_custody_es_table_rows(items: list) -> str:
    return _render_overdue_custody_rows(items)


def _render_reconciliation_table_rows(reconciliation: list) -> str:
    if not reconciliation:
        return '<tr class="recon-empty"><td colspan="11" class="empty">暂无核对记录</td></tr>'
    rows = ""
    for item in reconciliation:
        bal_ok = item["balance_passed"]
        cross_ok = item["cross_passed"]
        code_ok = item.get("code_mismatch_passed", True)
        custody_count = item.get("custody_count", 1)
        custody_note = f'<span class="recon-custody-count" title="含 {custody_count} 个托管房源号">×{custody_count}</span>' if custody_count > 1 else ""
        code_title = ""
        if not code_ok:
            code_title = (
                f' title="还款明细 {item.get("code_mismatch_count", 0)} 笔主编号与 trust_assets 不一致，'
                f'涉及 ¥{item.get("code_mismatch_amount", 0):,.2f}"'
            )
        rows += f"""
            <tr class="recon-row"
                data-balance-passed="{"1" if bal_ok else "0"}"
                data-cross-passed="{"1" if cross_ok else "0"}"
                data-code-mismatch-passed="{"1" if code_ok else "0"}"
                data-has-anomaly="{"1" if item["has_anomaly"] else "0"}">
                <td>{escape(item["asset_code"])}{custody_note}</td>
                <td>{escape(item["trust_product_name"])}</td>
                <td>{fmt_recon_money(item["balance_remainder"], passed=bal_ok)}</td>
                <td>{fmt_recon_money(item["remaining_amount"], passed=True)}</td>
                <td>{fmt_recon_money(item["initial_transfer_amount"], passed=True)}</td>
                <td>{fmt_recon_money(item["repaid_amount"], passed=True)}</td>
                <td>{fmt_cross_check_badge(cross_ok)}</td>
                <td{code_title}>{fmt_cross_check_badge(code_ok, pass_label="一致", fail_label="不一致")}</td>
                <td>{fmt_recon_money(item["monitor_repaid_amount"], passed=True)}</td>
                <td>{fmt_recon_money(item["repayment_detail_total"], passed=True)}</td>
            </tr>
        """
    return rows


def _render_code_mismatch_alert_banner(alerts: list) -> str:
    if not alerts:
        return ""
    lines = ""
    for alert in alerts[:10]:
        lines += (
            f"<li><strong>{escape(alert['canonical_asset_code'])}</strong> "
            f"（{escape(alert['trust_product_name'])}）："
            f"还款明细写入主编号 <code>{escape(alert['stored_asset_code'])}</code>，"
            f"{int(alert['row_count'])} 笔 / {fmt_money(float(alert['amount_sum']))}</li>"
        )
    more = ""
    if len(alerts) > 10:
        more = f'<li class="muted">… 另有 {len(alerts) - 10} 组编码不一致</li>'
    return f"""
        <div class="recon-code-alert" role="alert">
            <strong>编码不一致告警</strong>：以下还款明细的 <code>asset_code</code> 与底层资产权威主编号不符，将影响跨表核对与还款明细筛选。
            <ul>{lines}{more}</ul>
        </div>
    """


_MULTISELECT_COUNT_UNITS = {
    "trust-product": "产品",
    "delinquency-bucket": "等级",
    "trust-marker": "标记",
    "internal-status": "状态",
    "city": "城市",
}


def _multiselect_trigger_label(
    selected: list[str] | None,
    *,
    all_label: str,
    label_map: dict[str, str] | None = None,
    unit: str = "项",
) -> str:
    if not selected:
        return all_label
    labels = [(label_map or {}).get(v, v) for v in selected]
    if len(labels) == 1:
        return labels[0]
    return f"已选{len(labels)}{unit}"


def _render_str_multiselect(
    *,
    key: str,
    param_name: str,
    label: str,
    options: list[tuple[str, str]],
    selected: list[str] | None,
    all_label: str,
) -> str:
    """组合页字符串多选：selected=None 表示全部。"""
    all_mode = selected is None
    trigger = escape(
        _multiselect_trigger_label(
            selected,
            all_label=all_label,
            label_map=dict(options),
            unit=_MULTISELECT_COUNT_UNITS.get(key, "项"),
        )
    )
    opts_html = (
        f'<label class="multiselect-option multiselect-all">'
        f'<input type="checkbox" class="ms-all"{" checked" if all_mode else ""}> 全部</label>'
    )
    selected_set = set(selected or [])
    for value, text in options:
        checked = (not all_mode) and value in selected_set
        opts_html += (
            f'<label class="multiselect-option">'
            f'<input type="checkbox" class="ms-option" name="{escape(param_name)}" '
            f'value="{escape(value)}"{" checked" if checked else ""}> '
            f"{escape(text)}</label>"
        )
    return f"""
        <div class="filter-multiselect" data-multiselect="{escape(key)}">
            <span class="filter-multiselect-label">{escape(label)}</span>
            <button type="button" class="multiselect-trigger" aria-haspopup="listbox">{trigger}</button>
            <div class="multiselect-panel" hidden>
                {opts_html}
            </div>
        </div>
    """


def _trust_product_filter_label(products: list[dict], selected_ids: list[int] | None) -> str:
    if not selected_ids:
        return "全部信托产品"
    name_by_id = {int(p["id"]): str(p["name"]) for p in products}
    names = [name_by_id.get(pid, str(pid)) for pid in selected_ids]
    if len(names) == 1:
        return names[0]
    return f"已选{len(names)}产品"


def _render_trust_product_multiselect(
    products: list[dict],
    selected_ids: list[int] | None,
) -> str:
    all_mode = selected_ids is None
    trigger = escape(_trust_product_filter_label(products, selected_ids))
    options = (
        f'<label class="multiselect-option multiselect-all">'
        f'<input type="checkbox" class="ms-all tp-all"{" checked" if all_mode else ""}> 全部</label>'
    )
    for product in products:
        pid = int(product["id"])
        checked = (not all_mode) and (pid in selected_ids)
        options += (
            f'<label class="multiselect-option">'
            f'<input type="checkbox" class="ms-option tp-product" name="trust_product_ids" '
            f'value="{pid}"{" checked" if checked else ""}> '
            f'{escape(str(product["name"]))}</label>'
        )
    return f"""
        <div class="filter-multiselect" data-multiselect="trust-product">
            <span class="filter-multiselect-label">信托产品</span>
            <button type="button" class="multiselect-trigger" aria-haspopup="listbox">{trigger}</button>
            <div class="multiselect-panel" hidden>
                {options}
            </div>
        </div>
    """


def render_overdue_html(
    overview: dict,
    reconciliation: list,
    followups: list,
    *,
    filters: dict | None = None,
    products: list | None = None,
    code_mismatch_alerts: list | None = None,
    focus_asset: str | None = None,
    portfolio_tab: str | None = None,
):
    buckets = overview.get("top_overdue_by_bucket") or {}
    bucket_totals = overview.get("bucket_totals") or {}
    city_options_list = overview.get("issuance_city_options") or []
    tab_defs = [
        ("M1_PLUS", "M1+", buckets.get("M1_PLUS", [])),
        ("M1", "M1", buckets.get("M1", [])),
        ("M0_5", "M0.5", buckets.get("M0_5", [])),
        ("M0", "M0", buckets.get("M0", [])),
        ("ES", "ES（提前结清）", buckets.get("ES", [])),
    ]
    f = filters or {}
    buckets_sel = f.get("delinquency_buckets") or (
        [f["delinquency_bucket"]] if f.get("delinquency_bucket") else None
    )
    # 筛选仅单一等级时作为默认 Tab；否则用 portfolio_tab
    ui_tab = buckets_sel[0] if buckets_sel and len(buckets_sel) == 1 else portfolio_tab
    default_tab_idx = 0
    if ui_tab:
        for idx, (key, _, _) in enumerate(tab_defs):
            if key == ui_tab:
                default_tab_idx = idx
                break
    elif (filters or {}).get("asset_code") or (filters or {}).get("custody_asset_code") or any(
        (filters or {}).get(k)
        for k in (
            "trust_product_ids",
            "trust_markers",
            "internal_statuses",
            "cities",
            "has_followup",
        )
    ):
        for idx, (_, _, items) in enumerate(tab_defs):
            if items:
                default_tab_idx = idx
                break

    tab_buttons = ""
    tab_panels = ""
    for idx, (key, label, items) in enumerate(tab_defs):
        active = "active" if idx == default_tab_idx else ""
        tab_buttons += (
            f'<button type="button" class="tab-btn {active}" data-tab="{key}">'
            f'{escape(label)} ({len(items)})</button>'
        )
        panel_style = "" if idx == default_tab_idx else ' style="display:none"'
        totals = bucket_totals.get(key) or _bucket_amount_totals(items)
        overdue_label = "提前结清日期" if key == "ES" else None
        tab_panels += f"""
            <div class="tab-panel {active}" id="tab-{key}"{panel_style}>
                <div class="table-scroll-x">
                    {_render_portfolio_table(
                        items,
                        totals=totals,
                        empty_label="暂无资产",
                        overdue_col_label=overdue_label,
                        tab_bucket=key,
                        filters=filters or {},
                    )}
                </div>
            </div>
        """

    products = products or []
    selected_product_ids = f.get("trust_product_ids")
    trust_product_filter = _render_trust_product_multiselect(products, selected_product_ids)
    markers_sel = f.get("trust_markers") or (
        [f["trust_marker"]] if f.get("trust_marker") else None
    )
    statuses_sel = f.get("internal_statuses") or (
        [f["internal_status"]] if f.get("internal_status") else None
    )
    cities_sel = f.get("cities") or ([f["city"]] if f.get("city") else None)

    bucket_filter = _render_str_multiselect(
        key="delinquency-bucket",
        param_name="delinquency_buckets",
        label="等级",
        options=[
            ("ES", "ES（提前结清）"),
            ("M0", "M0"),
            ("M0_5", "M0.5"),
            ("M1", "M1"),
            ("M1_PLUS", "M1+"),
            ("M0_PLUS", "M0+"),
        ],
        selected=buckets_sel,
        all_label="全部等级",
    )
    marker_filter = _render_str_multiselect(
        key="trust-marker",
        param_name="trust_markers",
        label="信托标记",
        options=[(m, m) for m in TRUST_MARKER_OPTIONS],
        selected=markers_sel,
        all_label="全部信托标记",
    )
    status_filter = _render_str_multiselect(
        key="internal-status",
        param_name="internal_statuses",
        label="内部状态",
        options=[(s, s) for s in INTERNAL_STATUS_OPTIONS],
        selected=statuses_sel,
        all_label="全部内部状态",
    )
    city_filter = _render_str_multiselect(
        key="city",
        param_name="cities",
        label="城市",
        options=[(c, c) for c in city_options_list],
        selected=cities_sel,
        all_label="全部城市",
    )

    asset_q = escape(f.get("asset_code") or "")
    custody_q = escape(f.get("custody_asset_code") or "")

    filter_bar = f"""
        <form class="filter-form" method="get" action="/overdue">
            {trust_product_filter}
            {bucket_filter}
            {marker_filter}
            {status_filter}
            {city_filter}
            <label class="filter-field-code">资产主编号
                <input type="text" name="asset_code" value="{asset_q}" placeholder="模糊匹配">
            </label>
            <label class="filter-field-code">托管房源号
                <input type="text" name="custody_asset_code" value="{custody_q}" placeholder="模糊匹配">
            </label>
            <div class="filter-actions">
                <button type="submit" class="tab-btn">筛选</button>
                <a class="api-link" href="/overdue">清除</a>
            </div>
        </form>
    """

    recon_rows = _render_reconciliation_table_rows(reconciliation)
    recon_anomaly_count = sum(1 for item in reconciliation if item.get("has_anomaly"))
    recon_total_count = len(reconciliation)
    code_mismatch_alerts = code_mismatch_alerts or []
    code_mismatch_banner = _render_code_mismatch_alert_banner(code_mismatch_alerts)
    data_date = overview.get("data_date") or "—"
    selected_ids = overview.get("trust_product_ids")
    # 金额核对仍要求单产品；逾期天数重算支持多产品
    recalc_single_pid = selected_ids[0] if selected_ids and len(selected_ids) == 1 else None
    recon_disabled = "" if recalc_single_pid is not None else " disabled"
    recon_title = (
        ""
        if recalc_single_pid is not None
        else ' title="请先单选一个信托产品"'
    )
    recalc_disabled = ""
    recalc_title = ""
    recalc_hint_style = ' style="display:none;"'
    recon_data_date = data_date
    recon_recalc_payload = {"data_date": recon_data_date if recon_data_date != "—" else None}
    if recalc_single_pid is not None:
        recon_recalc_payload["trust_product_id"] = recalc_single_pid
    recon_recalc_payload_json = json.dumps(recon_recalc_payload, ensure_ascii=False)

    followup_count = len(followups)
    followup_rows = ""
    for item in followups:
        desc = str(item.get("description") or "").strip() or "—"
        if len(desc) > 48:
            desc = desc[:48] + "…"
        followup_rows += f"""
            <tr>
                <td>{escape(item.get("asset_code") or "—")}</td>
                <td>{escape(item.get("category") or "—")}</td>
                <td>{escape(FOLLOWUP_STATUS_LABELS.get(item["status"], item["status"]))}</td>
                <td>{escape(_format_display_timestamp(item.get("created_at") or item.get("opened_at")))}</td>
                <td>{escape(desc)}</td>
                <td>{escape(_followup_entry_summary_display(item))}</td>
            </tr>
        """
    if not followup_rows:
        followup_rows = '<tr><td colspan="6" class="empty">暂无跟进事项</td></tr>'

    header_meta = _render_overdue_header_meta(overview)
    recalc_payload = {}
    if selected_ids:
        recalc_payload["trust_product_ids"] = list(selected_ids)
    recalc_payload_json = json.dumps(recalc_payload, ensure_ascii=False)
    today_str = date.today().isoformat()
    product_count_for_confirm = len(selected_ids) if selected_ids else "全部"

    amounts = overview.get("amounts") or _zero_overdue_kpi_amounts()
    bd = overview.get("breakdown") or {}
    kpi_cards = (
        _render_overdue_bucket_kpi_card(
            "资产规模（Exposure）",
            overview["exposure_total"],
            amounts["exposure"],
            hint=f"ES+M0+M0.5+M1+M1+ 总风险暴露 · 资产 {overview['total_asset_code_count']} 个",
        )
        + _render_overdue_bucket_kpi_card(
            "提前结清（ES）",
            bd.get("ES", 0),
            amounts["ES"],
            value_css="ok",
            hint="应还款为 0，非逾期",
            use_repaid=True,
        )
        + _render_overdue_bucket_kpi_card(
            "正常（M0）",
            bd.get("M0", 0),
            amounts["M0"],
            value_css="ok",
            hint="逾期天数 ≤0",
        )
        + _render_overdue_bucket_kpi_card(
            "逾期资产（M0+）",
            overview["overdue_total"],
            amounts["overdue"],
            value_css="warn",
            hint="M0.5+M1+M1+，不含 ES / M0",
        )
        + _render_overdue_bucket_kpi_card(
            "M0.5",
            bd.get("M0.5", 0),
            amounts["M0_5"],
            value_css="m0_5",
            hint="逾期 1–15 天",
        )
        + _render_overdue_bucket_kpi_card(
            "M1",
            bd.get("M1", 0),
            amounts["M1"],
            value_css="m1",
            hint="逾期 16–30 天",
        )
        + _render_overdue_bucket_kpi_card(
            "M1+",
            bd.get("M1+", 0),
            amounts["M1_PLUS"],
            value_css="warn",
            hint="逾期 >30 天",
        )
        + f"""
            <div class="card">
                <div class="card-label">核对异常</div>
                <div class="card-value warn">{overview["reconciliation_failed_count"]}</div>
                <div class="card-hint">托管房源口径</div>
            </div>
            <div class="card">
                <div class="card-label">跟进中台账</div>
                <div class="card-value">{followup_count}</div>
                <div class="card-hint">当前筛选资产下事项数</div>
            </div>
        """
    )

    m0_5_bucket_color = DELINQUENCY_BUCKET_COLORS["M0_5"]
    m1_bucket_color = DELINQUENCY_BUCKET_COLORS["M1"]

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>逾期管理 · 房地产资产证券化平台</title>
    <style>
        {PAGE_CHROME_CSS}
        {STANDARD_HEADER_CSS}
        {BTN_CSS}
        header {{ margin-bottom: 2rem; }}
        header p {{ margin-top: 0.5rem; color: #94a3b8; font-size: 0.95rem; }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(9, minmax(0, 1fr));
            gap: 0.75rem;
            margin-bottom: 2rem;
        }}
        .card {{
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 1rem;
            backdrop-filter: blur(8px);
        }}
        .card-label {{ font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.35rem; }}
        .card-value {{ font-size: 1.35rem; font-weight: 700; color: #f8fafc; }}
        .card-value.warn {{ color: #f87171; }}
        .card-value.ok {{ color: #34d399; }}
        .card-value.m0_5 {{ color: {m0_5_bucket_color}; }}
        .card-value.m1 {{ color: {m1_bucket_color}; }}
        .card-amounts {{
            font-size: 0.68rem; color: #94a3b8; margin-top: 0.35rem;
            line-height: 1.35; word-break: break-all;
        }}
        .section {{ margin-top: 1.5rem; }}
        .section-title {{
            font-size: 1.05rem; font-weight: 600; color: #f8fafc;
            margin-bottom: 0.75rem;
            display: flex; justify-content: space-between; align-items: center;
            gap: 0.75rem; flex-wrap: wrap;
        }}
        .section-title-row {{
            display: flex; justify-content: space-between; align-items: center;
            flex-wrap: wrap; gap: 0.75rem; margin-bottom: 0.35rem;
        }}
        .section-title-row .section-title {{ margin-bottom: 0; }}
        .recon-meta {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.75rem; line-height: 1.5; }}
        .recon-meta strong {{ color: #e2e8f0; font-weight: 600; }}
        .recon-custody-count {{ font-size: 0.72rem; color: #64748b; margin-left: 4px; vertical-align: middle; }}
        .api-link {{ font-size: 0.8rem; font-weight: 400; color: #64748b; }}
        {TABLE_SCROLL_CSS}
        th, td {{
            padding: 0.65rem 0.85rem;
            text-align: left;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }}
        th {{ color: #94a3b8; font-weight: 500; font-size: 0.78rem; }}
        td.num {{ color: #38bdf8; font-weight: 600; }}
        td.num.warn, span.num.warn {{ color: #f87171; }}
        span.num.ok {{ color: #34d399; }}
        .badge.ok-badge {{ background: #34d39922; color: #34d399; border-color: #34d39955; }}
        .badge.fail-badge {{ background: #f8717122; color: #f87171; border-color: #f8717155; }}
        .filter-bar {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.75rem; align-items: center; }}
        .filter-bar .muted-count {{ font-size: 0.78rem; color: #64748b; margin-left: auto; }}
        .filter-form {{
            display: flex; flex-wrap: nowrap; gap: 0.4rem; align-items: flex-end;
            margin-bottom: 0.85rem; padding-bottom: 0.85rem;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            /* 勿用 overflow:auto，会裁切绝对定位的多选下拉 */
            overflow: visible;
            position: relative;
            z-index: 40;
        }}
        .filter-form label {{
            display: flex; flex-direction: column; gap: 0.2rem;
            font-size: 0.72rem; color: #94a3b8; min-width: 0; flex: 0 1 auto;
        }}
        .filter-form select, .filter-form input[type="text"] {{
            padding: 0.3rem 0.45rem; border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.15);
            background: rgba(0,0,0,0.2); color: #e2e8f0; font-size: 0.8rem;
            box-sizing: border-box;
        }}
        .filter-field-code {{ flex: 0 1 8.5rem; }}
        .filter-field-code input[type="text"] {{ width: 8.5rem; }}
        .filter-actions {{
            display: flex; align-items: center; gap: 0.45rem;
            flex: 0 0 auto; padding-bottom: 0.1rem; white-space: nowrap;
        }}
        .filter-multiselect {{
            position: relative;
            display: flex;
            flex-direction: column;
            gap: 0.2rem;
            min-width: 6.5rem;
            flex: 0 1 8rem;
            z-index: 1;
        }}
        .filter-multiselect.is-open {{
            z-index: 200;
        }}
        .filter-multiselect-label {{
            font-size: 0.72rem;
            color: #94a3b8;
        }}
        .multiselect-trigger {{
            padding: 0.3rem 0.45rem;
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.15);
            background: rgba(0,0,0,0.2);
            color: #e2e8f0;
            font-size: 0.8rem;
            text-align: left;
            cursor: pointer;
            width: 100%;
            max-width: 9.5rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            box-sizing: border-box;
        }}
        .multiselect-panel {{
            position: absolute;
            top: calc(100% + 0.25rem);
            left: 0;
            z-index: 300;
            min-width: 220px;
            max-height: 240px;
            overflow: auto;
            padding: 0.45rem;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.12);
            background: #0f172a;
            box-shadow: 0 10px 30px rgba(0,0,0,0.45);
        }}
        .multiselect-option {{
            display: flex;
            flex-direction: row;
            align-items: center;
            justify-content: flex-start;
            gap: 0.5rem;
            padding: 0.3rem 0.35rem;
            font-size: 0.82rem;
            color: #e2e8f0;
            cursor: pointer;
            white-space: nowrap;
            min-width: 0;
        }}
        .filter-form label.multiselect-option {{
            flex-direction: row;
            align-items: center;
            min-width: 0;
        }}
        .multiselect-option input[type="checkbox"] {{
            flex: 0 0 auto;
            width: 0.95rem;
            height: 0.95rem;
            margin: 0;
            cursor: pointer;
        }}
        .multiselect-option:hover {{ color: #f8fafc; }}
        .multiselect-all {{
            border-bottom: 1px solid rgba(255,255,255,0.08);
            margin-bottom: 0.25rem;
            padding-bottom: 0.35rem;
        }}
        .btn-recalc:disabled {{
            opacity: 0.45;
            cursor: not-allowed;
        }}
        .internal-status-cell {{
            display: inline-flex; align-items: center; gap: 0.35rem;
            min-height: 1.6rem;
        }}
        .internal-status-link {{
            display: inline-flex; align-items: center; justify-content: center;
            text-decoration: none; line-height: 1;
        }}
        .status-dot,
        .status-count {{
            display: inline-flex; align-items: center; justify-content: center;
            width: 1.35rem; height: 1.35rem; min-width: 1.35rem;
            border-radius: 50%; box-sizing: border-box;
        }}
        .status-dot {{
            background: #22c55e;
            box-shadow: 0 0 0 2px rgba(34,197,94,0.22);
        }}
        .status-count {{
            padding: 0;
            font-size: 0.72rem; font-weight: 700; line-height: 1;
            color: #0f172a; background: #f59e0b;
            box-shadow: 0 0 0 1px rgba(245,158,11,0.35);
        }}
        .status-count--settled {{
            border-radius: 999px;
            background: linear-gradient(135deg, #fbbf24, #34d399);
            box-shadow: 0 0 0 1px rgba(52,211,153,0.35);
        }}
        .internal-status-add {{
            display: inline-flex; align-items: center; justify-content: center;
            width: 1.2rem; height: 1.2rem; border-radius: 4px;
            font-size: 0.95rem; font-weight: 700; line-height: 1;
            color: #64748b; text-decoration: none;
            opacity: 0.28; border: 1px solid transparent;
            transition: opacity 0.15s ease, color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
        }}
        tr:hover .internal-status-add,
        .internal-status-cell:focus-within .internal-status-add,
        .internal-status-add:focus-visible {{
            opacity: 1; color: #e2e8f0;
            border-color: rgba(56,189,248,0.45);
            background: rgba(56,189,248,0.12);
        }}
        .trust-marker-cell {{
            position: relative; display: inline-flex; align-items: center;
        }}
        .trust-marker-badge {{
            display: inline-flex; align-items: center; gap: 0.35rem;
            padding: 0.15rem 0.45rem; border-radius: 999px;
            border: 1px solid rgba(255,255,255,0.12);
            background: rgba(255,255,255,0.04); color: #cbd5e1;
            font-size: 0.78rem; cursor: pointer; line-height: 1.2;
        }}
        .trust-marker-badge:hover,
        .trust-marker-cell.is-open .trust-marker-badge {{
            border-color: rgba(56,189,248,0.4);
            background: rgba(56,189,248,0.08);
        }}
        .trust-marker-dot {{
            width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
            background: #64748b;
        }}
        .trust-marker-dot.tone-none {{
            background: transparent; border: 1.5px solid #64748b;
        }}
        .trust-marker-dot.tone-watch {{ background: #f59e0b; }}
        .trust-marker-dot.tone-focus {{ background: #f87171; }}
        .trust-marker-badge.tone-none {{ color: #94a3b8; }}
        .trust-marker-badge.tone-watch {{ color: #fbbf24; }}
        .trust-marker-badge.tone-focus {{ color: #fecaca; }}
        .trust-marker-menu {{
            position: absolute; top: calc(100% + 0.25rem); left: 0; z-index: 40;
            min-width: 8.5rem; padding: 0.25rem;
            border-radius: 8px; border: 1px solid rgba(148,163,184,0.25);
            background: #0f172a; box-shadow: 0 8px 24px rgba(0,0,0,0.45);
            display: flex; flex-direction: column; gap: 0.1rem;
        }}
        .trust-marker-menu[hidden] {{ display: none !important; }}
        .trust-marker-option {{
            display: flex; align-items: center; gap: 0.4rem;
            width: 100%; padding: 0.35rem 0.45rem; border: none; border-radius: 6px;
            background: transparent; color: #e2e8f0; font-size: 0.78rem;
            cursor: pointer; text-align: left;
        }}
        .trust-marker-option:hover {{ background: rgba(56,189,248,0.12); }}
        .trust-marker-option.is-active {{ background: rgba(56,189,248,0.18); }}
        .trust-marker-cell.saving {{ opacity: 0.6; }}
        .trust-marker-cell.saved .trust-marker-badge {{ border-color: #34d399; }}
        .trust-marker-cell.error .trust-marker-badge {{ border-color: #f87171; }}
        .badge {{
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 999px;
            font-size: 0.75rem;
            background: rgba(56, 189, 248, 0.15);
            color: #7dd3fc;
            border: 1px solid rgba(56, 189, 248, 0.25);
        }}
        .empty {{ color: #64748b; text-align: center; }}
        .card-hint {{ font-size: 0.72rem; color: #64748b; margin-top: 0.35rem; line-height: 1.3; }}
        .tabs {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.75rem; position: relative; z-index: 1; }}
        .portfolio-panel {{ overflow: visible; position: relative; z-index: 2; }}
        .portfolio-panel .tab-panel {{ position: relative; z-index: 1; }}
        tr.portfolio-row-focus td {{
            background: rgba(56, 189, 248, 0.14);
            box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.35);
        }}
        .portfolio-panel .table-scroll-x {{
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            max-width: 100%;
        }}
        .portfolio-panel .table-scroll-x table {{
            width: max-content;
            min-width: 100%;
            border-collapse: collapse;
        }}
        .portfolio-table th.sortable {{
            cursor: pointer;
            user-select: none;
        }}
        .portfolio-table th.sortable:hover {{ color: #e2e8f0; }}
        .portfolio-table th.sortable.sort-asc::after {{ content: ' ▲'; font-size: 0.65rem; }}
        .portfolio-table th.sortable.sort-desc::after {{ content: ' ▼'; font-size: 0.65rem; }}
        tr.portfolio-totals td {{
            font-weight: 600;
            border-top: 2px solid rgba(255, 255, 255, 0.15);
            background: rgba(255, 255, 255, 0.04);
        }}
        tr.portfolio-totals td:first-child {{ color: #e2e8f0; }}
        .header-row {{
            display: flex; justify-content: space-between; align-items: flex-start;
            flex-wrap: wrap; gap: 1rem;
        }}
        .recalc-msg {{
            margin-top: 0.75rem; padding: 0.6rem 0.85rem; border-radius: 8px; font-size: 0.85rem;
            background: rgba(52, 211, 153, 0.12); border: 1px solid rgba(52, 211, 153, 0.35); color: #a7f3d0;
        }}
        .recalc-msg.err {{
            background: rgba(248, 113, 113, 0.12); border-color: rgba(248, 113, 113, 0.35); color: #fecaca;
        }}
        .recon-code-alert {{
            margin-bottom: 0.75rem; padding: 0.75rem 1rem; border-radius: 8px;
            background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.35);
            color: #fcd34d; font-size: 0.88rem; line-height: 1.5;
        }}
        .recon-code-alert ul {{ margin: 0.5rem 0 0 1.1rem; padding: 0; }}
        .recon-code-alert li {{ margin: 0.25rem 0; }}
        .meta-hint {{ font-size: 0.82rem; color: #64748b; }}
        .meta-warn {{ color: #fbbf24; }}
        header p strong {{ color: #e2e8f0; font-weight: 600; }}
        footer {{ margin-top: 2.5rem; text-align: center; font-size: 0.8rem; color: #64748b; }}
        @media (max-width: 1100px) {{
            .grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
        }}
        @media (max-width: 640px) {{
            .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
        }}
    </style>
</head>
<body class="overdue-page">
    <div class="container">
        <nav class="breadcrumb"><a href="/">首页</a> / 逾期管理</nav>
        <header>
            <div class="header-row">
                <div>
                    <h1>信托资产逾期管理</h1>
                    {header_meta}
                </div>
                <label class="recalc-asof" style="display:inline-flex;align-items:center;gap:0.4rem;margin-right:0.75rem;font-size:0.85rem;color:#94a3b8;">
                    重算日
                    <input type="date" id="recalc-as-of" value="{today_str}" style="background:#0f172a;border:1px solid rgba(255,255,255,0.15);color:#e2e8f0;border-radius:6px;padding:0.35rem 0.5rem;">
                </label>
                <button type="button" class="btn-recalc" id="btn-recalc-overdue"{recalc_disabled}{recalc_title}>重新计算逾期天数</button>
            </div>
            <p class="card-hint" id="recalc-hint"{recalc_hint_style}>金额核对仍需单选产品；逾期天数支持多产品，按各产品最新快照日分别重算。</p>
            <div id="recalc-message" class="recalc-msg" style="display:none;"></div>
        </header>

        <div class="grid">
            {kpi_cards}
        </div>

        <section class="section">
            <h2 class="section-title">
                资产组合管理
                <a class="api-link" href="/overdue/checks">查看全部 JSON</a>
            </h2>
            <div class="card portfolio-panel">
                {filter_bar}
                <div class="tabs">{tab_buttons}</div>
                {tab_panels}
            </div>
        </section>

        <section class="section">
            <div class="section-title-row">
                <h2 class="section-title">
                    金额核对
                    <a class="api-link" href="/overdue/reconciliation">JSON → /overdue/reconciliation</a>
                </h2>
                <button type="button" class="btn-recalc" id="btn-recalc-reconciliation"{recon_disabled}{recon_title}>重新计算金额核对</button>
            </div>
            <p class="recon-meta">
                金额核对数据日期：<strong>{escape(recon_data_date)}</strong>
                · 核对基准：{escape(RECONCILIATION_BASIS_LABEL)}
                · 最近重算时间：<span id="recon-recalc-at">—</span>
            </p>
            <div id="recon-recalc-message" class="recalc-msg" style="display:none; margin-bottom:0.75rem;"></div>
            {code_mismatch_banner}
            <div class="card table-wrap">
                <div class="filter-bar" id="recon-filters">
                    <button type="button" class="tab-btn active" data-recon-filter="anomaly">仅异常</button>
                    <button type="button" class="tab-btn" data-recon-filter="all">全部</button>
                    <button type="button" class="tab-btn" data-recon-filter="balance-zero">剩余差额 = 0</button>
                    <button type="button" class="tab-btn" data-recon-filter="balance-nonzero">剩余差额 ≠ 0</button>
                    <button type="button" class="tab-btn" data-recon-filter="cross-pass">跨表检查通过</button>
                    <button type="button" class="tab-btn" data-recon-filter="cross-fail">跨表检查不通过</button>
                    <button type="button" class="tab-btn" data-recon-filter="code-mismatch">编码不一致</button>
                    <span class="muted-count" id="recon-visible-count">显示 {recon_anomaly_count} / {recon_total_count}</span>
                </div>
                <table id="recon-table">
                    <thead>
                        <tr>
                            <th>资产主编号</th><th>信托产品</th><th>剩余差额</th>
                            <th>剩余还款金额或剩余应还款金额</th><th>初始受让金额</th><th>已还款金额</th>
                            <th>跨表检查</th><th>编码检查</th><th>监控表已还款金额</th><th>还款明细汇总</th>
                        </tr>
                    </thead>
                    <tbody>{recon_rows}</tbody>
                </table>
            </div>
        </section>

        <section class="section">
            <h2 class="section-title">
                跟进事项 · {followup_count}
                <a class="api-link" href="/overdue/followups">JSON → /overdue/followups</a>
            </h2>
            <div class="card table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>资产主编号</th><th>分类</th><th>状态</th>
                            <th>创建时间</th><th>描述</th><th>跟进摘要</th>
                        </tr>
                    </thead>
                    <tbody>{followup_rows}</tbody>
                </table>
            </div>
        </section>

        <footer>Real Estate Securitization Platform</footer>
    </div>
    <script>
    (function() {{
        var filterForm = document.querySelector('form.filter-form');
        if (!filterForm) return;

        var ALL_LABELS = {{
            'trust-product': '全部信托产品',
            'delinquency-bucket': '全部等级',
            'trust-marker': '全部信托标记',
            'internal-status': '全部内部状态',
            'city': '全部城市'
        }};
        var COUNT_UNITS = {{
            'trust-product': '产品',
            'delinquency-bucket': '等级',
            'trust-marker': '标记',
            'internal-status': '状态',
            'city': '城市'
        }};

        function updateMsTrigger(root) {{
            var trigger = root.querySelector('.multiselect-trigger');
            var allBox = root.querySelector('.ms-all');
            var key = root.getAttribute('data-multiselect') || '';
            var allLabel = ALL_LABELS[key] || '全部';
            var unit = COUNT_UNITS[key] || '项';
            if (!trigger) return;
            if (allBox && allBox.checked) {{
                trigger.textContent = allLabel;
                return;
            }}
            var names = [];
            root.querySelectorAll('.ms-option').forEach(function(box) {{
                if (box.checked) names.push(box.parentElement.textContent.trim());
            }});
            if (!names.length) trigger.textContent = allLabel;
            else if (names.length === 1) trigger.textContent = names[0];
            else trigger.textContent = '已选' + names.length + unit;
        }}

        function setMsOpen(root, open) {{
            if (!root) return;
            root.classList.toggle('is-open', !!open);
            var panel = root.querySelector('.multiselect-panel');
            if (panel) panel.hidden = !open;
        }}
        function closeAllMs(except) {{
            filterForm.querySelectorAll('[data-multiselect]').forEach(function(root) {{
                if (except && root === except) return;
                setMsOpen(root, false);
            }});
        }}
        filterForm.querySelectorAll('[data-multiselect]').forEach(function(root) {{
            var panel = root.querySelector('.multiselect-panel');
            var trigger = root.querySelector('.multiselect-trigger');
            var allBox = root.querySelector('.ms-all');
            if (trigger && panel) {{
                trigger.addEventListener('click', function(ev) {{
                    ev.stopPropagation();
                    var willOpen = panel.hidden;
                    closeAllMs(root);
                    setMsOpen(root, willOpen);
                }});
            }}
            document.addEventListener('click', function(ev) {{
                if (!root.contains(ev.target)) setMsOpen(root, false);
            }});
            if (allBox) {{
                allBox.addEventListener('change', function() {{
                    root.querySelectorAll('.ms-option').forEach(function(box) {{
                        if (allBox.checked) {{ box.checked = false; box.disabled = true; }}
                        else {{ box.disabled = false; }}
                    }});
                    updateMsTrigger(root);
                }});
                if (allBox.checked) {{
                    root.querySelectorAll('.ms-option').forEach(function(box) {{
                        box.disabled = true;
                    }});
                }}
            }}
            root.querySelectorAll('.ms-option').forEach(function(box) {{
                box.addEventListener('change', function() {{
                    if (box.checked && allBox) {{
                        allBox.checked = false;
                        root.querySelectorAll('.ms-option').forEach(function(other) {{
                            other.disabled = false;
                        }});
                    }}
                    updateMsTrigger(root);
                }});
            }});
            updateMsTrigger(root);
        }});

        filterForm.addEventListener('submit', function(ev) {{
            ev.preventDefault();
            var params = new URLSearchParams();
            filterForm.querySelectorAll('input, select, textarea').forEach(function(el) {{
                if (!el.name || el.disabled) return;
                if (el.classList.contains('ms-all')) return;
                if (el.classList.contains('ms-option')) {{
                    if (el.checked) params.append(el.name, el.value);
                    return;
                }}
                var val = (el.value || '').trim();
                if (val) params.set(el.name, val);
            }});
            var qs = params.toString();
            window.location = filterForm.getAttribute('action') + (qs ? '?' + qs : '');
        }});
    }})();

    function applyReconFilter(mode) {{
        var rows = document.querySelectorAll('#recon-table tbody tr.recon-row');
        var visible = 0;
        rows.forEach(function(row) {{
            var bal = row.getAttribute('data-balance-passed') === '1';
            var cross = row.getAttribute('data-cross-passed') === '1';
            var codeOk = row.getAttribute('data-code-mismatch-passed') === '1';
            var anomaly = row.getAttribute('data-has-anomaly') === '1';
            var show = false;
            if (mode === 'all') show = true;
            else if (mode === 'anomaly') show = anomaly;
            else if (mode === 'balance-zero') show = bal;
            else if (mode === 'balance-nonzero') show = !bal;
            else if (mode === 'cross-pass') show = cross;
            else if (mode === 'cross-fail') show = !cross;
            else if (mode === 'code-mismatch') show = !codeOk;
            row.style.display = show ? '' : 'none';
            if (show) visible += 1;
        }});
        var empty = document.querySelector('#recon-table tbody tr.recon-empty');
        if (empty) empty.style.display = rows.length ? 'none' : '';
        var counter = document.getElementById('recon-visible-count');
        if (counter) counter.textContent = '显示 ' + visible + ' / {recon_total_count}';
    }}
    document.querySelectorAll('[data-recon-filter]').forEach(function(btn) {{
        btn.addEventListener('click', function() {{
            document.querySelectorAll('[data-recon-filter]').forEach(function(b) {{
                b.classList.remove('active');
            }});
            btn.classList.add('active');
            applyReconFilter(btn.getAttribute('data-recon-filter'));
        }});
    }});
    applyReconFilter('anomaly');

    (function() {{
        var reconAtEl = document.getElementById('recon-recalc-at');
        var storedAt = sessionStorage.getItem('reconciliation_recalc_at');
        if (reconAtEl && storedAt) {{
            try {{
                var d = new Date(storedAt);
                if (!isNaN(d.getTime())) {{
                    var p = function(n) {{ return String(n).padStart(2, '0'); }};
                    reconAtEl.textContent = d.getFullYear() + '-' + p(d.getMonth()+1) + '-' + p(d.getDate())
                        + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
                }} else {{
                    reconAtEl.textContent = storedAt.slice(0, 16).replace('T', ' ');
                }}
            }} catch (e) {{
                reconAtEl.textContent = storedAt.slice(0, 16).replace('T', ' ');
            }}
        }}
    }})();

    (function() {{
        var btn = document.getElementById('btn-recalc-reconciliation');
        var msgEl = document.getElementById('recon-recalc-message');
        var reconPayload = {recon_recalc_payload_json};
        if (!btn) return;
        btn.addEventListener('click', function() {{
            if (!confirm('重新计算金额核对将基于当前资产监控快照和还款明细重新计算，是否继续？')) return;
            btn.disabled = true;
            if (msgEl) {{ msgEl.style.display = 'none'; msgEl.classList.remove('err'); }}
            fetch('/overdue/reconciliation/recalculate', {{
                method: 'POST',
                credentials: 'same-origin',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(reconPayload)
            }}).then(function(res) {{
                return res.json().then(function(data) {{
                    if (!res.ok) throw new Error(data.detail || '重算失败');
                    if (data.as_of) sessionStorage.setItem('reconciliation_recalc_at', data.as_of);
                    var text = data.message || ('已重新计算 ' + (data.recalculated_count || 0) + ' 条托管房源金额核对');
                    if (msgEl) {{
                        msgEl.textContent = text;
                        msgEl.style.display = 'block';
                    }}
                    setTimeout(function() {{ window.location.reload(); }}, 1200);
                }});
            }}).catch(function(err) {{
                btn.disabled = false;
                if (msgEl) {{
                    msgEl.textContent = err.message || '重算失败';
                    msgEl.classList.add('err');
                    msgEl.style.display = 'block';
                }}
            }});
        }});
    }})();

    (function() {{
        var btn = document.getElementById('btn-recalc-overdue');
        var msgEl = document.getElementById('recalc-message');
        var asOfEl = document.getElementById('recalc-as-of');
        var recalcPayload = {recalc_payload_json};
        var productCountLabel = {json.dumps(str(product_count_for_confirm), ensure_ascii=False)};
        if (!btn) return;
        btn.addEventListener('click', function() {{
            var asOf = (asOfEl && asOfEl.value) ? asOfEl.value : '{today_str}';
            var ids = recalcPayload.trust_product_ids || [];
            var isAll = !ids.length;
            var countText = isAll ? '全部有监控快照的产品' : (ids.length + ' 个产品');
            if (isAll || ids.length > 1) {{
                if (!confirm('将按重算日 ' + asOf + ' 重算逾期天数\\n范围：' + countText + '\\n按各产品最新监控快照日分别更新，是否继续？')) return;
            }} else {{
                if (!confirm('将按重算日 ' + asOf + ' 重新计算逾期天数，是否继续？')) return;
            }}
            var body = Object.assign({{}}, recalcPayload, {{ as_of: asOf }});
            btn.disabled = true;
            if (msgEl) {{ msgEl.style.display = 'none'; msgEl.classList.remove('err'); }}
            fetch('/overdue/recalculate', {{
                method: 'POST',
                credentials: 'same-origin',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(body)
            }}).then(function(res) {{
                return res.json().then(function(data) {{
                    if (!res.ok) throw new Error(data.detail || '重算失败');
                    var text = data.message || ('已重新计算 ' + (data.updated_count || 0) + ' 条监控记录');
                    if (data.missing_repayment_count) {{
                        text += '，缺少还款日期 ' + data.missing_repayment_count + ' 条';
                    }}
                    if (data.overdue_days_as_of) {{
                        text += '（逾期天数截至 ' + data.overdue_days_as_of + '）';
                    }}
                    if (data.risk_hint) text += '。' + data.risk_hint;
                    if (msgEl) {{
                        msgEl.textContent = text;
                        msgEl.style.display = 'block';
                    }}
                    setTimeout(function() {{ window.location.reload(); }}, 1200);
                }});
            }}).catch(function(err) {{
                btn.disabled = false;
                if (msgEl) {{
                    msgEl.textContent = err.message || '重算失败';
                    msgEl.classList.add('err');
                    msgEl.style.display = 'block';
                }}
            }});
        }});
    }})();

    (function() {{
        var MARKER_VISUAL = {{
            '无标记': {{ tone: 'none', short: '无' }},
            '已关注': {{ tone: 'watch', short: '已关注' }},
            '重点关注': {{ tone: 'focus', short: '重点关注' }}
        }};

        function closeAllMarkerMenus(except) {{
            document.querySelectorAll('.trust-marker-cell.is-open').forEach(function(cell) {{
                if (except && cell === except) return;
                cell.classList.remove('is-open');
                var menu = cell.querySelector('.trust-marker-menu');
                var badge = cell.querySelector('.trust-marker-badge');
                if (menu) menu.hidden = true;
                if (badge) badge.setAttribute('aria-expanded', 'false');
            }});
        }}

        function applyMarkerVisual(cell, value) {{
            var vis = MARKER_VISUAL[value] || {{ tone: 'none', short: value }};
            cell.dataset.value = value;
            var badge = cell.querySelector('.trust-marker-badge');
            var label = cell.querySelector('.trust-marker-label');
            var dot = badge && badge.querySelector('.trust-marker-dot');
            if (badge) {{
                badge.className = 'trust-marker-badge tone-' + vis.tone;
                badge.title = '信托标记：' + value;
                badge.setAttribute('aria-label', '信托标记：' + value + '，点击修改');
            }}
            if (dot) dot.className = 'trust-marker-dot tone-' + vis.tone;
            if (label) label.textContent = vis.short;
            cell.querySelectorAll('.trust-marker-option').forEach(function(opt) {{
                var active = opt.dataset.value === value;
                opt.classList.toggle('is-active', active);
                opt.setAttribute('aria-selected', active ? 'true' : 'false');
            }});
        }}

        function saveMarker(cell, value) {{
            var field = cell.dataset.field || 'trust_marker';
            var payload = {{
                trust_product_id: parseInt(cell.dataset.trustProductId, 10),
                asset_code: cell.dataset.assetCode,
                data_date: cell.dataset.dataDate
            }};
            payload[field] = value;
            cell.classList.remove('saved', 'error');
            cell.classList.add('saving');
            fetch('/overdue/custody-marks', {{
                method: 'PATCH',
                credentials: 'same-origin',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(payload)
            }}).then(function(res) {{
                return res.json().then(function(data) {{
                    cell.classList.remove('saving');
                    if (!res.ok) {{
                        cell.classList.add('error');
                        throw new Error(data.detail || '保存失败');
                    }}
                    applyMarkerVisual(cell, value);
                    cell.classList.add('saved');
                    setTimeout(function() {{ cell.classList.remove('saved'); }}, 1200);
                }});
            }}).catch(function() {{
                cell.classList.remove('saving');
                cell.classList.add('error');
            }});
        }}

        document.querySelectorAll('.trust-marker-cell').forEach(function(cell) {{
            var badge = cell.querySelector('.trust-marker-badge');
            var menu = cell.querySelector('.trust-marker-menu');
            if (!badge || !menu) return;

            badge.addEventListener('click', function(e) {{
                e.stopPropagation();
                var open = !cell.classList.contains('is-open');
                closeAllMarkerMenus(open ? cell : null);
                cell.classList.toggle('is-open', open);
                menu.hidden = !open;
                badge.setAttribute('aria-expanded', open ? 'true' : 'false');
            }});

            menu.querySelectorAll('.trust-marker-option').forEach(function(opt) {{
                opt.addEventListener('click', function(e) {{
                    e.stopPropagation();
                    var value = opt.dataset.value;
                    closeAllMarkerMenus();
                    if (!value || value === cell.dataset.value) return;
                    saveMarker(cell, value);
                }});
            }});
        }});

        document.addEventListener('click', function() {{ closeAllMarkerMenus(); }});
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') closeAllMarkerMenus();
        }});
    }})();

    function activatePortfolioTab(key) {{
        if (!key) return false;
        var btn = document.querySelector('.tab-btn[data-tab="' + key + '"]');
        var panel = document.getElementById('tab-' + key);
        if (!btn || !panel) return false;
        document.querySelectorAll('.tab-btn[data-tab]').forEach(function(b) {{ b.classList.remove('active'); }});
        document.querySelectorAll('.tab-panel').forEach(function(p) {{
            p.style.display = 'none';
            p.classList.remove('active');
        }});
        btn.classList.add('active');
        panel.style.display = 'block';
        panel.classList.add('active');
        return true;
    }}

    document.querySelectorAll('.tab-btn[data-tab]').forEach(function(btn) {{
        btn.addEventListener('click', function() {{
            activatePortfolioTab(btn.getAttribute('data-tab'));
        }});
    }});

    (function restorePortfolioFocus() {{
        var focusAsset = {json.dumps(focus_asset or "")};
        var tabKey = {json.dumps(
            portfolio_tab
            or (filters or {}).get("delinquency_bucket")
            or ""
        )};
        if (tabKey) activatePortfolioTab(tabKey);
        if (!focusAsset) return;
        var row = document.getElementById('portfolio-row-' + focusAsset)
            || document.querySelector('tr[data-asset-code="' + focusAsset + '"]');
        if (!row) return;
        var panel = row.closest('.tab-panel');
        if (panel && panel.id && panel.id.indexOf('tab-') === 0) {{
            activatePortfolioTab(panel.id.slice(4));
        }}
        row.classList.add('portfolio-row-focus');
        try {{
            row.scrollIntoView({{ block: 'center', behavior: 'instant' }});
        }} catch (e1) {{
            try {{
                row.scrollIntoView({{ block: 'center', behavior: 'auto' }});
            }} catch (e2) {{
                row.scrollIntoView(true);
            }}
        }}
        setTimeout(function() {{ row.classList.remove('portfolio-row-focus'); }}, 2500);
    }})();

    (function() {{
        document.querySelectorAll('.portfolio-table').forEach(function(table) {{
            var thead = table.querySelector('thead');
            if (!thead) return;
            thead.querySelectorAll('th.sortable').forEach(function(th) {{
                th.addEventListener('click', function() {{
                    var key = th.getAttribute('data-sort');
                    var sortType = th.getAttribute('data-sort-type') || 'text';
                    var tbody = table.querySelector('tbody');
                    if (!tbody || !key) return;
                    var rows = Array.from(tbody.querySelectorAll('tr')).filter(function(row) {{
                        return !row.classList.contains('empty-row');
                    }});
                    if (!rows.length) return;
                    var dir = th.getAttribute('data-sort-dir') === 'asc' ? 'desc' : 'asc';
                    thead.querySelectorAll('th.sortable').forEach(function(h) {{
                        h.removeAttribute('data-sort-dir');
                        h.classList.remove('sort-asc', 'sort-desc');
                    }});
                    th.setAttribute('data-sort-dir', dir);
                    th.classList.add(dir === 'asc' ? 'sort-asc' : 'sort-desc');
                    var attr = 'data-sort-' + key;
                    rows.sort(function(a, b) {{
                        var av = a.getAttribute(attr) || '';
                        var bv = b.getAttribute(attr) || '';
                        var cmp;
                        if (sortType === 'number') {{
                            cmp = (parseFloat(av) || 0) - (parseFloat(bv) || 0);
                        }} else {{
                            cmp = av.localeCompare(bv, 'zh-CN');
                        }}
                        return dir === 'asc' ? cmp : -cmp;
                    }});
                    rows.forEach(function(row) {{ tbody.appendChild(row); }});
                }});
            }});
        }});
    }})();
    </script>
</body>
</html>"""


def fmt_risk_badge(level: str | None) -> str:
    if not level:
        return '<span class="badge">—</span>'
    label = f"{level} · {risk_hub.RISK_LEVEL_LABELS.get(level, level)}"
    color = risk_hub.RISK_LEVEL_COLORS.get(level, "#94a3b8")
    return (
        f'<span class="badge" style="background:{color}22;color:{color};'
        f'border-color:{color}55;">{escape(label)}</span>'
    )


def _fmt_risk_day_meta(item: dict) -> str:
    if item.get("is_es") or item.get("risk_level") == "ES":
        settlement = item.get("settlement_date") or item.get("last_payment_date") or "—"
        return f'<span>提前结清 {escape(str(settlement))}</span>'
    od = item.get("overdue_days")
    if od is None:
        return "<span>逾期 —</span>"
    return f"<span>逾期 {od}天</span>"


def fmt_sla_badge(status: str | None) -> str:
    if not status:
        return '<span class="badge">—</span>'
    label = risk_hub.SLA_STATUS_LABELS.get(status, status)
    color = {"on_time": "#34d399", "overdue": "#fbbf24", "breached": "#f87171"}.get(status, "#94a3b8")
    icon = "⚠️ " if status in ("overdue", "breached") else ""
    return (
        f'<span class="badge" style="background:{color}22;color:{color};'
        f'border-color:{color}55;">{icon}{escape(label)}</span>'
    )


def render_risk_workbench_html(data: dict):
    summary = data["summary"]
    queue = data["queue"]
    detail = data.get("detail")
    selected_id = data.get("selected_asset_id")

    queue_rows = ""
    for item in queue:
        active = "active" if item["trust_asset_id"] == selected_id else ""
        queue_rows += f"""
            <a class="queue-item {active}" href="/risk/workbench?trust_asset_id={item['trust_asset_id']}">
                <div class="queue-top">
                    <span class="queue-code">{fmt_asset_identity(item)}</span>
                    {fmt_risk_badge(item['risk_level'])}
                </div>
                <div class="queue-meta">
                    <span>评分 {item['risk_score'] or '—'}</span>
                    {_fmt_risk_day_meta(item)}
                    <span>预警 {item['alert_count']}</span>
                </div>
                <div class="queue-meta">
                    {fmt_sla_badge(item['sla_status'])}
                    <span>{escape(item['case_priority'] or '—')}</span>
                    <span>{escape(item['case_status'] or '无案件')}</span>
                </div>
            </a>
        """
    if not queue_rows:
        queue_rows = '<div class="empty">暂无风险队列数据</div>'

    detail_html = '<div class="empty">请从左侧选择房源查看风险画像</div>'
    if detail:
        triggers = "".join(f"<li>{escape(t)}</li>" for t in detail["risk_triggers"]) or "<li>暂无触发项</li>"
        bd = detail["score_breakdown"]
        alerts_html = ""
        for alert in detail["alerts"]:
            alerts_html += f"""
                <tr>
                    <td>{escape(alert['trigger_rule'])}</td>
                    <td>{fmt_risk_badge(alert['risk_level'])}</td>
                    <td>{escape(risk_hub.ALERT_STATUS_LABELS.get(alert['status'], alert['status']))}</td>
                </tr>
            """
        if not alerts_html:
            alerts_html = '<tr><td colspan="3" class="empty">暂无预警</td></tr>'

        case = detail.get("case")
        case_html = "暂无进行中案件"
        if case:
            case_html = f"""
                <div class="case-grid">
                    <div><span class="lbl">状态</span>{escape(FOLLOWUP_STATUS_LABELS.get(case['status'], case['status']))}</div>
                    <div><span class="lbl">负责人</span>{escape(case['owner_name'] or '—')}</div>
                    <div><span class="lbl">优先级</span>{escape(case['case_priority'] or '—')}</div>
                    <div><span class="lbl">SLA</span>{fmt_sla_badge(case['sla_status'])}</div>
                    <div><span class="lbl">截止</span>{escape(case['sla_due_date'] or '—')}</div>
                    <div><span class="lbl">下次行动</span>{escape(case['next_action_date'] or '—')}</div>
                </div>
                <p class="case-text">{escape(case['follow_up_plan'] or '—')}</p>
            """

        if detail.get("is_es"):
            breakdown_line = "已结清（ES），不参与逾期评分与告警"
            settlement = detail.get("settlement_date") or detail.get("last_payment_date") or "—"
            lifecycle_line = f'<p class="muted">提前结清日期：{escape(str(settlement))}</p>'
        else:
            breakdown_line = (
                f"逾期权重 {bd['overdue_weight']} + "
                f"金额异常 {bd['reconciliation_weight']} + "
                f"回款波动 {bd['volatility_weight']}"
            )
            lifecycle_line = ""

        detail_html = f"""
            <div class="panel-section">
                <h3>风险画像</h3>
                {fmt_asset_identity_block(detail)}
                <div class="hero-score">
                    <div class="score">{detail['risk_score'] or '—'}</div>
                    <div>{fmt_risk_badge(detail['risk_level'])} {fmt_sla_badge(case['sla_status'] if case else None)}</div>
                </div>
                {lifecycle_line}
                <div class="breakdown">{breakdown_line}</div>
            </div>
            <div class="panel-section">
                <h3>风险触发源</h3>
                <ul class="triggers">{triggers}</ul>
            </div>
            <div class="panel-section">
                <h3>预警列表</h3>
                <div class="table-wrap">
                <table><thead><tr><th>规则</th><th>等级</th><th>状态</th></tr></thead>
                <tbody>{alerts_html}</tbody></table>
                </div>
            </div>
            <div class="panel-section">
                <h3>案件（Case）</h3>
                {case_html}
            </div>
            <div class="panel-section actions">
                <h3>操作</h3>
                <p class="muted">API: PATCH /risk/alerts/{{id}} · POST /risk/cases · POST /risk/score/recalculate</p>
                <div class="btn-row">
                    <a class="btn" href="/risk/alerts">查看全部预警</a>
                    <a class="btn" href="/risk/cases">查看全部案件</a>
                    <a class="btn primary" href="/risk/assets/{detail['trust_asset_id']}">JSON 详情</a>
                </div>
            </div>
        """

    data_date = data.get("data_date") or "—"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>风控工作台 · 房地产资产证券化平台</title>
    <style>
        {PAGE_CHROME_CSS}
        {STANDARD_HEADER_CSS}
        header p {{ color: #94a3b8; margin-top: 0.35rem; font-size: 0.9rem; }}
        .kpi-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 0.75rem; margin: 1.25rem 0;
        }}
        .kpi {{
            background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 10px; padding: 0.85rem;
        }}
        .kpi .lbl {{ font-size: 0.75rem; color: #94a3b8; }}
        .kpi .val {{ font-size: 1.35rem; font-weight: 700; margin-top: 0.25rem; }}
        .kpi .val.warn {{ color: #f87171; }}
        .workbench {{
            display: grid; grid-template-columns: 360px 1fr; gap: 1rem; min-height: 520px;
        }}
        @media (max-width: 900px) {{ .workbench {{ grid-template-columns: 1fr; }} }}
        .panel {{
            background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px; overflow: hidden;
        }}
        .panel-hd {{
            padding: 0.85rem 1rem; border-bottom: 1px solid rgba(255,255,255,0.08);
            font-weight: 600; color: #f8fafc;
        }}
        .queue-item {{
            display: block; padding: 0.85rem 1rem; border-bottom: 1px solid rgba(255,255,255,0.06);
            color: inherit; text-decoration: none;
        }}
        .queue-item:hover, .queue-item.active {{
            background: rgba(56,189,248,0.08);
        }}
        .queue-top {{ display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }}
        .queue-code {{ font-weight: 600; color: #f8fafc; }}
        .queue-meta {{ font-size: 0.78rem; color: #94a3b8; margin-top: 0.35rem; display: flex; gap: 0.65rem; flex-wrap: wrap; }}
        .panel-body {{ padding: 1rem; }}
        .panel-section {{ margin-bottom: 1.25rem; }}
        .panel-section h3 {{ font-size: 0.9rem; color: #94a3b8; margin-bottom: 0.6rem; }}
        .hero-score {{ display: flex; align-items: center; gap: 1rem; }}
        .hero-score .score {{ font-size: 2.5rem; font-weight: 700; color: #f87171; }}
        .breakdown {{ font-size: 0.82rem; color: #94a3b8; margin-top: 0.5rem; }}
        .triggers {{ margin-left: 1.1rem; font-size: 0.9rem; color: #e2e8f0; }}
        {TABLE_SCROLL_CSS}
        th, td {{ padding: 0.5rem; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.06); }}
        th {{ color: #94a3b8; font-weight: 500; font-size: 0.85rem; }}
        .badge {{
            display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px;
            font-size: 0.72rem; border: 1px solid rgba(255,255,255,0.15);
        }}
        .case-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.5rem; font-size: 0.85rem; }}
        .case-grid .lbl {{ display: block; color: #64748b; font-size: 0.75rem; }}
        .case-text {{ margin-top: 0.5rem; font-size: 0.85rem; color: #cbd5e1; }}
        .btn-row {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }}
        .btn {{
            display: inline-block; padding: 0.45rem 0.85rem; border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.15); font-size: 0.82rem; color: #e2e8f0;
        }}
        .btn.primary {{ background: rgba(56,189,248,0.2); border-color: rgba(56,189,248,0.4); }}
        .empty {{ color: #64748b; text-align: center; padding: 1.5rem; }}
        .muted {{ color: #64748b; font-size: 0.8rem; }}
        footer {{ margin-top: 1.5rem; text-align: center; font-size: 0.8rem; color: #64748b; }}
    </style>
</head>
<body class="risk-page">
    <div class="container">
        <nav class="breadcrumb"><a href="/">首页</a> / 信托资产风险中台 / 工作台</nav>
        <header>
            <h1>信托资产风险中台 · Risk Control Hub</h1>
            <p>数据日期 {escape(data_date)} · <a href="/risk/workbench/data">JSON</a> · <a href="/overdue">V1 逾期视图</a></p>
        </header>
        <div class="kpi-grid">
            <div class="kpi"><div class="lbl">A 高风险</div><div class="val warn">{summary['level_a_count']}</div></div>
            <div class="kpi"><div class="lbl">B / C</div><div class="val">{summary['level_b_count']} / {summary['level_c_count']}</div></div>
            <div class="kpi"><div class="lbl">平均风险分</div><div class="val">{summary['avg_risk_score']}</div></div>
            <div class="kpi"><div class="lbl">开放预警</div><div class="val warn">{summary['open_alert_count']}</div></div>
            <div class="kpi"><div class="lbl">SLA 异常案件</div><div class="val warn">{summary['sla_breached_count']}</div></div>
            <div class="kpi"><div class="lbl">逾期资产（M0+）</div><div class="val warn">{summary.get('overdue_total', summary.get('overdue_count', 0))}</div></div>
            <div class="kpi"><div class="lbl">风险暴露（Exposure）</div><div class="val">{summary.get('exposure_total', 0)}</div></div>
            <div class="kpi"><div class="lbl">提前结清（ES）</div><div class="val">{summary.get('breakdown', {}).get('ES', summary.get('es_count', 0))}</div></div>
        </div>
        <div class="workbench">
            <div class="panel">
                <div class="panel-hd">Risk Queue · 风险队列</div>
                <div>{queue_rows}</div>
            </div>
            <div class="panel">
                <div class="panel-hd">Risk Control Panel · 风控面板</div>
                <div class="panel-body">{detail_html}</div>
            </div>
        </div>
        <footer>Real Estate Securitization Platform · Risk Ops Platform</footer>
    </div>
</body>
</html>"""


def fetch_asset_pool_overview(conn, asset_pool_id: int):
    pool_row = conn.execute(
        text("""
            SELECT
                id,
                code,
                name,
                status,
                appraised_value
            FROM asset_pools
            WHERE id = :asset_pool_id
        """),
        {"asset_pool_id": asset_pool_id},
    ).fetchone()

    if pool_row is None:
        return None

    trust_product_rows = conn.execute(
        text("""
            SELECT
                id,
                code,
                name,
                status,
                expected_return_rate
            FROM trust_products
            WHERE asset_pool_id = :asset_pool_id
            ORDER BY id
        """),
        {"asset_pool_id": asset_pool_id},
    )

    trust_products = []
    for row in trust_product_rows:
        trust_products.append({
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "status": row.status,
            "expected_return_rate": float(row.expected_return_rate) if row.expected_return_rate else None,
        })

    return {
        "asset_pool": {
            "id": pool_row.id,
            "code": pool_row.code,
            "name": pool_row.name,
            "status": pool_row.status,
            "appraised_value": float(pool_row.appraised_value),
        },
        "trust_products": trust_products,
    }


def render_asset_pool_detail_html(data):
    pool = data["asset_pool"]
    trust_products = data["trust_products"]

    trust_product_cards = ""
    if trust_products:
        for tp in trust_products:
            trust_product_cards += f"""
                <div class="card sub-card">
                    <div class="sub-card-header">
                        <div>
                            <div class="sub-card-code">{escape(tp["code"])}</div>
                            <div class="sub-card-title">{escape(tp["name"])}</div>
                        </div>
                        {fmt_status(tp["status"])}
                    </div>
                    <div class="meta-grid">
                        <div><span class="meta-label">预期收益率</span><span class="meta-value">{fmt_rate(tp["expected_return_rate"])}</span></div>
                    </div>
                </div>
            """
    else:
        trust_product_cards = '<div class="empty-block">尚未发行信托产品</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(pool["name"])} · 资产包详情</title>
    <style>
        {PAGE_CHROME_CSS}
        {STANDARD_HEADER_CSS}
        header {{
            margin-bottom: 2rem;
        }}
        header p {{
            margin-top: 0.5rem;
            font-size: 0.95rem;
            color: #94a3b8;
        }}
        .hero {{
            display: flex;
            flex-wrap: wrap;
            gap: 1.5rem;
            align-items: flex-start;
            justify-content: space-between;
        }}
        .hero-main {{
            flex: 1;
            min-width: 220px;
        }}
        .hero-code {{
            font-size: 0.875rem;
            color: #94a3b8;
            margin-bottom: 0.5rem;
        }}
        .hero-value {{
            font-size: 2rem;
            font-weight: 700;
            color: #38bdf8;
            margin-top: 0.75rem;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.25rem;
        }}
        .card {{
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 1.5rem;
            backdrop-filter: blur(8px);
        }}
        .card-label {{
            font-size: 0.875rem;
            color: #94a3b8;
            margin-bottom: 0.75rem;
        }}
        .card-value {{
            font-size: 1.75rem;
            font-weight: 700;
            color: #f8fafc;
            line-height: 1.2;
        }}
        .card-value.money {{
            color: #38bdf8;
        }}
        .card-value.budget {{
            color: #34d399;
        }}
        .section {{
            margin-top: 2rem;
        }}
        .section-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: #f8fafc;
            margin-bottom: 1rem;
        }}
        {TABLE_SCROLL_CSS}
        th, td {{
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }}
        th {{
            color: #94a3b8;
            font-weight: 500;
            font-size: 0.8rem;
        }}
        td.num {{
            color: #38bdf8;
            font-weight: 600;
        }}
        .badge {{
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 999px;
            font-size: 0.75rem;
            background: rgba(56, 189, 248, 0.15);
            color: #7dd3fc;
            border: 1px solid rgba(56, 189, 248, 0.25);
        }}
        .sub-card {{
            margin-bottom: 1rem;
        }}
        .sub-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            margin-bottom: 1rem;
        }}
        .sub-card-code {{
            font-size: 0.8rem;
            color: #94a3b8;
            margin-bottom: 0.25rem;
        }}
        .sub-card-title {{
            font-size: 1rem;
            font-weight: 600;
            color: #f8fafc;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 0.75rem;
            margin-bottom: 1rem;
        }}
        .meta-label {{
            display: block;
            font-size: 0.75rem;
            color: #94a3b8;
            margin-bottom: 0.25rem;
        }}
        .meta-value {{
            font-size: 0.95rem;
            color: #f8fafc;
        }}
        .meta-value.money {{
            color: #38bdf8;
        }}
        .progress-wrap {{
            margin-top: 0.5rem;
        }}
        .progress-label {{
            display: flex;
            justify-content: space-between;
            font-size: 0.8rem;
            color: #94a3b8;
            margin-bottom: 0.4rem;
        }}
        .progress-bar {{
            height: 8px;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 999px;
            overflow: hidden;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #38bdf8, #34d399);
            border-radius: 999px;
        }}
        .empty, .empty-block {{
            color: #64748b;
            text-align: center;
        }}
        .empty-block {{
            padding: 2rem 1rem;
            background: rgba(255, 255, 255, 0.04);
            border: 1px dashed rgba(255, 255, 255, 0.1);
            border-radius: 12px;
        }}
        .muted {{
            color: #64748b;
            font-size: 0.85rem;
        }}
        footer {{
            margin-top: 2.5rem;
            text-align: center;
            font-size: 0.8rem;
            color: #64748b;
        }}
    </style>
</head>
<body class="pool-page">
    <div class="container">
        <nav class="breadcrumb">
            <a href="/">首页</a> / 资产包 / {escape(pool["code"])}
        </nav>

        <header>
            <div class="card hero">
                <div class="hero-main">
                    <div class="hero-code">{escape(pool["code"])} · {fmt_status(pool["status"])}</div>
                    <h1>{escape(pool["name"])}</h1>
                    <p>资产包详情 · Real Estate Securitization Platform</p>
                    <div class="hero-value">{fmt_money(pool["appraised_value"])}</div>
                    <div class="card-label" style="margin-top: 0.5rem;">评估价值</div>
                </div>
            </div>
        </header>

        <div class="grid">
            <div class="card">
                <div class="card-label">信托产品数</div>
                <div class="card-value">{len(trust_products)}</div>
            </div>
        </div>

        <section class="section">
            <h2 class="section-title">信托产品</h2>
            {trust_product_cards}
        </section>

        <footer>Real Estate Securitization Platform</footer>
    </div>
</body>
</html>"""


def render_not_found_html():
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>资产包不存在</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
            min-height: 100vh;
            color: #e2e8f0;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2rem;
        }
        .box {
            text-align: center;
            max-width: 420px;
        }
        h1 { font-size: 1.5rem; margin-bottom: 0.75rem; color: #f8fafc; }
        p { color: #94a3b8; margin-bottom: 1.5rem; }
        a { color: #38bdf8; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="box">
        <h1>资产包不存在</h1>
        <p>请检查 URL 中的资产包 ID 是否正确。</p>
        <a href="/">返回首页</a>
    </div>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
def dashboard(page_user: Annotated[dict, Depends(get_page_user)]):
    asset_pool_count = 0
    trust_product_count = 0
    overdue_total = 0
    exposure_total = 0
    high_risk_count = 0
    monitor_asset_count = 0
    snapshot_date: str | None = None
    latest_issue_date: str | None = None
    issuance_row_count = 0

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM asset_pools) AS asset_pool_count,
                (SELECT COUNT(*) FROM trust_products) AS trust_product_count
        """)).fetchone()
        asset_pool_count = int(row.asset_pool_count)
        trust_product_count = int(row.trust_product_count)

        try:
            iss_row = conn.execute(text("""
                SELECT MAX(issue_date) AS latest_issue_date, COUNT(*) AS row_count
                FROM trust_product_issuance_asset_records
            """)).fetchone()
            if iss_row:
                if iss_row.latest_issue_date:
                    latest_issue_date = str(iss_row.latest_issue_date)
                issuance_row_count = int(iss_row.row_count)
        except Exception:
            latest_issue_date = None
            issuance_row_count = 0

        try:
            overview_kpi = fetch_overdue_overview(conn)
            overdue_total = int(overview_kpi.get("overdue_total", 0))
            exposure_total = int(overview_kpi.get("exposure_total", 0))
            monitor_asset_count = int(overview_kpi.get("total_asset_code_count", 0))
            if overview_kpi.get("data_date"):
                snapshot_date = str(overview_kpi["data_date"])
            risk_row = conn.execute(text("""
                SELECT COUNT(*) AS cnt
                FROM trust_asset_monitor_records m
                WHERE m.data_date = (SELECT MAX(data_date) FROM trust_asset_monitor_records)
                  AND m.risk_level = 'A'
            """)).fetchone()
            if risk_row:
                high_risk_count = int(risk_row.cnt)
        except Exception:
            overdue_total = 0
            exposure_total = 0
            high_risk_count = 0
            monitor_asset_count = 0
            snapshot_date = None

    def dash_count(value: int) -> str:
        return str(value)

    def dash_date(value: str | None) -> str:
        return value if value else "—"

    data_updated_at = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    issuance_count_display = dash_count(issuance_row_count) if issuance_row_count else "—"
    monitor_count_display = dash_count(monitor_asset_count) if monitor_asset_count else "—"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>贝源RSP平台</title>
    <style>
        {PAGE_CHROME_CSS}
        {DASHBOARD_BODY_CSS}
        {STANDARD_HEADER_CSS}
        .page-header {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 0.5rem 1rem;
            margin-bottom: 1.25rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }}
        .brand {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            min-width: 0;
        }}
        .brand-icon {{
            width: 42px;
            height: 42px;
            border-radius: 10px;
            background: linear-gradient(135deg, #0ea5e9, #2563eb);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}
        .brand-icon svg {{
            width: 24px;
            height: 24px;
            fill: #fff;
        }}
        .brand p {{
            margin-top: 0.15rem;
            font-size: 0.78rem;
            color: #94a3b8;
        }}
        .header-meta {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: flex-end;
            gap: 0.5rem 0.75rem;
            font-size: 0.85rem;
            color: #94a3b8;
        }}
        .btn-refresh {{
            cursor: pointer;
            font: inherit;
            font-size: 0.78rem;
            padding: 0.28rem 0.55rem;
            border-radius: 6px;
            border: 1px solid rgba(255, 255, 255, 0.15);
            background: rgba(15, 23, 42, 0.7);
            color: #e2e8f0;
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
        }}
        .btn-refresh:hover {{
            border-color: #38bdf8;
            color: #38bdf8;
        }}
        .kpi-bar {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 0.6rem;
            margin-bottom: 0.75rem;
        }}
        .kpi-item {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            padding: 0.6rem 0.65rem;
        }}
        .kpi-label {{
            display: block;
            font-size: 0.75rem;
            color: #94a3b8;
            margin-bottom: 0.15rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .kpi-value {{
            display: block;
            font-size: 1.25rem;
            font-weight: 700;
            color: #f8fafc;
            line-height: 1.15;
        }}
        .kpi-value.warn {{ color: #fb923c; }}
        .kpi-value.overdue {{ color: #f87171; }}
        .kpi-value.money {{
            font-size: 1.05rem;
            font-weight: 700;
            font-variant-numeric: tabular-nums;
        }}
        .dash-section {{
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 10px;
            padding: 0.65rem 0.75rem 0.7rem;
            margin-bottom: 0.6rem;
        }}
        .ops-dual {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.65rem;
        }}
        .ops-panel {{
            min-width: 0;
        }}
        .section-title {{
            display: flex;
            align-items: center;
            gap: 0.45rem;
            margin-bottom: 0.45rem;
        }}
        .section-num {{
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            font-size: 0.68rem;
            font-weight: 700;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}
        .section-title h2 {{
            font-size: 0.88rem;
            font-weight: 600;
            color: #f1f5f9;
        }}
        .op-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-bottom: 0.55rem;
        }}
        a.op-chip {{
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.5rem 0.85rem;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.15);
            background: rgba(255, 255, 255, 0.06);
            color: #f8fafc;
            text-decoration: none;
            font-size: 0.85rem;
            font-weight: 600;
            letter-spacing: 0.01em;
            transition: background 0.15s, border-color 0.15s, transform 0.15s, box-shadow 0.15s;
        }}
        a.op-chip:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            text-decoration: none;
        }}
        .op-chip svg {{
            width: 15px;
            height: 15px;
            fill: currentColor;
            flex-shrink: 0;
        }}
        /* 导入主按钮：填充背景 */
        a.op-chip.op-blue {{
            background: linear-gradient(135deg, rgba(56,189,248,0.25) 0%, rgba(56,189,248,0.12) 100%);
            border-color: rgba(56,189,248,0.5);
            color: #7dd3fc;
        }}
        a.op-chip.op-blue:hover {{
            background: linear-gradient(135deg, rgba(56,189,248,0.38) 0%, rgba(56,189,248,0.2) 100%);
            border-color: #38bdf8;
            box-shadow: 0 4px 14px rgba(56,189,248,0.25);
        }}
        /* 查看/明细类按钮：彩色边框 */
        a.op-chip.op-green {{ color: #4ade80; border-color: rgba(74,222,128,0.35); }}
        a.op-chip.op-green:hover {{ border-color: #4ade80; box-shadow: 0 4px 12px rgba(74,222,128,0.2); }}
        a.op-chip.op-orange {{ color: #fb923c; border-color: rgba(251,146,60,0.35); }}
        a.op-chip.op-orange:hover {{ border-color: #fb923c; box-shadow: 0 4px 12px rgba(251,146,60,0.2); }}
        a.op-chip.op-purple {{ color: #c084fc; border-color: rgba(192,132,252,0.35); }}
        a.op-chip.op-purple:hover {{ border-color: #c084fc; box-shadow: 0 4px 12px rgba(192,132,252,0.2); }}
        a.op-chip.op-teal {{ color: #2dd4bf; border-color: rgba(45,212,191,0.35); }}
        a.op-chip.op-teal:hover {{ border-color: #2dd4bf; box-shadow: 0 4px 12px rgba(45,212,191,0.2); }}
        .mini-kpi-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem 1rem;
            font-size: 0.8rem;
            color: #94a3b8;
        }}
        .mini-kpi-row strong {{
            color: #e2e8f0;
            font-weight: 600;
            font-variant-numeric: tabular-nums;
        }}
        .risk-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 0.55rem;
        }}
        a.risk-card {{
            display: block;
            padding: 0.65rem 0.75rem;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            background: rgba(15, 23, 42, 0.55);
            color: inherit;
            text-decoration: none;
            transition: transform 0.15s, border-color 0.15s;
        }}
        a.risk-card:hover {{
            transform: translateY(-1px);
            border-color: rgba(56, 189, 248, 0.35);
            text-decoration: none;
        }}
        .risk-card-head {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 0.35rem;
            margin-bottom: 0.35rem;
        }}
        .risk-card-label {{
            font-size: 0.75rem;
            color: #94a3b8;
        }}
        .risk-card-icon {{
            width: 26px;
            height: 26px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}
        .risk-card-icon svg {{
            width: 14px;
            height: 14px;
            fill: currentColor;
        }}
        .risk-icon-warn {{ background: rgba(251, 146, 60, 0.15); color: #fb923c; }}
        .risk-icon-overdue {{ background: rgba(248, 113, 113, 0.15); color: #f87171; }}
        .risk-icon-monitor {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; }}
        .risk-card-value {{
            font-size: 1.35rem;
            font-weight: 700;
            line-height: 1.1;
            color: #f8fafc;
        }}
        .risk-card-value.warn {{ color: #fb923c; }}
        .risk-card-value.overdue {{ color: #f87171; }}
        .risk-card-value.muted {{ color: #94a3b8; font-size: 1.2rem; }}
        .risk-card-foot {{
            margin-top: 0.3rem;
            font-size: 0.72rem;
            color: #64748b;
        }}
        .page-footer {{
            margin-top: 0.45rem;
            padding-top: 0.45rem;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 0.35rem;
            font-size: 0.72rem;
            color: #64748b;
        }}
        .page-footer a {{
            color: #94a3b8;
            text-decoration: none;
            margin-left: 0.75rem;
        }}
        .page-footer a:hover {{ color: #38bdf8; }}
        @media (min-width: 1100px) {{
            .kpi-bar {{ grid-template-columns: repeat(8, 1fr); }}
            .kpi-value.money {{ font-size: 0.95rem; }}
        }}
        @media (max-width: 960px) {{
            .ops-dual {{ grid-template-columns: 1fr; }}
            .risk-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .kpi-bar {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        @media (max-width: 560px) {{
            .risk-grid {{ grid-template-columns: 1fr; }}
            .page-header {{ flex-direction: column; align-items: flex-start; }}
            body.dashboard-page {{ padding: 1rem 0.75rem 1.25rem; }}
        }}
    </style>
</head>
<body class="dashboard-page">
    <div class="container">
        <header class="page-header">
            <div class="brand">
                <div class="brand-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24"><path d="M12 3L2 20h20L12 3zm0 4.5l6.2 10.5H5.8L12 7.5z"/></svg>
                </div>
                <div>
                    <h1>贝源RSP平台</h1>
                    <p>Real Estate Securitization Platform</p>
                </div>
            </div>
            <div class="header-meta">
                <span>数据更新：{data_updated_at}</span>
                <button type="button" class="btn-refresh" onclick="location.reload()" title="刷新">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M17.65 6.35A7.958 7.958 0 0012 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0112 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>
                    刷新
                </button>
            </div>
        </header>

        <div class="kpi-bar" aria-label="平台概览">
            <div class="kpi-item">
                <span class="kpi-label">资产包</span>
                <span class="kpi-value">{dash_count(asset_pool_count)}</span>
            </div>
            <div class="kpi-item">
                <span class="kpi-label">信托产品</span>
                <span class="kpi-value">{dash_count(trust_product_count)}</span>
            </div>
            <div class="kpi-item">
                <span class="kpi-label">逾期 M0+</span>
                <span class="kpi-value overdue">{dash_count(overdue_total)}</span>
            </div>
            <div class="kpi-item">
                <span class="kpi-label">暴露规模</span>
                <span class="kpi-value">{dash_count(exposure_total)}</span>
            </div>
            <div class="kpi-item">
                <span class="kpi-label">A 级风险</span>
                <span class="kpi-value warn">{dash_count(high_risk_count)}</span>
            </div>
        </div>

        <section class="dash-section" aria-label="业务操作">
            <div class="ops-dual">
                <div class="ops-panel" aria-labelledby="sec-issuance">
                    <div class="section-title">
                        <span class="section-num">1</span>
                        <h2 id="sec-issuance">发行数据</h2>
                    </div>
                    <div class="op-row">
                        <a href="/issuance/upload" class="op-chip op-blue">
                            <svg viewBox="0 0 24 24"><path d="M9 16h6v-6h4l-7-7-7 7h4v6zm-4 2h14v2H5v-2z"/></svg>
                            发行数据导入
                        </a>
                        <a href="/issuance/records" class="op-chip op-green">
                            <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>
                            发行查看
                        </a>
                        <a href="/trust-products/manage" class="op-chip op-purple">
                            <svg viewBox="0 0 24 24"><path d="M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h16v2H4v-2z"/></svg>
                            产品管理
                        </a>
                    </div>
                    <div class="mini-kpi-row">
                        <span>最近发行日 <strong>{dash_date(latest_issue_date)}</strong></span>
                        <span>发行明细 <strong>{issuance_count_display}</strong> 条</span>
                    </div>
                </div>
                <div class="ops-panel" aria-labelledby="sec-assetinfo">
                    <div class="section-title">
                        <span class="section-num">2</span>
                        <h2 id="sec-assetinfo">资产情况更新</h2>
                    </div>
                    <div class="op-row">
                        <a href="/assetinfo/upload" class="op-chip op-blue">
                            <svg viewBox="0 0 24 24"><path d="M9 16h6v-6h4l-7-7-7 7h4v6zm-4 2h14v2H5v-2z"/></svg>
                            资产数据导入
                        </a>
                        <a href="/assetinfo/repayment-records" class="op-chip op-orange">
                            <svg viewBox="0 0 24 24"><path d="M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z"/></svg>
                            还款明细
                        </a>
                        <a href="/assetinfo/repayment-plan-records" class="op-chip op-orange">
                            <svg viewBox="0 0 24 24"><path d="M19 3h-1V1h-2v2H8V1H6v2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7v-5z"/></svg>
                            回款计划
                        </a>
                        <a href="/assetinfo/monitor-records" class="op-chip op-purple">
                            <svg viewBox="0 0 24 24"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
                            监控快照
                        </a>
                    </div>
                    <div class="mini-kpi-row">
                        <span>监控快照日 <strong>{dash_date(snapshot_date)}</strong></span>
                        <span>资产数 <strong>{monitor_count_display}</strong></span>
                    </div>
                </div>
            </div>
        </section>

        <section class="dash-section" aria-labelledby="sec-swap">
            <div class="section-title">
                <span class="section-num">3</span>
                <h2 id="sec-swap">资产置换和回购</h2>
            </div>
            <div class="op-row">
                <a href="/asset-swap" class="op-chip op-teal">
                    <svg viewBox="0 0 24 24"><path d="M6.99 11L3 15l3.99 4v-3H14v-2H6.99v-3zM21 9l-3.99-4v3H10v2h7.01v3L21 9z"/></svg>
                    资产置换
                </a>
            </div>
        </section>

        <section class="dash-section" aria-labelledby="sec-portfolio">
            <div class="section-title">
                <span class="section-num">4</span>
                <h2 id="sec-portfolio">资产组合管理</h2>
            </div>
            <div class="op-row">
                <a href="/assetinfo/asset-stats" class="op-chip op-teal">
                    <svg viewBox="0 0 24 24"><path d="M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z"/></svg>
                    资产情况统计
                </a>
            </div>
            <div class="risk-grid">
                <a href="/risk/workbench" class="risk-card">
                    <div class="risk-card-head">
                        <span class="risk-card-label">风险预警</span>
                        <span class="risk-card-icon risk-icon-warn" aria-hidden="true">
                            <svg viewBox="0 0 24 24"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>
                        </span>
                    </div>
                    <div class="risk-card-value warn">{dash_count(high_risk_count)}</div>
                    <div class="risk-card-foot">A 类高风险资产 →</div>
                </a>
                <a href="/overdue" class="risk-card">
                    <div class="risk-card-head">
                        <span class="risk-card-label">逾期资产（M0+）</span>
                        <span class="risk-card-icon risk-icon-overdue" aria-hidden="true">
                            <svg viewBox="0 0 24 24"><path d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67V7z"/></svg>
                        </span>
                    </div>
                    <div class="risk-card-value overdue">{dash_count(overdue_total)}</div>
                    <div class="risk-card-foot">暴露规模 {dash_count(exposure_total)} 户 →</div>
                </a>
                <a href="/assetinfo/monitor-records" class="risk-card">
                    <div class="risk-card-head">
                        <span class="risk-card-label">监控中资产</span>
                        <span class="risk-card-icon risk-icon-monitor" aria-hidden="true">
                            <svg viewBox="0 0 24 24"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
                        </span>
                    </div>
                    <div class="risk-card-value">{monitor_count_display}</div>
                    <div class="risk-card-foot">快照日 {dash_date(snapshot_date)} →</div>
                </a>
                <a href="/spatial/map" class="risk-card">
                    <div class="risk-card-head">
                        <span class="risk-card-label">地图监控</span>
                        <span class="risk-card-icon risk-icon-monitor" aria-hidden="true">
                            <svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>
                        </span>
                    </div>
                    <div class="risk-card-value">按城市</div>
                    <div class="risk-card-foot">监控快照 · M 级着色 →</div>
                </a>
            </div>
        </section>

        <section class="dash-section" aria-labelledby="sec-disclosure">
            <div class="section-title">
                <span class="section-num">5</span>
                <h2 id="sec-disclosure">数据披露</h2>
            </div>
            <div class="op-row">
                <a href="/disclosure/repayment" class="op-chip op-orange">
                    <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
                    还款明细披露
                </a>
                <a href="/disclosure/monitor" class="op-chip op-purple">
                    <svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
                    资产监控披露
                </a>
            </div>
        </section>

        <footer class="page-footer">
            <span>贝源RSP平台 © {datetime.now().year}</span>
            <span>
                <a href="#">关于我们</a>
                <a href="#">帮助中心</a>
                <a href="#">联系我们</a>
            </span>
        </footer>
    </div>
</body>
</html>"""
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))

@app.get("/asset-pools")
def list_asset_pools():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                id,
                code,
                name,
                status,
                appraised_value
            FROM asset_pools
            ORDER BY id
        """))

        asset_pools = []
        for row in result:
            asset_pools.append({
                "id": row.id,
                "code": row.code,
                "name": row.name,
                "status": row.status,
                "appraised_value": float(row.appraised_value),
            })

        return asset_pools

@app.get("/asset-pools/{asset_pool_id}", response_class=HTMLResponse)
def asset_pool_detail(
    asset_pool_id: int,
    page_user: Annotated[dict, Depends(get_page_user)],
):
    with engine.connect() as conn:
        data = fetch_asset_pool_overview(conn, asset_pool_id)
        if data is None:
            return HTMLResponse(content=render_not_found_html(), status_code=404)
        html = render_asset_pool_detail_html(data)

    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))

@app.get("/asset-pools/{asset_pool_id}/overview")
def get_asset_pool_overview(asset_pool_id: int):
    with engine.connect() as conn:
        data = fetch_asset_pool_overview(conn, asset_pool_id)

    if data is None:
        raise HTTPException(status_code=404, detail="Asset pool not found")

    return data

@app.get("/trust-products")
def list_trust_products():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                id,
                asset_pool_id,
                code,
                name,
                status,
                expected_return_rate
            FROM trust_products
            ORDER BY id
        """))

        trust_products = []
        for row in result:
            trust_products.append({
                "id": row.id,
                "asset_pool_id": row.asset_pool_id,
                "code": row.code,
                "name": row.name,
                "status": row.status,
                "expected_return_rate": float(row.expected_return_rate) if row.expected_return_rate else None,
            })

        return trust_products

@app.get("/trust-products/manage", response_class=HTMLResponse)
def trust_products_manage_page(page_user: Annotated[dict, Depends(get_page_user)]):
    with engine.connect() as conn:
        items = trust_products_svc.fetch_manage_list(conn)
    html = trust_products_html.render_trust_products_manage_page(items)
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


@app.get("/trust-products/new", response_class=HTMLResponse)
def trust_products_new_page(page_user: Annotated[dict, Depends(get_page_user)]):
    with engine.connect() as conn:
        pools = trust_products_svc.fetch_asset_pools(conn)
    html = trust_products_html.render_trust_product_form_page(mode="create", asset_pools=pools)
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


@app.get("/trust-products/{product_id}/edit", response_class=HTMLResponse)
def trust_products_edit_page(
    product_id: int,
    page_user: Annotated[dict, Depends(get_page_user)],
):
    with engine.connect() as conn:
        product = trust_products_svc.fetch_by_id(conn, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Trust product not found")
    html = trust_products_html.render_trust_product_form_page(mode="edit", product=product)
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


@app.get("/trust-products/{product_id}")
def get_trust_product(
    product_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    with engine.connect() as conn:
        product = trust_products_svc.fetch_by_id(conn, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Trust product not found")
    return product


@app.post("/trust-products")
def create_trust_product(
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(...),
):
    # TODO: admin only
    with engine.begin() as conn:
        return trust_products_svc.create_trust_product(conn, body)


@app.patch("/trust-products/{product_id}")
def patch_trust_product(
    product_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(...),
):
    # TODO: admin only
    with engine.begin() as conn:
        return trust_products_svc.update_trust_product(conn, product_id, body)


@app.get("/overdue/overview")
def overdue_overview(
    trust_product_id: str | None = None,
    trust_product_ids: list[str] | None = Query(default=None),
    data_date: str | None = None,
    delinquency_bucket: str | None = None,
    trust_marker: str | None = None,
    internal_status: str | None = None,
    has_followup: str | None = None,
    asset_code: str | None = None,
    custody_asset_code: str | None = None,
    city: str | None = None,
):
    pids = query_utils.parse_trust_product_ids(trust_product_id, trust_product_ids)
    dd = query_utils.parse_optional_date(data_date)
    with engine.connect() as conn:
        return fetch_overdue_overview(
            conn,
            pids,
            dd,
            delinquency_bucket=query_utils.clean_optional_str(delinquency_bucket),
            trust_marker=query_utils.clean_optional_str(trust_marker),
            internal_status=query_utils.clean_optional_str(internal_status),
            has_followup=query_utils.clean_optional_str(has_followup),
            asset_code=query_utils.clean_optional_str(asset_code),
            custody_asset_code=query_utils.clean_optional_str(custody_asset_code),
            city=query_utils.clean_optional_str(city),
        )


@app.get("/overdue/checks")
def overdue_checks(
    trust_product_id: str | None = None,
    trust_product_ids: list[str] | None = Query(default=None),
    data_date: str | None = None,
):
    with engine.connect() as conn:
        return fetch_overdue_checks(
            conn,
            query_utils.parse_trust_product_ids(trust_product_id, trust_product_ids),
            query_utils.parse_optional_date(data_date),
        )


@app.get("/overdue/reconciliation")
def overdue_reconciliation(
    trust_product_id: str | None = None,
    trust_product_ids: list[str] | None = Query(default=None),
    data_date: str | None = None,
):
    with engine.connect() as conn:
        return fetch_reconciliation(
            conn,
            query_utils.parse_trust_product_ids(trust_product_id, trust_product_ids),
            query_utils.parse_optional_date(data_date),
        )


@app.get("/overdue/followups")
def overdue_followups(
    trust_product_id: str | None = None,
    trust_product_ids: list[str] | None = Query(default=None),
    status: str | None = None,
):
    return fetch_overdue_followups(
        query_utils.parse_trust_product_ids(trust_product_id, trust_product_ids),
        query_utils.clean_optional_str(status),
    )


@app.post("/overdue/reconciliation/recalculate")
def overdue_reconciliation_recalculate(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str | None = Query(default=None),
    data_date: str | None = Query(default=None),
    body: dict | None = Body(default=None),
):
    payload = body or {}
    pid = payload.get("trust_product_id", query_utils.parse_optional_int(trust_product_id))
    dd = payload.get("data_date", query_utils.parse_optional_date(data_date))
    if pid is not None:
        pid = int(pid)
    with engine.connect() as conn:
        return recalculate_reconciliation(conn, pid, dd)


@app.post("/overdue/recalculate")
def overdue_recalculate(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str | None = Query(default=None),
    data_date: str | None = Query(default=None),
    body: dict | None = Body(default=None),
):
    payload = body or {}
    pid = payload.get("trust_product_id", query_utils.parse_optional_int(trust_product_id))
    dd = payload.get("data_date", query_utils.parse_optional_date(data_date))
    if pid is not None:
        pid = int(pid)
    raw_ids = payload.get("trust_product_ids")
    pids: list[int] | None = None
    if isinstance(raw_ids, list):
        pids = [int(x) for x in raw_ids]
    elif pid is not None:
        pids = [pid]
    as_of_raw = payload.get("as_of") or payload.get("as_of_date")
    as_of_date = None
    if as_of_raw:
        as_of_date = date.fromisoformat(str(as_of_raw)[:10])
    with engine.begin() as conn:
        result = recalculate_overdue_days(
            conn,
            trust_product_id=pid,
            data_date=dd,
            as_of=as_of_date,
            trust_product_ids=pids,
        )
    return result


@app.patch("/overdue/custody-marks")
def update_custody_mark(
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(...),
):
    trust_product_id = body.get("trust_product_id")
    asset_code = body.get("asset_code")
    custody_asset_code = body.get("custody_asset_code")
    data_date = body.get("data_date")
    if not trust_product_id or not data_date:
        raise HTTPException(status_code=400, detail="Missing required fields")
    if not asset_code and not custody_asset_code:
        raise HTTPException(status_code=400, detail="Missing asset_code")
    with engine.begin() as conn:
        if asset_code:
            return upsert_asset_trust_mark(
                conn,
                int(trust_product_id),
                str(asset_code),
                str(data_date),
                trust_marker=body.get("trust_marker"),
                internal_status=body.get("internal_status"),
                updated_by=current_user.get("username"),
            )
        return upsert_custody_trust_mark(
            conn,
            int(trust_product_id),
            str(custody_asset_code),
            str(data_date),
            trust_marker=body.get("trust_marker"),
            internal_status=body.get("internal_status"),
            updated_by=current_user.get("username"),
        )


@app.get("/overdue", response_class=HTMLResponse)
def overdue_dashboard(
    page_user: Annotated[dict, Depends(get_page_user)],
    trust_product_id: str | None = None,
    trust_product_ids: list[str] | None = Query(default=None),
    delinquency_bucket: str | None = None,
    delinquency_buckets: list[str] | None = Query(default=None),
    trust_marker: str | None = None,
    trust_markers: list[str] | None = Query(default=None),
    internal_status: str | None = None,
    internal_statuses: list[str] | None = Query(default=None),
    has_followup: str | None = None,
    asset_code: str | None = None,
    custody_asset_code: str | None = None,
    city: str | None = None,
    cities: list[str] | None = Query(default=None),
    focus_asset: str | None = None,
    portfolio_tab: str | None = None,
):
    pids = query_utils.parse_trust_product_ids(trust_product_id, trust_product_ids)
    parsed_buckets = normalize_delinquency_bucket_filters(
        query_utils.parse_optional_str_list(
            delinquency_bucket, delinquency_buckets
        )
    )
    parsed_markers = query_utils.parse_optional_str_list(trust_marker, trust_markers)
    parsed_statuses = query_utils.parse_optional_str_list(
        internal_status, internal_statuses
    )
    parsed_cities = query_utils.parse_optional_str_list(city, cities)
    parsed_has_followup = query_utils.clean_optional_str(has_followup)
    parsed_asset = query_utils.clean_optional_str(asset_code)
    parsed_custody = query_utils.clean_optional_str(custody_asset_code)
    parsed_focus = query_utils.clean_optional_str(focus_asset)
    parsed_portfolio_tab = query_utils.clean_optional_str(portfolio_tab)
    filters = {
        "trust_product_ids": pids,
        "delinquency_buckets": parsed_buckets,
        "trust_markers": parsed_markers,
        "internal_statuses": parsed_statuses,
        "has_followup": parsed_has_followup,
        "asset_code": parsed_asset,
        "custody_asset_code": parsed_custody,
        "cities": parsed_cities,
    }
    with engine.connect() as conn:
        overview = fetch_overdue_overview(
            conn,
            pids,
            delinquency_buckets=parsed_buckets,
            trust_markers=parsed_markers,
            internal_statuses=parsed_statuses,
            has_followup=parsed_has_followup,
            asset_code=parsed_asset,
            custody_asset_code=parsed_custody,
            cities=parsed_cities,
        )
        recon_data = fetch_reconciliation(conn, pids)
        products = fetch_trust_products(conn)

    followups = fetch_portfolio_followup_cases(overview)
    overview["active_followup_count"] = len(followups)

    html = render_overdue_html(
        overview,
        recon_data["items"],
        followups,
        filters=filters,
        products=products,
        code_mismatch_alerts=recon_data.get("code_mismatch_alerts") or [],
        focus_asset=parsed_focus,
        portfolio_tab=parsed_portfolio_tab,
    )
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


@app.get("/overdue/workbench/data")
def overdue_workbench_data(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str | None = None,
    asset_code: str | None = None,
    trust_asset_id: str | None = None,
    data_date: str | None = None,
    custody_asset_code: str | None = None,
):
    from app.service.overdue_workbench import build_overdue_workbench_service

    return build_overdue_workbench_service(engine).get_detail(
        trust_product_id=query_utils.parse_optional_int(trust_product_id),
        asset_code=query_utils.clean_optional_str(asset_code),
        custody_asset_code=query_utils.clean_optional_str(custody_asset_code),
        trust_asset_id=query_utils.parse_optional_int(trust_asset_id),
        data_date=query_utils.parse_optional_date(data_date),
    )


@app.get("/overdue/workbench/fragment")
def overdue_workbench_fragment(
    page_user: Annotated[dict, Depends(get_page_user)],
    trust_product_id: str | None = None,
    asset_code: str | None = None,
    custody_asset_code: str | None = None,
    delinquency_bucket: str | None = None,
    delinquency_buckets: list[str] | None = Query(default=None),
    data_date: str | None = None,
    list_product_id: str | None = None,
    list_product_ids: list[str] | None = Query(default=None),
    trust_asset_id: str | None = None,
    new_followup: str | None = None,
    new_followup_case: str | None = None,
    followup_expanded: str | None = None,
    followup_entry_id: str | None = None,
    followup_case_id: str | None = None,
    trust_marker: str | None = None,
    trust_markers: list[str] | None = Query(default=None),
    followup_status: str | None = None,
    followup_statuses: list[str] | None = Query(default=None),
    city: str | None = None,
    cities: list[str] | None = Query(default=None),
):
    """Partial detail-main HTML for workbench asset switching (no asset_list)."""
    del page_user  # auth only
    from app.html.render import build_workbench_fragment_payload
    from app.service.overdue_workbench import build_overdue_workbench_service

    svc = build_overdue_workbench_service(engine)
    pid = query_utils.parse_optional_int(trust_product_id)
    aid = query_utils.parse_optional_int(trust_asset_id)
    list_pid = query_utils.parse_optional_int(list_product_id)
    parsed_list_ids = query_utils.parse_trust_product_ids(
        list_product_id, list_product_ids
    )
    ac = query_utils.clean_optional_str(asset_code)
    custody = query_utils.clean_optional_str(custody_asset_code)
    parsed_buckets = normalize_delinquency_bucket_filters(
        query_utils.parse_optional_str_list(delinquency_bucket, delinquency_buckets)
    )
    parsed_markers = query_utils.parse_optional_str_list(trust_marker, trust_markers)
    parsed_statuses = query_utils.parse_optional_str_list(
        followup_status, followup_statuses
    )
    parsed_cities = query_utils.parse_optional_str_list(city, cities)
    list_scope_explicit = list_product_id is not None or list_product_ids is not None
    parsed_date = query_utils.parse_optional_date(data_date)

    dto = svc.get_workbench_detail_dto(
        trust_product_id=pid,
        asset_code=ac,
        custody_asset_code=custody if ac else None,
        delinquency_bucket=None,
        delinquency_buckets=parsed_buckets,
        data_date=parsed_date,
        list_product_id=list_pid,
        list_product_ids=parsed_list_ids,
        list_product_scope_explicit=list_scope_explicit,
        trust_asset_id=aid,
        trust_markers=parsed_markers,
        followup_statuses=parsed_statuses,
        cities=parsed_cities,
    )
    return build_workbench_fragment_payload(
        dto,
        new_followup=bool(query_utils.parse_optional_int(new_followup)),
        new_followup_case=bool(query_utils.parse_optional_int(new_followup_case)),
        followup_expanded=bool(
            query_utils.parse_optional_int(followup_expanded)
            or query_utils.parse_optional_int(new_followup_case)
        ),
        followup_entry_id=query_utils.parse_optional_int(followup_entry_id),
        followup_case_id=query_utils.parse_optional_int(followup_case_id),
    )


@app.get("/overdue/workbench", response_class=HTMLResponse)
def overdue_workbench_page(
    page_user: Annotated[dict, Depends(get_page_user)],
    trust_product_id: str | None = None,
    asset_code: str | None = None,
    custody_asset_code: str | None = None,
    delinquency_bucket: str | None = None,
    delinquency_buckets: list[str] | None = Query(default=None),
    data_date: str | None = None,
    list_product_id: str | None = None,
    list_product_ids: list[str] | None = Query(default=None),
    trust_asset_id: str | None = None,
    new_followup: str | None = None,
    new_followup_case: str | None = None,
    followup_expanded: str | None = None,
    followup_entry_id: str | None = None,
    followup_case_id: str | None = None,
    trust_marker: str | None = None,
    trust_markers: list[str] | None = Query(default=None),
    followup_status: str | None = None,
    followup_statuses: list[str] | None = Query(default=None),
    city: str | None = None,
    cities: list[str] | None = Query(default=None),
):
    from app.html.render import render_overdue_workbench_html
    from app.service.overdue_workbench import build_overdue_workbench_service

    svc = build_overdue_workbench_service(engine)
    pid = query_utils.parse_optional_int(trust_product_id)
    aid = query_utils.parse_optional_int(trust_asset_id)
    list_pid = query_utils.parse_optional_int(list_product_id)
    parsed_list_ids = query_utils.parse_trust_product_ids(list_product_id, list_product_ids)
    ac = query_utils.clean_optional_str(asset_code)
    custody = query_utils.clean_optional_str(custody_asset_code)
    # 与资产组合管理一致：未显式传等级时默认全部（不限 M0+）
    parsed_buckets = normalize_delinquency_bucket_filters(
        query_utils.parse_optional_str_list(
            delinquency_bucket, delinquency_buckets
        )
    )
    parsed_markers = query_utils.parse_optional_str_list(trust_marker, trust_markers)
    parsed_statuses = query_utils.parse_optional_str_list(
        followup_status, followup_statuses
    )
    parsed_cities = query_utils.parse_optional_str_list(city, cities)
    list_scope_explicit = list_product_id is not None or list_product_ids is not None
    parsed_date = query_utils.parse_optional_date(data_date)

    if custody and not ac and pid is not None:
        resolved_ac = svc.resolve_asset_code(pid, custody, parsed_date)
        if resolved_ac:
            redirect_pairs: list[tuple[str, str]] = [
                ("trust_product_id", str(pid)),
                ("asset_code", resolved_ac),
            ]
            if parsed_buckets:
                for b in parsed_buckets:
                    redirect_pairs.append(("delinquency_buckets", b))
            elif delinquency_bucket is not None or delinquency_buckets is not None:
                redirect_pairs.append(("delinquency_bucket", ""))
            if parsed_date:
                redirect_pairs.append(("data_date", parsed_date))
            if aid is not None:
                redirect_pairs.append(("trust_asset_id", str(aid)))
            if list_scope_explicit:
                redirect_pairs.append(
                    ("list_product_id", "" if list_pid is None else str(list_pid))
                )
            for m in parsed_markers or []:
                redirect_pairs.append(("trust_markers", m))
            for s in parsed_statuses or []:
                redirect_pairs.append(("followup_statuses", s))
            for c in parsed_cities or []:
                redirect_pairs.append(("cities", c))
            if query_utils.parse_optional_int(new_followup):
                redirect_pairs.append(("new_followup", "1"))
            if query_utils.parse_optional_int(new_followup_case):
                redirect_pairs.append(("new_followup_case", "1"))
            if query_utils.parse_optional_int(followup_expanded):
                redirect_pairs.append(("followup_expanded", "1"))
            parsed_entry_id = query_utils.parse_optional_int(followup_entry_id)
            if parsed_entry_id:
                redirect_pairs.append(("followup_entry_id", str(parsed_entry_id)))
            parsed_case_id = query_utils.parse_optional_int(followup_case_id)
            if parsed_case_id:
                redirect_pairs.append(("followup_case_id", str(parsed_case_id)))
            return RedirectResponse(
                url=f"/overdue/workbench?{urlencode(redirect_pairs)}",
                status_code=302,
            )

    dto = svc.get_workbench_page_dto(
        trust_product_id=pid,
        asset_code=ac,
        custody_asset_code=custody if ac else None,
        delinquency_bucket=None,
        delinquency_buckets=parsed_buckets,
        data_date=parsed_date,
        list_product_id=list_pid,
        list_product_ids=parsed_list_ids,
        list_product_scope_explicit=list_scope_explicit,
        trust_asset_id=aid,
        trust_markers=parsed_markers,
        followup_statuses=parsed_statuses,
        cities=parsed_cities,
    )
    with engine.connect() as conn:
        dto["products"] = fetch_trust_products(conn)
        city_scope = parsed_list_ids
        if city_scope is None and not list_scope_explicit and pid is not None:
            city_scope = [pid]
        dto["issuance_city_options"] = fetch_overdue_issuance_cities(conn, city_scope)

    html = render_overdue_workbench_html(
        dto,
        new_followup=bool(query_utils.parse_optional_int(new_followup)),
        new_followup_case=bool(query_utils.parse_optional_int(new_followup_case)),
        followup_expanded=bool(
            query_utils.parse_optional_int(followup_expanded)
            or query_utils.parse_optional_int(new_followup_case)
        ),
        followup_entry_id=query_utils.parse_optional_int(followup_entry_id),
        followup_case_id=query_utils.parse_optional_int(followup_case_id),
    )
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


@app.get("/risk/workbench/data")
def risk_workbench_data(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str | None = None,
    trust_asset_id: str | None = None,
):
    with engine.connect() as conn:
        return risk_hub.fetch_risk_workbench(
            conn,
            query_utils.parse_optional_int(trust_product_id),
            query_utils.parse_optional_int(trust_asset_id),
        )


@app.get("/risk/workbench", response_class=HTMLResponse)
def risk_workbench_page(
    page_user: Annotated[dict, Depends(get_page_user)],
    trust_product_id: str | None = None,
    trust_asset_id: str | None = None,
):
    with engine.connect() as conn:
        data = risk_hub.fetch_risk_workbench(
            conn,
            query_utils.parse_optional_int(trust_product_id),
            query_utils.parse_optional_int(trust_asset_id),
        )
    html = render_risk_workbench_html(data)
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


@app.get("/risk/assets")
def risk_assets(trust_product_id: str | None = None, risk_level: str | None = None):
    with engine.connect() as conn:
        return risk_hub.fetch_risk_assets(
            conn,
            query_utils.parse_optional_int(trust_product_id),
            query_utils.clean_optional_str(risk_level),
        )


@app.get("/risk/assets/{trust_asset_id}")
def risk_asset_detail(trust_asset_id: int):
    with engine.connect() as conn:
        detail = risk_hub.fetch_risk_asset_detail(conn, trust_asset_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Risk asset not found")
    return detail


@app.post("/risk/score/recalculate")
def risk_score_recalculate(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str | None = None,
):
    with engine.connect() as conn:
        return risk_hub.recalculate_risk_scores(
            conn, query_utils.parse_optional_int(trust_product_id)
        )


@app.get("/risk/alerts")
def risk_alerts(
    trust_product_id: str | None = None,
    trust_asset_id: str | None = None,
    status: str | None = None,
):
    with engine.connect() as conn:
        return risk_hub.fetch_risk_alerts(
            conn,
            query_utils.parse_optional_int(trust_product_id),
            query_utils.parse_optional_int(trust_asset_id),
            status=query_utils.clean_optional_str(status),
        )


@app.patch("/risk/alerts/{alert_id}")
def risk_alert_patch(
    alert_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(...),
):
    with engine.connect() as conn:
        result = risk_hub.patch_risk_alert(conn, alert_id, body)
    if result is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return result


@app.get("/risk/cases")
def risk_cases(
    trust_product_id: str | None = None,
    trust_asset_id: str | None = None,
    status: str | None = None,
):
    with engine.connect() as conn:
        return risk_hub.fetch_risk_cases(
            conn,
            query_utils.parse_optional_int(trust_product_id),
            query_utils.parse_optional_int(trust_asset_id),
            query_utils.clean_optional_str(status),
        )


@app.post("/risk/cases")
def risk_case_create(
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(...),
):
    if "trust_asset_id" not in body:
        raise HTTPException(status_code=400, detail="trust_asset_id is required")
    with engine.connect() as conn:
        result = risk_hub.create_risk_case(conn, body)
    if result is None:
        raise HTTPException(status_code=404, detail="Asset monitor data not found")
    return result


@app.patch("/risk/cases/{case_id}")
def risk_case_patch(
    case_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(...),
):
    with engine.connect() as conn:
        result = risk_hub.patch_risk_case(conn, case_id, body)
    if result is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return result


@app.get("/login", response_class=HTMLResponse)
def login_page(next: str = "/"):
    return HTMLResponse(content=auth_html.render_login_page(None, _safe_next_path(next)))


@app.post("/login")
def login_submit(
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    next_safe = _safe_next_path(next)
    with engine.connect() as conn:
        user = auth.authenticate_user(conn, username, password)
    if user is None:
        return HTMLResponse(
            content=auth_html.render_login_page("用户名或密码错误", next_safe),
            status_code=401,
        )
    token = auth.create_access_token(user["id"], user["username"], user["role"])
    redirect = RedirectResponse(url=next_safe, status_code=303)
    auth.set_auth_cookie(redirect, token)
    return redirect


@app.post("/logout")
def logout():
    redirect = RedirectResponse(url="/login", status_code=303)
    auth.clear_auth_cookie(redirect)
    return redirect


@app.post("/auth/login")
def auth_login(body: auth.LoginRequest, response: Response):
    with engine.connect() as conn:
        result = auth.login(conn, body.username, body.password)
    auth.set_auth_cookie(response, result["access_token"])
    return result


@app.get("/auth/me")
def auth_me(current_user: Annotated[dict, Depends(get_current_user)]):
    return current_user


@app.post("/assetinfo/pipeline")
def assetinfo_pipeline_run(
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(default={}),
):
    trust_product_id = body.get("trust_product_id")
    if trust_product_id is None:
        raise HTTPException(status_code=400, detail="trust_product_id is required")
    with engine.connect() as conn:
        return assetinfo_pipeline.run_assetinfo_pipeline(
            conn,
            trust_product_id=int(trust_product_id),
            trust_plan_alias=body.get("trust_plan_alias"),
            excel_path=body.get("excel_path"),
            asset_lookup_path=body.get("asset_lookup_path"),
            user_id=current_user["id"],
        )


@app.get("/assetinfo/upload", response_class=HTMLResponse)
def assetinfo_upload_page(page_user: Annotated[dict, Depends(get_page_user)]):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, name FROM trust_products ORDER BY id"))
        products = [{"id": r.id, "name": r.name} for r in rows]
    html = assetinfo_html.render_upload_page(products)
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


@app.post("/assetinfo/preview")
async def assetinfo_preview(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: int = Form(...),
    files: list[UploadFile] = File(...),
):
    batch_uuid = str(uuid.uuid4())
    saved = await assetinfo_upload.save_batch_files(batch_uuid, files)
    with engine.connect() as conn:
        return assetinfo_upload.run_preview(conn, trust_product_id, batch_uuid, saved)


@app.post("/assetinfo/import")
def assetinfo_import(
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(...),
):
    batch_uuid = body.get("batch_uuid") or body.get("file_id")
    trust_product_id = body.get("trust_product_id")
    if not batch_uuid or trust_product_id is None:
        raise HTTPException(status_code=400, detail="batch_uuid/file_id and trust_product_id required")
    with engine.connect() as conn:
        return assetinfo_upload.run_import(
            conn,
            batch_uuid=batch_uuid,
            trust_product_id=int(trust_product_id),
            user_id=current_user["id"],
            selected_sheet_keys=body.get("selected_sheet_keys"),
            selected_sheets=body.get("selected_sheets"),
            confirm_sheet_keys=body.get("confirm_sheet_keys"),
        )


@app.get("/assetinfo/repayment-records/data")
def assetinfo_repayment_records_data(
    current_user: Annotated[dict, Depends(get_current_user)],
    page: str | None = Query(default=None),
    page_size: str | None = Query(default=None),
    trust_product_id: str | None = Query(default=None),
    data_date: str | None = Query(default=None),
    asset_code: str | None = Query(default=None),
    custody_asset_code: str | None = Query(default=None),
    source_asset_code: str | None = Query(default=None),
    source_file_name: str | None = Query(default=None),
    source_sheet_name: str | None = Query(default=None),
):
    page_no, page_sz = query_utils.parse_pagination(page, page_size)
    filters = assetinfo_upload.build_record_filters(
        trust_product_id=trust_product_id,
        data_date=data_date,
        asset_code=asset_code,
        custody_asset_code=custody_asset_code,
        source_asset_code=source_asset_code,
        source_file_name=source_file_name,
        source_sheet_name=source_sheet_name,
    )
    with engine.connect() as conn:
        return assetinfo_upload.fetch_paginated_records(
            conn, "repayment", page_no, page_sz, filters,
        )


@app.get("/assetinfo/repayment-records", response_class=HTMLResponse)
def assetinfo_repayment_records_page(
    page_user: Annotated[dict, Depends(get_page_user)],
    page: str | None = Query(default=None),
    page_size: str | None = Query(default=None),
    trust_product_id: str | None = Query(default=None),
    data_date: str | None = Query(default=None),
    asset_code: str | None = Query(default=None),
    custody_asset_code: str | None = Query(default=None),
    source_asset_code: str | None = Query(default=None),
    source_file_name: str | None = Query(default=None),
    source_sheet_name: str | None = Query(default=None),
):
    page_no, page_sz = query_utils.parse_pagination(page, page_size)
    filters = assetinfo_upload.build_record_filters(
        trust_product_id=trust_product_id,
        data_date=data_date,
        asset_code=asset_code,
        custody_asset_code=custody_asset_code,
        source_asset_code=source_asset_code,
        source_file_name=source_file_name,
        source_sheet_name=source_sheet_name,
    )
    with engine.connect() as conn:
        data = assetinfo_upload.fetch_paginated_records(
            conn, "repayment", page_no, page_sz, filters,
        )
        products = [
            {"id": r.id, "name": r.name}
            for r in conn.execute(text("SELECT id, name FROM trust_products ORDER BY id"))
        ]
    html = assetinfo_html.render_records_page(
        "还款明细导入数据", "/assetinfo/repayment-records/data", filters, data, products,
        record_type="repayment",
    )
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


@app.get("/assetinfo/repayment-plan-records/data")
def assetinfo_repayment_plan_records_data(
    current_user: Annotated[dict, Depends(get_current_user)],
    page: str | None = Query(default=None),
    page_size: str | None = Query(default=None),
    trust_product_id: str | None = Query(default=None),
    data_date: str | None = Query(default=None),
    asset_code: str | None = Query(default=None),
    custody_asset_code: str | None = Query(default=None),
    source_asset_code: str | None = Query(default=None),
    source_file_name: str | None = Query(default=None),
    source_sheet_name: str | None = Query(default=None),
):
    page_no, page_sz = query_utils.parse_pagination(page, page_size)
    filters = assetinfo_upload.build_record_filters(
        trust_product_id=trust_product_id,
        data_date=data_date,
        asset_code=asset_code,
        custody_asset_code=custody_asset_code,
        source_asset_code=source_asset_code,
        source_file_name=source_file_name,
        source_sheet_name=source_sheet_name,
    )
    with engine.connect() as conn:
        return assetinfo_upload.fetch_paginated_records(
            conn, "repayment_plan", page_no, page_sz, filters,
        )


@app.get("/assetinfo/repayment-plan-records", response_class=HTMLResponse)
def assetinfo_repayment_plan_records_page(
    page_user: Annotated[dict, Depends(get_page_user)],
    page: str | None = Query(default=None),
    page_size: str | None = Query(default=None),
    trust_product_id: str | None = Query(default=None),
    data_date: str | None = Query(default=None),
    asset_code: str | None = Query(default=None),
    custody_asset_code: str | None = Query(default=None),
    source_asset_code: str | None = Query(default=None),
    source_file_name: str | None = Query(default=None),
    source_sheet_name: str | None = Query(default=None),
):
    page_no, page_sz = query_utils.parse_pagination(page, page_size)
    filters = assetinfo_upload.build_record_filters(
        trust_product_id=trust_product_id,
        data_date=data_date,
        asset_code=asset_code,
        custody_asset_code=custody_asset_code,
        source_asset_code=source_asset_code,
        source_file_name=source_file_name,
        source_sheet_name=source_sheet_name,
    )
    with engine.connect() as conn:
        data = assetinfo_upload.fetch_paginated_records(
            conn, "repayment_plan", page_no, page_sz, filters,
        )
        products = [
            {"id": r.id, "name": r.name}
            for r in conn.execute(text("SELECT id, name FROM trust_products ORDER BY id"))
        ]
    html = assetinfo_html.render_records_page(
        "回款计划数据", "/assetinfo/repayment-plan-records/data", filters, data, products,
        record_type="repayment_plan",
    )
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


def _build_monitor_record_filters(
    *,
    trust_product_id: str | None = None,
    data_date: str | None = None,
    asset_code: str | None = None,
    custody_asset_code: str | None = None,
    source_asset_code: str | None = None,
    source_file_name: str | None = None,
    source_sheet_name: str | None = None,
    include_history: str | None = None,
    transferred: str | None = None,
    asset_transfer_discount_rate: str | None = None,
    city: str | None = None,
    sort_by: str | None = None,
    sort_dir: str | None = None,
) -> dict:
    return assetinfo_upload.build_record_filters(
        trust_product_id=trust_product_id,
        data_date=data_date,
        asset_code=asset_code,
        custody_asset_code=custody_asset_code,
        source_asset_code=source_asset_code,
        source_file_name=source_file_name,
        source_sheet_name=source_sheet_name,
        include_history=include_history,
        transferred=transferred,
        asset_transfer_discount_rate=asset_transfer_discount_rate,
        city=city,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@app.get("/assetinfo/monitor-records/data")
def assetinfo_monitor_records_data(
    current_user: Annotated[dict, Depends(get_current_user)],
    page: str | None = Query(default=None),
    page_size: str | None = Query(default=None),
    trust_product_id: str | None = Query(default=None),
    data_date: str | None = Query(default=None),
    asset_code: str | None = Query(default=None),
    custody_asset_code: str | None = Query(default=None),
    source_asset_code: str | None = Query(default=None),
    source_file_name: str | None = Query(default=None),
    source_sheet_name: str | None = Query(default=None),
    include_history: str | None = Query(default=None),
    transferred: str | None = Query(default=None),
    asset_transfer_discount_rate: str | None = Query(default=None),
    city: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str | None = Query(default=None),
):
    page_no, page_sz = query_utils.parse_pagination(page, page_size)
    filters = _build_monitor_record_filters(
        trust_product_id=trust_product_id,
        data_date=data_date,
        asset_code=asset_code,
        custody_asset_code=custody_asset_code,
        source_asset_code=source_asset_code,
        source_file_name=source_file_name,
        source_sheet_name=source_sheet_name,
        include_history=include_history,
        transferred=transferred,
        asset_transfer_discount_rate=asset_transfer_discount_rate,
        city=city,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    with engine.connect() as conn:
        return assetinfo_upload.fetch_paginated_records(
            conn, "monitor", page_no, page_sz, filters,
        )


@app.get("/assetinfo/monitor-records", response_class=HTMLResponse)
def assetinfo_monitor_records_page(
    page_user: Annotated[dict, Depends(get_page_user)],
    page: str | None = Query(default=None),
    page_size: str | None = Query(default=None),
    trust_product_id: str | None = Query(default=None),
    data_date: str | None = Query(default=None),
    asset_code: str | None = Query(default=None),
    custody_asset_code: str | None = Query(default=None),
    source_asset_code: str | None = Query(default=None),
    source_file_name: str | None = Query(default=None),
    source_sheet_name: str | None = Query(default=None),
    include_history: str | None = Query(default=None),
    transferred: str | None = Query(default=None),
    asset_transfer_discount_rate: str | None = Query(default=None),
    city: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str | None = Query(default=None),
):
    page_no, page_sz = query_utils.parse_pagination(page, page_size)
    filters = _build_monitor_record_filters(
        trust_product_id=trust_product_id,
        data_date=data_date,
        asset_code=asset_code,
        custody_asset_code=custody_asset_code,
        source_asset_code=source_asset_code,
        source_file_name=source_file_name,
        source_sheet_name=source_sheet_name,
        include_history=include_history,
        transferred=transferred,
        asset_transfer_discount_rate=asset_transfer_discount_rate,
        city=city,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    with engine.connect() as conn:
        data = assetinfo_upload.fetch_paginated_records(
            conn, "monitor", page_no, page_sz, filters,
        )
        products = [
            {"id": r.id, "name": r.name}
            for r in conn.execute(text("SELECT id, name FROM trust_products ORDER BY id"))
        ]
        discount_rate_options = assetinfo_upload.fetch_monitor_discount_rate_options(
            conn, filters.get("trust_product_id"),
        )
        city_options = assetinfo_upload.fetch_monitor_city_options(
            conn, filters.get("trust_product_id"),
        )
    html = assetinfo_html.render_records_page(
        "资产监控导入数据", "/assetinfo/monitor-records/data", filters, data, products,
        record_type="monitor",
        discount_rate_options=discount_rate_options,
        city_options=city_options,
    )
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


def _disclosure_product_ids(
    trust_product_id: str | None,
    trust_product_ids: list[str] | None,
) -> list[int] | None:
    return query_utils.parse_trust_product_ids(trust_product_id, trust_product_ids)


@app.get("/disclosure/repayment", response_class=HTMLResponse)
def disclosure_repayment_page(
    page_user: Annotated[dict, Depends(get_page_user)],
    trust_product_id: str | None = None,
    trust_product_ids: list[str] | None = Query(default=None),
    as_of: str | None = None,
):
    pids = _disclosure_product_ids(trust_product_id, trust_product_ids)
    with engine.connect() as conn:
        products = fetch_trust_products(conn)
        snapshots = disclosure.list_snapshots(conn, "repayment")
    if not pids:
        pids = [int(p["id"]) for p in products]
    as_of_val = query_utils.parse_optional_date(as_of) or date.today().isoformat()
    html = disclosure_html.render_repayment_disclosure_page(
        products,
        snapshots,
        selected_ids=pids,
        as_of=as_of_val,
        username=page_user["username"],
    )
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


@app.get("/disclosure/monitor", response_class=HTMLResponse)
def disclosure_monitor_page(
    page_user: Annotated[dict, Depends(get_page_user)],
    trust_product_id: str | None = None,
    trust_product_ids: list[str] | None = Query(default=None),
    as_of: str | None = None,
):
    pids = _disclosure_product_ids(trust_product_id, trust_product_ids)
    with engine.connect() as conn:
        products = fetch_trust_products(conn)
        snapshots = disclosure.list_snapshots(conn, "monitor")
    if not pids:
        pids = [int(p["id"]) for p in products]
    as_of_val = query_utils.parse_optional_date(as_of) or date.today().isoformat()
    html = disclosure_html.render_monitor_disclosure_page(
        products,
        snapshots,
        selected_ids=pids,
        as_of=as_of_val,
        username=page_user["username"],
    )
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


@app.get("/disclosure/repayment/snapshots")
def disclosure_repayment_snapshots(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    with engine.connect() as conn:
        return {"items": disclosure.list_snapshots(conn, "repayment")}


@app.get("/disclosure/monitor/snapshots")
def disclosure_monitor_snapshots(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    with engine.connect() as conn:
        return {"items": disclosure.list_snapshots(conn, "monitor")}


@app.get("/disclosure/repayment/preview")
def disclosure_repayment_preview(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str | None = None,
    trust_product_ids: list[str] | None = Query(default=None),
    as_of: str | None = None,
    snapshot_id: int | None = None,
):
    with engine.connect() as conn:
        if snapshot_id is not None:
            return disclosure.preview_repayment_snapshot(conn, int(snapshot_id))
        pids = _disclosure_product_ids(trust_product_id, trust_product_ids)
        return disclosure.preview_repayment_live(
            conn, pids or [], disclosure.parse_as_of_date(as_of),
        )


@app.get("/disclosure/monitor/preview")
def disclosure_monitor_preview(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str | None = None,
    trust_product_ids: list[str] | None = Query(default=None),
    as_of: str | None = None,
    snapshot_id: int | None = None,
):
    with engine.connect() as conn:
        if snapshot_id is not None:
            return disclosure.preview_monitor_snapshot(conn, int(snapshot_id))
        pids = _disclosure_product_ids(trust_product_id, trust_product_ids)
        return disclosure.preview_monitor_live(
            conn, pids or [], disclosure.parse_as_of_date(as_of),
        )


@app.post("/disclosure/repayment/freeze")
def disclosure_repayment_freeze(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str | None = None,
    trust_product_ids: list[str] | None = Query(default=None),
    as_of: str | None = None,
    note: str | None = None,
):
    pids = _disclosure_product_ids(trust_product_id, trust_product_ids)
    with engine.begin() as conn:
        return disclosure.freeze_repayment(
            conn,
            pids or [],
            disclosure.parse_as_of_date(as_of),
            note=note,
            created_by=current_user.get("username"),
        )


@app.post("/disclosure/monitor/freeze")
def disclosure_monitor_freeze(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str | None = None,
    trust_product_ids: list[str] | None = Query(default=None),
    as_of: str | None = None,
    note: str | None = None,
):
    pids = _disclosure_product_ids(trust_product_id, trust_product_ids)
    with engine.begin() as conn:
        return disclosure.freeze_monitor(
            conn,
            pids or [],
            disclosure.parse_as_of_date(as_of),
            note=note,
            created_by=current_user.get("username"),
        )


@app.delete("/disclosure/snapshots/{snapshot_id}")
def disclosure_snapshot_delete(
    snapshot_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    with engine.begin() as conn:
        return disclosure.delete_snapshot(conn, snapshot_id)


@app.get("/disclosure/repayment/export")
def disclosure_repayment_export(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str | None = None,
    trust_product_ids: list[str] | None = Query(default=None),
    as_of: str | None = None,
    snapshot_id: int | None = None,
):
    pids = _disclosure_product_ids(trust_product_id, trust_product_ids)
    with engine.connect() as conn:
        xlsx_bytes = disclosure.export_repayment_xlsx(
            conn,
            product_ids=pids,
            as_of=disclosure.parse_as_of_date(as_of) if as_of else None,
            snapshot_id=int(snapshot_id) if snapshot_id is not None else None,
        )
    ts = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S")
    filename = f"还款明细披露信息_{ts}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@app.get("/disclosure/monitor/export")
def disclosure_monitor_export(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str | None = None,
    trust_product_ids: list[str] | None = Query(default=None),
    as_of: str | None = None,
    snapshot_id: int | None = None,
):
    pids = _disclosure_product_ids(trust_product_id, trust_product_ids)
    with engine.connect() as conn:
        xlsx_bytes = disclosure.export_monitor_xlsx(
            conn,
            product_ids=pids,
            as_of=disclosure.parse_as_of_date(as_of) if as_of else None,
            snapshot_id=int(snapshot_id) if snapshot_id is not None else None,
        )
    ts = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S")
    filename = f"资产监控表_{ts}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@app.get("/assetinfo/repayment-records/export")
def assetinfo_repayment_records_export(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str | None = Query(default=None),
    data_date: str | None = Query(default=None),
    asset_code: str | None = Query(default=None),
    custody_asset_code: str | None = Query(default=None),
    source_asset_code: str | None = Query(default=None),
    source_file_name: str | None = Query(default=None),
    source_sheet_name: str | None = Query(default=None),
):
    filters = assetinfo_upload.build_record_filters(
        trust_product_id=trust_product_id,
        data_date=data_date,
        asset_code=asset_code,
        custody_asset_code=custody_asset_code,
        source_asset_code=source_asset_code,
        source_file_name=source_file_name,
        source_sheet_name=source_sheet_name,
    )
    with engine.connect() as conn:
        repayment_items, _total = assetinfo_upload.fetch_repayment_records_for_export(
            conn, filters,
        )
        plan_items = assetinfo_upload.fetch_repayment_plan_records_for_export(conn, filters)
    xlsx_bytes = assetinfo_upload.build_repayment_disclosure_export_xlsx(
        repayment_items, plan_items,
    )
    ts = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S")
    filename = f"还款明细披露信息_{ts}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@app.get("/assetinfo/monitor-records/export")
def assetinfo_monitor_records_export(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str | None = Query(default=None),
    data_date: str | None = Query(default=None),
    asset_code: str | None = Query(default=None),
    custody_asset_code: str | None = Query(default=None),
    source_asset_code: str | None = Query(default=None),
    source_file_name: str | None = Query(default=None),
    source_sheet_name: str | None = Query(default=None),
    include_history: str | None = Query(default=None),
    transferred: str | None = Query(default=None),
    asset_transfer_discount_rate: str | None = Query(default=None),
    city: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str | None = Query(default=None),
):
    filters = _build_monitor_record_filters(
        trust_product_id=trust_product_id,
        data_date=data_date,
        asset_code=asset_code,
        custody_asset_code=custody_asset_code,
        source_asset_code=source_asset_code,
        source_file_name=source_file_name,
        source_sheet_name=source_sheet_name,
        include_history=include_history,
        transferred=transferred,
        asset_transfer_discount_rate=asset_transfer_discount_rate,
        city=city,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    with engine.connect() as conn:
        items, _total = assetinfo_upload.fetch_monitor_records_for_export(conn, filters)
    xlsx_bytes = assetinfo_upload.build_monitor_export_xlsx(items)
    ts = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S")
    filename = f"资产监控导入数据_{ts}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@app.get("/asset-swap", response_class=HTMLResponse)
def asset_swap_page(
    page_user: Annotated[dict, Depends(get_page_user)],
):
    with engine.connect() as conn:
        products = asset_swap.fetch_meihaosheng_products(conn)
    html = asset_swap_html.render_swap_page(
        products,
        username=page_user["username"],
    )
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


@app.get("/asset-swap/data")
def asset_swap_data(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str = Query(...),
    asset_codes: list[str] = Query(default=[]),
    exclude_asset_codes: list[str] = Query(default=[]),
    required_asset_codes: list[str] = Query(default=[]),
):
    pid = query_utils.parse_optional_int(trust_product_id)
    if pid is None:
        raise HTTPException(status_code=400, detail="请选择信托产品")
    parsed_codes = asset_swap.parse_asset_code_list(
        asset_codes,
        max_count=asset_swap.MAX_SOURCE_ASSETS,
        field_label="转出资产编号",
    )
    with engine.connect() as conn:
        return asset_swap.fetch_swap_recommendations(
            conn,
            trust_product_id=pid,
            asset_codes=parsed_codes,
            exclude_asset_codes=exclude_asset_codes or None,
            required_asset_codes=required_asset_codes or None,
        )


def _parse_swap_payload(body: dict) -> dict:
    pid = query_utils.parse_optional_int(body.get("trust_product_id"))
    if pid is None:
        raise HTTPException(status_code=400, detail="请选择信托产品")
    scheme_id = query_utils.clean_optional_str(body.get("scheme_id")) or "manual"
    biz_raw = query_utils.parse_optional_date(body.get("swap_business_date"))
    if not biz_raw:
        biz_date = date.today()
    else:
        try:
            biz_date = date.fromisoformat(biz_raw[:10])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="置换业务日无效") from exc
    source_codes = body.get("source_asset_codes") or []
    candidate_codes = body.get("candidate_asset_codes") or []
    if isinstance(source_codes, str):
        source_codes = [source_codes]
    if isinstance(candidate_codes, str):
        candidate_codes = [candidate_codes]
    note = query_utils.clean_optional_str(body.get("note"))
    return {
        "trust_product_id": pid,
        "source_asset_codes": source_codes,
        "candidate_asset_codes": candidate_codes,
        "scheme_id": scheme_id,
        "swap_business_date": biz_date,
        "note": note,
    }


@app.post("/asset-swap/preview")
def asset_swap_preview(
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(...),
):
    payload = _parse_swap_payload(body)
    with engine.connect() as conn:
        return asset_swap.build_swap_preview(
            conn,
            trust_product_id=payload["trust_product_id"],
            source_asset_codes=payload["source_asset_codes"],
            candidate_asset_codes=payload["candidate_asset_codes"],
            scheme_id=payload["scheme_id"],
            swap_business_date=payload["swap_business_date"],
        )


@app.post("/asset-swap/execute")
def asset_swap_execute(
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(...),
):
    payload = _parse_swap_payload(body)
    with engine.begin() as conn:
        return asset_swap.execute_swap(
            conn,
            trust_product_id=payload["trust_product_id"],
            source_asset_codes=payload["source_asset_codes"],
            candidate_asset_codes=payload["candidate_asset_codes"],
            scheme_id=payload["scheme_id"],
            swap_business_date=payload["swap_business_date"],
            note=payload["note"],
            executed_by=current_user.get("username"),
        )


@app.get("/asset-swap/orders")
def asset_swap_orders_list(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    with engine.connect() as conn:
        return {"items": asset_swap.list_swap_orders(conn)}


@app.get("/asset-swap/orders/{order_id}")
def asset_swap_order_detail(
    order_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    with engine.connect() as conn:
        return asset_swap.get_swap_order(conn, order_id)


@app.post("/asset-swap/orders/{order_id}/void")
def asset_swap_order_void(
    order_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    with engine.begin() as conn:
        return asset_swap.void_swap_order(
            conn,
            order_id,
            voided_by=current_user.get("username"),
        )


def _parse_asset_stats_dates(
    date_from_raw: str | None,
    date_to_raw: str | None,
) -> tuple[date, date]:
    today = date.today()
    parsed_from = query_utils.parse_optional_date(date_from_raw)
    parsed_to = query_utils.parse_optional_date(date_to_raw)
    date_from = date.fromisoformat(parsed_from[:10]) if parsed_from else date(today.year, 1, 1)
    date_to = date.fromisoformat(parsed_to[:10]) if parsed_to else today
    if date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from 不能晚于 date_to")
    return date_from, date_to


def _parse_asset_stats_issue_date(issue_date: str | None) -> str | None:
    cleaned = query_utils.clean_optional_str(issue_date)
    if not cleaned:
        return None
    if cleaned.lower() == repayment_analytics.ISSUE_DATE_ALL:
        return repayment_analytics.ISSUE_DATE_ALL
    parsed = query_utils.parse_optional_date(cleaned)
    if parsed:
        return parsed[:10]
    raise HTTPException(status_code=400, detail="issue_date 无效")


@app.get("/assetinfo/asset-stats/issue-dates")
def asset_stats_issue_dates(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str = Query(...),
):
    pid = query_utils.parse_optional_int(trust_product_id)
    if pid is None:
        raise HTTPException(status_code=400, detail="trust_product_id 无效")
    with engine.connect() as conn:
        items = repayment_analytics.fetch_issue_dates(conn, pid)
        all_summary = repayment_analytics.fetch_all_issue_summary(conn, pid)
    return {"items": items, "all": all_summary}


@app.get("/assetinfo/asset-stats/cities")
def asset_stats_cities(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str = Query(...),
    issue_date: str = Query(...),
):
    pid = query_utils.parse_optional_int(trust_product_id)
    if pid is None:
        raise HTTPException(status_code=400, detail="trust_product_id 无效")
    issue_key = _parse_asset_stats_issue_date(issue_date)
    with engine.connect() as conn:
        items = repayment_analytics.fetch_issuance_cities(conn, pid, issue_key)
    return {"items": items}


@app.get("/assetinfo/asset-stats/data")
def asset_stats_data(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: str = Query(...),
    issue_date: str | None = Query(default=None),
    period: str = Query(default="month"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    city: str | None = Query(default=None),
):
    pid = query_utils.parse_optional_int(trust_product_id)
    if pid is None:
        raise HTTPException(status_code=400, detail="trust_product_id 无效")
    if period not in ("week", "month", "year"):
        raise HTTPException(status_code=400, detail="period 须为 week/month/year")
    d_from, d_to = _parse_asset_stats_dates(date_from, date_to)
    issue_str = _parse_asset_stats_issue_date(issue_date)
    city_filter = query_utils.clean_optional_str(city)
    with engine.connect() as conn:
        try:
            return repayment_analytics.build_asset_stats_report(
                conn,
                trust_product_id=pid,
                issue_date=issue_str,
                period=period,  # type: ignore[arg-type]
                date_from=d_from,
                date_to=d_to,
                city=city_filter,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/assetinfo/asset-stats", response_class=HTMLResponse)
def asset_stats_page(
    page_user: Annotated[dict, Depends(get_page_user)],
    trust_product_id: str | None = Query(default=None),
    issue_date: str | None = Query(default=None),
    period: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    city: str | None = Query(default=None),
):
    pid = query_utils.parse_optional_int(trust_product_id)
    issue_str = _parse_asset_stats_issue_date(issue_date) if issue_date else None
    period_val = period if period in ("week", "month", "year") else "month"
    with engine.connect() as conn:
        products = [
            {"id": r.id, "name": r.name}
            for r in conn.execute(text("SELECT id, name FROM trust_products ORDER BY id"))
        ]
    html = repayment_analytics_html.render_asset_stats_page(
        products,
        trust_product_id=pid,
        issue_date=issue_str,
        period=period_val,
        date_from=date_from,
        date_to=date_to,
        city=query_utils.clean_optional_str(city),
    )
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


@app.get("/issuance/upload", response_class=HTMLResponse)
def issuance_upload_page(page_user: Annotated[dict, Depends(get_page_user)]):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, name FROM trust_products ORDER BY id"))
        products = [{"id": r.id, "name": r.name} for r in rows]
    html = issuance_html.render_upload_page(products)
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


@app.post("/issuance/preview")
async def issuance_preview(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: int = Form(...),
    issue_date: str = Form(...),
    files: list[UploadFile] = File(...),
):
    parsed_issue = query_utils.parse_optional_date(issue_date)
    if not parsed_issue:
        raise HTTPException(status_code=400, detail="issue_date 无效")
    issue = date.fromisoformat(parsed_issue[:10])
    batch_uuid = str(uuid.uuid4())
    saved = await issuance_upload.save_batch_files(batch_uuid, files)
    with engine.connect() as conn:
        return issuance_upload.run_preview(conn, trust_product_id, issue, batch_uuid, saved)


@app.post("/issuance/import")
def issuance_import(
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(...),
):
    batch_uuid = body.get("batch_uuid") or body.get("file_id")
    trust_product_id = body.get("trust_product_id")
    issue_date_raw = body.get("issue_date")
    if not batch_uuid or trust_product_id is None or not issue_date_raw:
        raise HTTPException(
            status_code=400,
            detail="batch_uuid/file_id, trust_product_id and issue_date required",
        )
    parsed_issue = query_utils.parse_optional_date(str(issue_date_raw))
    if not parsed_issue:
        raise HTTPException(status_code=400, detail="issue_date 无效")
    issue = date.fromisoformat(parsed_issue[:10])
    with engine.connect() as conn:
        return issuance_upload.run_import(
            conn,
            batch_uuid=batch_uuid,
            trust_product_id=int(trust_product_id),
            issue_date=issue,
            user_id=current_user["id"],
            selected_sheet_keys=body.get("selected_sheet_keys"),
            confirm_sheet_keys=body.get("confirm_sheet_keys"),
        )


@app.get("/issuance/records/data")
def issuance_records_data(
    current_user: Annotated[dict, Depends(get_current_user)],
    page: str | None = Query(default=None),
    page_size: str | None = Query(default=None),
    trust_product_id: str | None = Query(default=None),
    trust_product_name: str | None = Query(default=None),
    from_trust_product_id: str | None = Query(default=None),
    from_trust_product_name: str | None = Query(default=None),
    issue_date: str | None = Query(default=None),
    custody_asset_code: str | None = Query(default=None),
    business_asset_key: str | None = Query(default=None),
    city: str | None = Query(default=None),
    source_file_name: str | None = Query(default=None),
    source_sheet_name: str | None = Query(default=None),
    migration_type: str | None = Query(default=None),
):
    page_no, page_sz = query_utils.parse_pagination(page, page_size)
    filters = issuance_upload.build_record_filters(
        trust_product_id=trust_product_id,
        trust_product_name=trust_product_name,
        from_trust_product_id=from_trust_product_id,
        from_trust_product_name=from_trust_product_name,
        issue_date=issue_date,
        custody_asset_code=custody_asset_code,
        business_asset_key=business_asset_key,
        city=city,
        source_file_name=source_file_name,
        source_sheet_name=source_sheet_name,
        migration_type=migration_type,
    )
    with engine.connect() as conn:
        return issuance_upload.fetch_paginated_records(conn, page_no, page_sz, filters)


@app.get("/issuance/records", response_class=HTMLResponse)
def issuance_records_page(
    page_user: Annotated[dict, Depends(get_page_user)],
    page: str | None = Query(default=None),
    page_size: str | None = Query(default=None),
    trust_product_id: str | None = Query(default=None),
    trust_product_name: str | None = Query(default=None),
    from_trust_product_id: str | None = Query(default=None),
    from_trust_product_name: str | None = Query(default=None),
    issue_date: str | None = Query(default=None),
    custody_asset_code: str | None = Query(default=None),
    business_asset_key: str | None = Query(default=None),
    city: str | None = Query(default=None),
    source_file_name: str | None = Query(default=None),
    source_sheet_name: str | None = Query(default=None),
    migration_type: str | None = Query(default=None),
):
    page_no, page_sz = query_utils.parse_pagination(page, page_size)
    filters = issuance_upload.build_record_filters(
        trust_product_id=trust_product_id,
        trust_product_name=trust_product_name,
        from_trust_product_id=from_trust_product_id,
        from_trust_product_name=from_trust_product_name,
        issue_date=issue_date,
        custody_asset_code=custody_asset_code,
        business_asset_key=business_asset_key,
        city=city,
        source_file_name=source_file_name,
        source_sheet_name=source_sheet_name,
        migration_type=migration_type,
    )
    with engine.connect() as conn:
        data = issuance_upload.fetch_paginated_records(conn, page_no, page_sz, filters)
        products = [
            {"id": r.id, "name": r.name}
            for r in conn.execute(text("SELECT id, name FROM trust_products ORDER BY id"))
        ]
        city_options = issuance_upload.fetch_issuance_record_cities(
            conn, filters.get("trust_product_id")
        )
    html = issuance_html.render_records_page(filters, data, products, city_options)
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))
