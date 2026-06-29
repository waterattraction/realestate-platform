"""Overdue workbench HTML — dumb render from get_detail() DTO only."""

from html import escape
from urllib.parse import quote

from app.field_labels import (
    ASSET_CODE_LABEL,
    CUSTODY_ASSET_CODE_LABEL,
    SOURCE_ASSET_CODE_LABEL,
)
from app.html.formatters import (
    fmt_check_result,
    fmt_delinquency_badge,
    fmt_money,
    fmt_risk_badge,
)
from app.issuance_labels import format_rate, migration_type_label
from app.overdue.ui_constants import (
    FOLLOWUP_STATUS_LABELS,
    INTERNAL_STATUS_OPTIONS,
    TRUST_MARKER_OPTIONS,
)
from app.service.checks_service import RECONCILIATION_BASIS_LABEL
from app.service.overdue_workbench import DEFAULT_DELINQUENCY_BUCKET
from app.ui_css import (
    BTN_CSS,
    PAGE_CHROME_CSS,
    STANDARD_HEADER_CSS,
    TABLE_SCROLL_CSS,
    WORKBENCH_BODY_CSS,
)

_TIMELINE_PREVIEW = 3
_REPAYMENT_PREVIEW = 3
_PANEL_PREVIEW_ROWS = 3

_BUCKET_FILTER_OPTIONS = [
    ("M2_PLUS", "M2+"),
    ("M2", "M2"),
    ("M3", "M3"),
    ("M3_PLUS", "M3+"),
    ("M1", "M1"),
    ("ES", "ES"),
]


def _filter_bar_product_id(dto: dict) -> int | None:
    filters = dto.get("filters") or {}
    if filters.get("list_product_scope_explicit"):
        return filters.get("list_product_id")
    return dto.get("trust_product_id")


def _append_list_product_qs(parts: list[str], filters: dict, *, list_filter: int | None) -> None:
    if filters.get("list_product_scope_explicit"):
        parts.append(
            f"list_product_id={list_filter}" if list_filter is not None else "list_product_id="
        )
    elif list_filter is None and filters.get("trust_product_id"):
        parts.append("list_product_id=")


def _asset_list_item_href(
    item: dict,
    *,
    filters: dict,
    bucket: str,
    data_date: str | None,
    list_filter: int | None,
) -> str:
    ac = item.get("asset_code") or ""
    pid = item.get("trust_product_id")
    parts = [f"trust_product_id={pid}", f"asset_code={quote(str(ac))}"]
    if bucket:
        parts.append(f"delinquency_bucket={quote(str(bucket))}")
    if data_date:
        parts.append(f"data_date={quote(str(data_date))}")
    if list_filter is None and pid is not None:
        parts.append("list_product_id=")
    elif filters.get("list_product_scope_explicit"):
        parts.append(
            f"list_product_id={list_filter}" if list_filter is not None else "list_product_id="
        )
    return f"/overdue/workbench?{'&'.join(parts)}"


def _is_selected_asset_item(
    item_product_id,
    item_asset_code,
    *,
    selected_product_id: int | None,
    selected_asset_code: str | None,
) -> bool:
    if not selected_asset_code or not selected_product_id:
        return False
    return (
        str(item_asset_code) == str(selected_asset_code)
        and int(item_product_id) == int(selected_product_id)
    )


def render_overdue_workbench_html(
    dto: dict,
    *,
    new_followup: bool = False,
) -> str:
    if dto.get("legacy_error"):
        return _render_legacy_error_page(dto)

    trust_product_id = dto.get("trust_product_id")
    current_asset_code = dto.get("asset_code")
    filters = dto.get("filters") or {}
    delinquency_bucket = filters.get("delinquency_bucket") or DEFAULT_DELINQUENCY_BUCKET
    asset = dto.get("asset") or {}
    selected_trust_asset_id = asset.get("selected_trust_asset_id")

    def workbench_qs(trust_asset_id: int | None = None, asset_code: str | None = None) -> str:
        parts: list[str] = []
        if trust_product_id is not None:
            parts.append(f"trust_product_id={trust_product_id}")
        ac = asset_code if asset_code is not None else current_asset_code
        if ac:
            parts.append(f"asset_code={quote(str(ac))}")
        if delinquency_bucket:
            parts.append(f"delinquency_bucket={quote(str(delinquency_bucket))}")
        if dto.get("data_date"):
            parts.append(f"data_date={quote(str(dto['data_date']))}")
        tid = trust_asset_id if trust_asset_id is not None else selected_trust_asset_id
        if tid is not None:
            parts.append(f"trust_asset_id={tid}")
        _append_list_product_qs(parts, filters, list_filter=_filter_bar_product_id(dto))
        return "?" + "&".join(parts) if parts else ""

    product_hidden = (
        f'<input type="hidden" name="trust_product_id" value="{trust_product_id}">'
        if trust_product_id is not None
        else ""
    )
    asset_hidden = (
        f'<input type="hidden" name="asset_code" value="{escape(str(current_asset_code))}">'
        if current_asset_code
        else ""
    )
    bucket_hidden = (
        f'<input type="hidden" name="delinquency_bucket" value="{escape(delinquency_bucket)}">'
    )

    sidebar_html = _render_sidebar(dto, trust_product_id, current_asset_code, workbench_qs)
    detail_html = _render_panels(dto, asset, workbench_qs)
    json_qs = workbench_qs()
    identity_id = dto.get("identity_id")
    header_actions = _render_header_actions(trust_product_id, json_qs, identity_id)
    selection_notice = _render_selection_notice(dto.get("selection_notice"))
    data_date_display = escape(str(dto.get("data_date") or ""))
    data_date_span = (
        f' <span class="header-data-date">· 数据日期 {data_date_display}</span>'
        if data_date_display else ""
    )
    write_bar = ""
    if asset.get("selected_split") or asset.get("monitor", {}).get("splits"):
        write_bar = _panel_followup_write(
            product_hidden,
            asset_hidden,
            bucket_hidden,
            workbench_qs,
            dto,
            new_followup=new_followup,
        )

    scroll_flag = "1" if new_followup else "0"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>资产逾期跟进工作台 · 房地产资产证券化平台</title>
    {_WORKBENCH_CSS}
</head>
<body class="workbench-page" data-scroll-followup="{scroll_flag}">
<div class="page-wrap">
<div class="container">
    <div class="breadcrumb">
        <a href="/">首页</a> / <a href="/overdue">逾期管理</a> / 资产逾期跟进工作台
    </div>
    <header class="page-header">
        <div class="header-row">
            <h1>资产逾期跟进工作台</h1>
            {header_actions}
        </div>
        <p class="header-sub muted">按资产主编号统一管理监控、还款、跟进与风险。{data_date_span}</p>
        {selection_notice}
    </header>
    <div class="workbench">
        <aside class="sidebar panel">
            {sidebar_html}
        </aside>
        <main class="detail-main">
            {detail_html}
            {write_bar}
        </main>
    </div>
</div>
</div>
{_WORKBENCH_SCRIPTS}
</body>
</html>"""


def _render_legacy_error_page(dto: dict) -> str:
    err = dto.get("legacy_error") or {}
    message = escape(str(err.get("message") or "无法打开工作台"))
    candidates = err.get("candidates") or []
    links = ""
    for cand in candidates:
        url = escape(str(cand.get("url") or ""))
        code = escape(str(cand.get("asset_code") or ""))
        links += f'<li><a href="{url}">{ASSET_CODE_LABEL} {code}</a></li>'
    list_html = f"<ul>{links}</ul>" if links else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>资产逾期跟进工作台 · 无法解析</title>
    {_WORKBENCH_CSS}
</head>
<body>
<div class="page-wrap"><div class="container">
    <div class="breadcrumb">
        <a href="/">首页</a> / <a href="/overdue">逾期管理</a> / 资产逾期跟进工作台
    </div>
    <header class="page-header">
        <h1>资产逾期跟进工作台</h1>
        <p class="header-sub muted">按资产主编号统一管理监控、还款、跟进与风险。</p>
    </header>
    <div class="panel" style="padding:1.25rem">
        <p class="warn-text">{message}</p>
        {list_html}
        <p style="margin-top:1rem"><a href="/overdue/workbench">返回资产清单</a></p>
    </div>
</div></div>
</body>
</html>"""


def _render_sidebar_filter(dto: dict) -> str:
    """Compact inline-edit filter row rendered inside the sidebar below the panel-hd."""
    filters = dto.get("filters") or {}
    active_bucket = filters.get("delinquency_bucket") or DEFAULT_DELINQUENCY_BUCKET
    active_marker = filters.get("trust_marker") or ""
    active_status = filters.get("followup_status") or ""
    filter_pid = _filter_bar_product_id(dto)
    data_date = dto.get("data_date") or ""
    products = dto.get("products") or []
    current_asset = dto.get("asset_code")
    detail_pid = dto.get("trust_product_id")

    # Display labels
    product_name = next((p["name"] for p in products if filter_pid == p["id"]), "全部产品")
    bucket_label = dict(_BUCKET_FILTER_OPTIONS).get(active_bucket, active_bucket)
    marker_label = active_marker or "全部标记"
    status_label = active_status or "全部状态"

    # Options
    product_opts = '<option value="">全部产品</option>'
    for p in products:
        sel = " selected" if filter_pid == p["id"] else ""
        product_opts += f'<option value="{p["id"]}"{sel}>{escape(p["name"])}</option>'

    bucket_opts = ""
    for val, label in _BUCKET_FILTER_OPTIONS:
        sel = " selected" if active_bucket == val else ""
        bucket_opts += f'<option value="{val}"{sel}>{escape(label)}</option>'

    marker_opts = '<option value="">全部标记</option>'
    for m in TRUST_MARKER_OPTIONS:
        sel = " selected" if active_marker == m else ""
        marker_opts += f'<option value="{escape(m)}"{sel}>{escape(m)}</option>'

    status_opts = '<option value="">全部状态</option>'
    for s in INTERNAL_STATUS_OPTIONS:
        sel = " selected" if active_status == s else ""
        status_opts += f'<option value="{escape(s)}"{sel}>{escape(s)}</option>'

    # Hidden fields
    detail_fields = ""
    if current_asset and detail_pid is not None:
        detail_fields = (
            f'<input type="hidden" name="trust_product_id" value="{detail_pid}">'
            f'<input type="hidden" name="asset_code" value="{escape(str(current_asset))}">'
        )
    date_hidden = f'<input type="hidden" name="data_date" value="{escape(str(data_date))}">' if data_date else ""

    def item(title: str, label: str, name: str, opts: str) -> str:
        return (
            f'<span class="sf-item" title="{title}">'
            f'<span class="sf-display">{escape(label)}</span>'
            f'<select class="sf-select" name="{name}">{opts}</select>'
            f'</span>'
        )

    return (
        f'<form class="sidebar-filter" method="get" action="/overdue/workbench" id="sf-form">'
        + item("双击修改产品", product_name, "list_product_id", product_opts)
        + '<span class="sf-sep">·</span>'
        + item("双击修改M级", bucket_label, "delinquency_bucket", bucket_opts)
        + '<span class="sf-sep">·</span>'
        + item("双击修改信托标记", marker_label, "trust_marker", marker_opts)
        + '<span class="sf-sep">·</span>'
        + item("双击修改跟进状态", status_label, "followup_status", status_opts)
        + date_hidden + detail_fields
        + '</form>'
    )


def _render_filter_bar(dto: dict, workbench_qs) -> str:
    filters = dto.get("filters") or {}
    active_bucket = filters.get("delinquency_bucket") or DEFAULT_DELINQUENCY_BUCKET
    filter_pid = _filter_bar_product_id(dto)
    data_date = dto.get("data_date") or ""
    products = dto.get("products") or []
    current_asset = dto.get("asset_code")
    detail_pid = dto.get("trust_product_id")

    product_opts = '<option value="">全部信托产品</option>'
    for p in products:
        sel = " selected" if filter_pid == p["id"] else ""
        product_opts += (
            f'<option value="{p["id"]}"{sel}>{escape(p["name"])}</option>'
        )

    bucket_opts = ""
    for val, label in _BUCKET_FILTER_OPTIONS:
        sel = " selected" if active_bucket == val else ""
        bucket_opts += f'<option value="{val}"{sel}>{escape(label)}</option>'

    detail_fields = ""
    if current_asset and detail_pid is not None:
        detail_fields = (
            f'<input type="hidden" name="trust_product_id" value="{detail_pid}">'
            f'<input type="hidden" name="asset_code" value="{escape(str(current_asset))}">'
        )

    date_hidden = ""
    if data_date:
        date_hidden = f'<input type="hidden" name="data_date" value="{escape(str(data_date))}">'

    return f"""<form class="filter-form workbench-filter" method="get" action="/overdue/workbench">
        <label>信托产品
            <select name="list_product_id">{product_opts}</select>
        </label>
        <label>M 级
            <select name="delinquency_bucket">{bucket_opts}</select>
        </label>
        <span class="filter-readonly-date">
            <span class="filter-readonly-lbl">数据日期</span>
            <span class="filter-date-val">{escape(str(data_date) or "—")}</span>
        </span>
        {date_hidden}
        {detail_fields}
        <button type="submit" class="btn btn-compact">应用筛选</button>
    </form>"""


def _render_selection_notice(notice: dict | None) -> str:
    if not notice or not notice.get("message"):
        return ""
    return (
        f'<p class="selection-notice muted tiny">{escape(str(notice["message"]))}</p>'
    )


def _render_header_actions(
    trust_product_id: int | None,
    json_qs: str,
    identity_id: int | None = None,
) -> str:
    back_href = "/overdue"
    if trust_product_id is not None:
        back_href = f"/overdue?trust_product_id={trust_product_id}"
    extra_links = f'<a class="header-tool-link" href="/overdue/workbench/detail{json_qs}">JSON</a>'
    if identity_id:
        extra_links += (
            f'<a class="header-tool-link" href="/asset-workbench/{identity_id}">'
            f"Asset Workbench</a>"
        )
    return f"""<div class="header-actions">
        <div class="header-tool-links">{extra_links}</div>
        <div class="header-action-btns">
            <a class="btn btn-ghost" href="{back_href}">返回列表</a>
            <button type="button" class="btn btn-ghost" onclick="location.reload()">刷新数据</button>
        </div>
    </div>"""


def _overdue_label(summary: dict) -> str:
    bucket = summary.get("delinquency_bucket")
    od = summary.get("overdue_days")
    if bucket == "ES":
        return "提前结清"
    if od is not None:
        return f"逾期 {od} 天"
    return "—"


def _fmt_source_asset_code(value) -> str:
    if value is None or str(value).strip() == "":
        return "—"
    return str(value)


def _fmt_date_only(value) -> str:
    if value is None:
        return "—"
    text = str(value).strip()
    if not text or text == "—":
        return "—"
    return text[:10]


def _summary_tip_body(*lines: str) -> str:
    return "<br>".join(escape(l) for l in lines if l is not None and str(l).strip())


def _summary_chip(inner_html: str, tip_lines: list[str], *, extra_class: str = "") -> str:
    tips = [str(l) for l in tip_lines if l is not None and str(l).strip()]
    body = _summary_tip_body(*tips) if tips else "—"
    cls = "summary-chip has-tip"
    if extra_class:
        cls += f" {extra_class}"
    return (
        f'<span class="{cls}">'
        f'{inner_html}<span class="tip-panel" role="tooltip">{body}</span></span>'
    )


def _summary_sep() -> str:
    return '<span class="summary-sep" aria-hidden="true">·</span>'


def _sum_withholding_total(issuance_records: list) -> float | None:
    total = 0.0
    found = False
    for rec in issuance_records:
        amt = rec.get("total_rent_withholding_amount")
        if amt is not None:
            total += float(amt)
            found = True
    return total if found else None


def _sum_contract_total(issuance_records: list) -> float | None:
    total = 0.0
    found = False
    for rec in issuance_records:
        amt = rec.get("receivable_contract_amount")
        if amt is not None:
            total += float(amt)
            found = True
    return total if found else None


def _resolve_withholding_amount(issuance_records: list) -> tuple[float | None, str]:
    """Return (amount, source) where source is withholding | contract | none."""
    withholding = _sum_withholding_total(issuance_records)
    if withholding is not None:
        return withholding, "withholding"
    contract = _sum_contract_total(issuance_records)
    if contract is not None:
        return contract, "contract"
    return None, "none"


def _render_editable_mark_chip(
    display_text: str,
    field: str,
    pid,
    ac_raw,
    data_date,
    options_html: str,
    tip_lines: list[str],
) -> str:
    inner = f"""<span class="mark-inline-group">
        <span class="mark-display">{escape(display_text)}</span>
        <select class="mark-select summary-select mark-edit-hidden" data-field="{field}"
                data-product="{pid}" data-asset-code="{escape(str(ac_raw))}" data-date="{escape(str(data_date))}">
            {options_html}
        </select>
    </span>"""
    return _summary_chip(inner, tip_lines, extra_class="summary-chip-editable")


def _render_summary_card(dto: dict, asset: dict) -> str:
    """Summary Card — 4 scan lines with hover detail chips."""
    summary = asset.get("summary") or {}
    checks = asset.get("checks")
    trust_mark = asset.get("trust_mark") or {}
    followup_case = asset.get("followup_case") or {}
    timeline = asset.get("timeline") or []
    issuance_records = asset.get("issuance_records") or []
    repayment = asset.get("repayment") or {}
    ops = asset.get("ops") or {}
    monitor = asset.get("monitor") or {}
    splits = monitor.get("splits") or []

    asset_code_raw = asset.get("asset_code") or dto.get("asset_code") or "—"
    asset_code = escape(str(asset_code_raw))
    custodies = asset.get("custody_asset_codes") or dto.get("custody_asset_codes") or []
    custody_str = "、".join(str(c) for c in custodies) if custodies else "—"

    bucket = summary.get("delinquency_bucket")
    remaining = summary.get("remaining_amount")
    repaid = summary.get("repaid_amount")
    initial = summary.get("initial_transfer_amount")
    overdue_days = summary.get("overdue_days")

    if bucket == "ES":
        overdue_str = "提前结清"
        od_cls = ""
    elif overdue_days is not None:
        overdue_str = f"{overdue_days}天"
        od_cls = " summary-warn"
    else:
        overdue_str = "—"
        od_cls = ""

    pid = dto.get("trust_product_id")
    ac_raw = asset_code_raw if asset_code_raw != "—" else ""
    data_date = dto.get("data_date") or ""
    data_date_str = escape(str(data_date or "—"))
    current_marker = trust_mark.get("trust_marker") or "未标记"
    current_internal = trust_mark.get("internal_status") or "待跟进"
    marker_note = trust_mark.get("marker_note")
    followup_count = len([e for e in timeline if e.get("event_type") == "followup"])
    product_name = summary.get("trust_product_name") or "—"
    risk_score = summary.get("risk_score")

    marker_opts = "".join(
        f'<option value="{escape(m)}"{" selected" if m == current_marker else ""}>{escape(m)}</option>'
        for m in TRUST_MARKER_OPTIONS
    )
    status_opts = "".join(
        f'<option value="{escape(s)}"{" selected" if s == current_internal else ""}>{escape(s)}</option>'
        for s in INTERNAL_STATUS_OPTIONS
    )

    asset_tip = [
        f"{CUSTODY_ASSET_CODE_LABEL}：{custody_str}",
        f"信托产品：{product_name}",
    ]

    m_tip = [f"逾期阶段：{bucket or '—'}"]
    if risk_score is not None:
        m_tip.append(f"风险分：{risk_score}")

    od_tip = []
    if bucket == "ES":
        od_tip.append("资产已提前结清")
    elif overdue_days is not None:
        od_tip.append(f"汇总逾期：{overdue_days} 天")
        for s in splits:
            sod = s.get("overdue_days")
            if sod is not None:
                od_tip.append(
                    f"{s.get('custody_asset_code') or '—'}：{sod} 天"
                )

    marker_tip = ["双击可修改信托标记"]
    if marker_note:
        marker_tip.append(f"备注：{marker_note}")

    withholding, wh_source = _resolve_withholding_amount(issuance_records)

    wh_tip: list[str] = []
    if wh_source == "withholding":
        wh_tip.append(f"发行 {len(issuance_records)} 条 · 总代扣 {fmt_money(withholding)}")
        for rec in issuance_records[:3]:
            per = rec.get("calculated_rent_withholding_per_period")
            periods = rec.get("withholding_periods_at_pooling")
            parts: list[str] = []
            if periods is not None:
                parts.append(f"代扣 {periods} 期")
            if per is not None:
                parts.append(f"每期 {fmt_money(per)}")
            if parts:
                wh_tip.append(f"{rec.get('custody_asset_code') or '—'}：{' · '.join(parts)}")
    elif wh_source == "contract":
        wh_tip.append(f"发行总代扣缺失，暂用合同金额 {fmt_money(withholding)}")
        for rec in issuance_records[:3]:
            contract_amt = rec.get("receivable_contract_amount")
            if contract_amt is not None:
                wh_tip.append(
                    f"{rec.get('custody_asset_code') or '—'}：合同 {fmt_money(contract_amt)}"
                )

    repayment_items = repayment.get("items") or []
    recent_repay = repayment.get("recent_repayment_date")
    recent_repay_str = _fmt_date_only(recent_repay)
    repaid_tip: list[str] = [f"还款明细 {len(repayment_items)} 条"]
    for item in repayment_items[:3]:
        repaid_tip.append(
            f"{_fmt_date_only(item.get('repayment_date'))} · {fmt_money(item.get('actual_repayment_amount'))}"
        )

    remain_tip = [
        f"{fmt_money(initial)} − {fmt_money(repaid)} = {fmt_money(remaining)}",
        "（监控初始 − 已还 = 剩余）",
    ]

    if checks:
        bal = checks["balance_equation"]
        cross = checks["cross_sheet_repayment"]
        bal_passed = bal["passed"]
        cross_passed = cross["passed"]
        bal_label = "余额✓" if bal_passed else "余额⚠"
        cross_label = "还款✓" if cross_passed else "还款⚠"
        bal_cls = "check-ok" if bal_passed else "check-bad"
        cross_cls = "check-ok" if cross_passed else "check-bad"
        bal_tip = [
            f"剩余 {fmt_money(bal['left_amount'])} vs 初始−已还 {fmt_money(bal['right_amount'])}",
            f"差额 {fmt_money(bal['diff_amount'])}",
            f"核对基准：{RECONCILIATION_BASIS_LABEL}",
        ]
        cross_tip = [
            f"监控已还 {fmt_money(cross['left_amount'])} vs 还款明细 {fmt_money(cross['right_amount'])}",
            f"差额 {fmt_money(cross['diff_amount'])}",
            f"核对基准：{RECONCILIATION_BASIS_LABEL}",
        ]
    else:
        bal_label = cross_label = "—"
        bal_cls = cross_cls = ""
        bal_tip = cross_tip = []

    last_at = summary.get("last_follow_up_at") or followup_case.get("last_follow_up_at")
    last_owner = summary.get("last_follow_up_owner") or followup_case.get("owner_name")
    status_tip = ["双击可修改跟进状态"]
    if last_at or last_owner:
        status_tip.append(
            f"最近跟进：{_fmt_date_only(last_at)} · {last_owner or '—'}"
        )
    if followup_case.get("overdue_reason"):
        status_tip.append(f"原因：{followup_case.get('overdue_reason')}")

    count_tip = [f"跟进记录 {followup_count} 条"]
    for ev in timeline:
        if ev.get("event_type") != "followup":
            continue
        count_tip.append(
            f"{_fmt_date_only(ev.get('occurred_at'))} · {ev.get('title') or '—'}"
        )
        if len(count_tip) >= 4:
            break

    actions = ops.get("recommended_actions") or []
    first_action = actions[0].get("label") if actions else None
    sla = ops.get("sla") or {}

    line4_tip: list[str] = ["── 监控 ──", f"数据日期：{data_date or '—'}"]
    for s in splits:
        sod = s.get("overdue_days")
        line4_tip.append(
            f"{s.get('custody_asset_code') or '—'} · "
            f"逾期 {sod if sod is not None else '—'}天 · "
            f"{s.get('delinquency_bucket') or '—'}"
        )
    if not splits:
        line4_tip.append("暂无监控分笔")

    line4_tip.append("── 还款 ──")
    if repayment_items:
        for item in repayment_items[:3]:
            line4_tip.append(
                f"{_fmt_date_only(item.get('repayment_date'))} · {fmt_money(item.get('actual_repayment_amount'))}"
            )
    else:
        line4_tip.append("暂无还款明细")

    line4_tip.append("── Ops ──")
    ops_detail_count = 0
    if ops.get("bucket") or ops.get("risk_level"):
        line4_tip.append(
            f"逾期阶段 {ops.get('bucket') or '—'} · 风险 {ops.get('risk_level') or '—'}"
        )
        ops_detail_count += 1
    if sla.get("due_date"):
        sla_state = "已超期" if sla.get("is_breached") else "正常"
        line4_tip.append(f"SLA 截止 {_fmt_date_only(sla.get('due_date'))}（{sla_state}）")
        ops_detail_count += 1
    for action in actions[:5]:
        line4_tip.append(str(action.get("label") or action.get("action_type") or "—"))
        ops_detail_count += 1
    if ops_detail_count == 0:
        line4_tip.append("暂无 Ops 建议")

    anomaly_cls = " card-summary-anomaly" if summary.get("has_check_anomaly") else ""
    ops_short = escape(str(first_action)) if first_action else "暂无建议"
    sla_badge = ""
    if sla.get("is_breached"):
        sla_badge = ' <span class="badge fail-badge tiny-badge">SLA超期</span>'
    elif sla.get("due_date"):
        sla_badge = ' <span class="badge ok-badge tiny-badge">SLA正常</span>'

    od_inner = f'<span class="summary-warn">{escape(overdue_str)}</span>' if od_cls else escape(overdue_str)

    line1 = (
        f"{_summary_chip(asset_code, asset_tip)}"
        f"{_summary_sep()}"
        f"{_summary_chip(fmt_delinquency_badge(bucket), m_tip)}"
        f"{_summary_sep()}"
        f"{_summary_chip(od_inner, od_tip or ['—'])}"
        f"{_summary_sep()}"
        f"{_render_editable_mark_chip(current_marker, 'trust_marker', pid, ac_raw, data_date, marker_opts, marker_tip)}"
    )

    wh_display = fmt_money(withholding) if withholding is not None else "—"
    remain_inner = f'剩余 <span class="summary-em">{fmt_money(remaining)}</span>'
    line2 = (
        f"{_summary_chip(f'总代扣 {wh_display}', wh_tip or ['—'])}"
        f"{_summary_sep()}"
        f"{_summary_chip(f'已还 {fmt_money(repaid)}', repaid_tip)}"
        f"{_summary_sep()}"
        f'{_summary_chip(remain_inner, remain_tip, extra_class="summary-chip-em")}'
    )

    if checks:
        bal_inner = f'<span class="{bal_cls}">{escape(bal_label)}</span>'
        cross_inner = f'<span class="{cross_cls}">{escape(cross_label)}</span>'
        line3 = (
            f"{_render_editable_mark_chip(current_internal, 'internal_status', pid, ac_raw, data_date, status_opts, status_tip)}"
            f"{_summary_sep()}"
            f"{_summary_chip(f'{followup_count}条', count_tip)}"
            f"{_summary_sep()}"
            f"{_summary_chip(bal_inner, bal_tip)}"
            f"{_summary_sep()}"
            f"{_summary_chip(cross_inner, cross_tip)}"
        )
    else:
        line3 = (
            f"{_render_editable_mark_chip(current_internal, 'internal_status', pid, ac_raw, data_date, status_opts, status_tip)}"
            f"{_summary_sep()}"
            f"{_summary_chip(f'{followup_count}条', count_tip)}"
            f"{_summary_sep()}余额 —{_summary_sep()}还款 —"
        )

    line4_inner = (
        f"监控 {data_date_str}{_summary_sep()}"
        f"末次还款 {recent_repay_str}{_summary_sep()}"
        f"建议：{ops_short}{sla_badge}"
    )
    line4 = _summary_chip(line4_inner, line4_tip, extra_class="summary-chip-line")

    return f"""<div class="card-summary card-summary-v2{anomaly_cls}">
        <div class="summary-line">{line1}</div>
        <div class="summary-line summary-line-money">{line2}</div>
        <div class="summary-line summary-line-checks">{line3}</div>
        <div class="summary-line summary-line-monitor">{line4}</div>
    </div>"""


def _render_hero_asset_card(dto: dict, asset: dict) -> str:
    """Legacy wrapper: Summary + Check in sequence (not used by detail-grid path)."""
    return _render_summary_card(dto, asset) + "\n" + _render_check_card(asset.get("checks"))


def _render_check_card(checks: dict | None) -> str:
    """Compact Check Card — shows balance equation and cross-sheet repayment results."""
    if not checks:
        return '<div class="card-check"><span class="muted tiny">金额核对：—</span></div>'
    bal = checks["balance_equation"]
    cross = checks["cross_sheet_repayment"]
    has_anomaly = not (bal["passed"] and cross["passed"])
    alert_cls = " card-check-alert" if has_anomaly else ""
    bal_tip = f"剩余 {fmt_money(bal['left_amount'])} vs 初始−已还 {fmt_money(bal['right_amount'])}"
    cross_tip = (
        f"监控已还 {fmt_money(cross['left_amount'])} vs 还款明细 "
        f"{fmt_money(cross['right_amount'])}"
    )

    def check_row(label: str, passed: bool, tip: str, diff) -> str:
        res_cls = "check-pass" if passed else "check-fail"
        return (
            f'<div class="check-row" title="{escape(tip)}">'
            f'<span class="check-label">{escape(label)}</span>'
            f'<span class="check-result {res_cls}">{fmt_check_result(passed)}</span>'
            f'<span class="check-diff">差额 {fmt_money(diff)}</span>'
            f"</div>"
        )

    return f"""<div class="card-check{alert_cls}">
        <div class="card-check-title">资产金额核对</div>
        {check_row("余额等式", bal["passed"], bal_tip, bal["diff_amount"])}
        {check_row("跨表已还", cross["passed"], cross_tip, cross["diff_amount"])}
        <p class="check-basis muted tiny">核对基准：{escape(RECONCILIATION_BASIS_LABEL)}</p>
    </div>"""


def _render_sidebar(
    dto: dict,
    trust_product_id: int | None,
    current_asset_code: str | None,
    workbench_qs,
) -> str:
    asset_list_html = _render_asset_list(
        dto.get("asset_list") or {},
        trust_product_id,
        current_asset_code,
        dto.get("filters") or {},
    )
    bucket = (dto.get("filters") or {}).get("delinquency_bucket") or DEFAULT_DELINQUENCY_BUCKET
    bucket_label = dict(_BUCKET_FILTER_OPTIONS).get(bucket, bucket)
    sidebar_filter = _render_sidebar_filter(dto)
    return f"""
        <div class="sidebar-section">
            <div class="panel-hd">资产清单 <span class="muted tiny">· {escape(str(bucket_label))}</span></div>
            {sidebar_filter}
            <div class="queue-body compact-queue" id="asset-queue">{asset_list_html}</div>
            <script>
            (function(){{
                var pos = sessionStorage.getItem('_queueScroll');
                if (pos !== null) {{
                    document.getElementById('asset-queue').scrollTop = parseInt(pos, 10);
                    sessionStorage.removeItem('_queueScroll');
                }}
            }})();
            </script>
        </div>
    """


def _render_asset_list(
    asset_list: dict,
    trust_product_id: int | None,
    current_asset_code: str | None,
    filters: dict,
) -> str:
    items = asset_list.get("items") or []
    if not items:
        return '<div class="empty">暂无符合条件的资产</div>'
    bucket = filters.get("delinquency_bucket") or DEFAULT_DELINQUENCY_BUCKET
    data_date = asset_list.get("data_date")
    list_filter = (
        filters.get("list_product_id")
        if filters.get("list_product_scope_explicit")
        else trust_product_id
    )
    html = ""
    for it in items:
        ac = it.get("asset_code") or ""
        pid = it.get("trust_product_id") or trust_product_id
        active = (
            "active"
            if _is_selected_asset_item(
                pid,
                ac,
                selected_product_id=trust_product_id,
                selected_asset_code=current_asset_code,
            )
            else ""
        )
        href = _asset_list_item_href(
            it,
            filters=filters,
            bucket=bucket,
            data_date=data_date,
            list_filter=list_filter,
        )
        bucket_html = fmt_delinquency_badge(it.get("delinquency_bucket"))
        custodies = it.get("custody_asset_codes") or []
        if len(custodies) <= 1:
            custody_hint = escape(str(custodies[0] if custodies else "—"))
        else:
            custody_hint = f"托管 {len(custodies)} 个"
        product_name = escape(str(it.get("trust_product_name") or ""))
        product_line = (
            f'<span>{product_name}</span>' if list_filter is None and product_name else ""
        )
        html += f"""
        <a class="queue-item compact {active}" id="asset-{escape(str(pid))}-{escape(str(ac))}" href="{href}">
            <div class="queue-line1">{escape(str(ac))}</div>
            <div class="queue-line2">
                {product_line}
                <span>逾期 {it.get('overdue_days', '—')} 天</span>
                <span>{bucket_html}</span>
                <span>跟进 {it.get('followup_count', 0)} 次</span>
                <span>{escape(str(it.get('internal_status') or '—'))}</span>
            </div>
            <div class="queue-line3 muted tiny">{CUSTODY_ASSET_CODE_LABEL} {custody_hint}</div>
        </a>
        """
    return html


def _last_followup_html(summary: dict) -> str:
    at = summary.get("last_follow_up_at")
    owner = summary.get("last_follow_up_owner")
    if not at and not owner:
        return '<div class="asset-card-followup muted tiny">最近跟进：—</div>'
    at_esc = escape(str(at or "—"))
    owner_esc = escape(str(owner or "—"))
    return f'<div class="asset-card-followup muted tiny">最近跟进：{at_esc} · {owner_esc}</div>'


def _render_asset_info_card(dto: dict, workbench_qs) -> str:
    asset = dto.get("asset")
    if not asset:
        if dto.get("asset_code"):
            return '<div class="panel-hd">资产信息</div><div class="empty">该资产暂无监控快照</div>'
        return '<div class="panel-hd">资产信息</div><div class="empty">请从资产清单选择资产。</div>'

    summary = asset.get("summary") or {}
    asset_code = escape(str(asset.get("asset_code") or "—"))
    custodies = asset.get("custody_asset_codes") or []
    custody_html = "<br>".join(escape(str(c)) for c in custodies) if custodies else "—"
    data_date = escape(str(dto.get("data_date") or "—"))
    primary = escape(str(asset.get("primary_custody_asset_code") or "—"))
    followup_line = _last_followup_html(summary)
    multi_hint = ""
    if len(custodies) > 1 and asset.get("primary_custody_asset_code"):
        multi_hint = (
            f'<p class="muted tiny">默认托管号（跟进/标记）：{primary}</p>'
        )

    splits = asset.get("monitor", {}).get("splits") or []
    selected_id = asset.get("selected_trust_asset_id")
    split_list = ""
    if len(splits) > 1:
        split_list = f'<div class="split-list">{_render_split_list(splits, selected_id, workbench_qs)}</div>'

    return f"""
    <div class="panel-hd">资产信息</div>
    <div class="asset-card">
        <p><span class="lbl">{ASSET_CODE_LABEL}</span><strong>{asset_code}</strong></p>
        <p><span class="lbl">{CUSTODY_ASSET_CODE_LABEL}</span>{custody_html}</p>
        <p><span class="lbl">监控快照</span>{data_date}</p>
        {followup_line}
        {multi_hint}
    </div>
    {split_list}
    """


def _render_split_list(queue: list, selected_id: int | None, workbench_qs) -> str:
    items = ""
    for item in queue:
        active = "active" if item["trust_asset_id"] == selected_id else ""
        recon_flag = "" if item["checks"]["cross_sheet_repayment"]["passed"] else " ⚠"
        source = escape(_fmt_source_asset_code(item.get("source_asset_code")))
        custody = escape(str(item.get("custody_asset_code") or "—"))
        od_label = (
            f"提前结清 {item.get('last_payment_date') or '—'}"
            if item.get("delinquency_bucket") == "ES"
            else f"逾期 {item['overdue_days']}天"
        )
        badge = (
            fmt_risk_badge(item.get("risk_level"))
            if item.get("risk_level")
            else fmt_delinquency_badge(item.get("delinquency_bucket"))
        )
        score = item["risk_score"] if item.get("risk_score") is not None else "—"
        follow_label = "已跟进" if item.get("has_follow_up") else "未跟进"
        items += f"""
        <a class="queue-item compact split-item {active}"
           href="/overdue/workbench{workbench_qs(item['trust_asset_id'])}">
            <div class="queue-line1">
                <span class="queue-code" title="{SOURCE_ASSET_CODE_LABEL}">{source}{recon_flag}</span>
                {badge}
            </div>
            <div class="queue-line2">
                <span>{od_label}</span>
                <span class="muted tiny">{CUSTODY_ASSET_CODE_LABEL} {custody}</span>
                <span>评分 {score}</span>
                <span>{follow_label}</span>
            </div>
        </a>
        """
    return items


def _render_panels(dto: dict, asset: dict, workbench_qs) -> str:
    """Right-column detail-grid: summary | issuance, repay | timeline, ops."""
    if not asset or not (asset.get("selected_split") or asset.get("monitor", {}).get("splits")):
        if dto.get("asset_code"):
            return '<div class="empty">该资产主编号暂无监控分笔数据</div>'
        return '<div class="empty">请从资产清单选择资产。</div>'
    return f"""<div class="detail-grid">
        <div class="grid-summary">{_render_summary_card(dto, asset)}</div>
        <div class="grid-issuance">{_panel_issuance(asset.get("issuance_records") or [])}</div>
        <div class="grid-repay">{_panel_repayment(asset.get("repayment") or {})}</div>
        <div class="grid-timeline">{_panel_timeline(
            asset.get("timeline") or [],
            asset.get("followup_case"),
            asset.get("summary") or {},
            asset.get("trust_mark") or {},
            asset.get("followup_entries") or [],
        )}</div>
        <div class="grid-ops">{_panel_ops(asset.get("ops"), asset.get("summary") or {})}</div>
    </div>"""


def _panel_issuance(records: list) -> str:
    count = len(records)
    if not records:
        inner = '<p class="empty">暂无发行明细 · <a href="/issuance/records">发行记录</a></p>'
    else:
        # Group by custody_asset_code (preserving insertion order = custody_code order)
        groups: dict[str, list] = {}
        for rec in records:
            key = rec.get("custody_asset_code") or "—"
            groups.setdefault(key, []).append(rec)

        group_blocks = ""
        for custody_code, recs in groups.items():
            rec_cards = ""
            for rec in recs:
                issue = escape(str(rec.get("issue_date") or "—"))
                city = escape(str(rec.get("city") or ""))
                addr = escape(str(rec.get("property_address") or ""))
                debtor = escape(str(rec.get("debtor_name") or "—"))
                contract = escape(str(rec.get("contract_name") or "—"))
                signing = rec.get("signing_date")
                rental_end = rec.get("rental_contract_end_date")

                location_parts = []
                if city:
                    location_parts.append(f"城市：{city}")
                if addr:
                    location_parts.append(f"地址：{addr}")
                location_line = " · ".join(location_parts) if location_parts else "—"

                date_parts = []
                if signing:
                    date_parts.append(f"签约日 {escape(str(signing))}")
                if rental_end:
                    date_parts.append(f"租约到期 {escape(str(rental_end))}")
                date_line = " · ".join(date_parts)

                price_parts = []
                contract_amt = rec.get("receivable_contract_amount")
                transfer_amt = rec.get("receivable_transfer_amount")
                rental_price = rec.get("rental_price")
                per_period = rec.get("calculated_rent_withholding_per_period")
                ratio = rec.get("rent_withholding_ratio")
                discount = rec.get("asset_transfer_discount_rate")
                migration = rec.get("migration_type")
                from_product = rec.get("from_trust_product_name")
                if contract_amt is not None:
                    price_parts.append(f"合同金额 {fmt_money(contract_amt)}")
                if transfer_amt is not None:
                    price_parts.append(f"转让价款 {fmt_money(transfer_amt)}")
                if rental_price is not None:
                    price_parts.append(f"出房价格 {fmt_money(rental_price)}")
                if per_period is not None:
                    price_parts.append(f"每期代扣 {fmt_money(per_period)}")
                if ratio is not None:
                    price_parts.append(f"代扣比 {format_rate(ratio)}")
                if discount is not None:
                    price_parts.append(f"折价率 {format_rate(discount)}")

                meta_parts = []
                if migration:
                    meta_parts.append(f"迁移类型：{escape(migration_type_label(str(migration)))}")
                if from_product:
                    meta_parts.append(f"转出信托：{escape(str(from_product))}")
                meta_line = " · ".join(meta_parts)
                price_line = " · ".join(price_parts) if price_parts else "—"

                source = escape(str(rec.get("source_file_name") or ""))

                rec_cards += f"""<div class="issuance-record">
                    <p class="issuance-issue-date">发行日 {issue}</p>
                    {f'<p class="issuance-line">{meta_line}</p>' if meta_line else ''}
                    <p class="issuance-line">{location_line}</p>
                    <p class="issuance-line">债务人：{debtor} · 合同：{contract}</p>
                    <p class="issuance-line">{price_line}</p>
                    {f'<p class="issuance-line">{date_line}</p>' if date_line else ''}
                    {f'<p class="muted tiny">来源 {source}</p>' if source else ''}
                </div>"""

            multi = len(recs) > 1
            group_label = f'<span class="issuance-custody">托管房源号 {escape(custody_code)}</span>'
            if multi:
                group_blocks += f"""<details class="issuance-group">
                    <summary class="issuance-group-hd">{group_label} · {len(recs)} 条发行记录</summary>
                    {rec_cards}
                </details>"""
            else:
                group_blocks += f"""<div class="issuance-group">
                    <p class="issuance-group-hd">{group_label}</p>
                    {rec_cards}
                </div>"""

        inner = group_blocks

    return f"""<details class="info-card info-card-folded">
        <summary class="info-card-title">发行信息（{count} 条）</summary>
        <div class="info-card-body">{inner}</div>
    </details>"""


def _repayment_table_row(it: dict) -> str:
    return f"""<tr>
        <td>{escape(str(it.get('custody_asset_code') or '—'))}</td>
        <td>{escape(_fmt_date_only(it.get('repayment_date')))}</td>
        <td class="num">{fmt_money(it.get('actual_repayment_amount'))}</td>
    </tr>"""


def _build_panel_preview_table(
    *,
    colgroup_html: str,
    thead_html: str,
    items: list,
    row_fn,
    colspan: int,
    expand_summary: str,
    empty_message: str | None = None,
) -> str:
    preview_items = items[:_PANEL_PREVIEW_ROWS]
    rows: list[str] = []
    for i in range(_PANEL_PREVIEW_ROWS):
        if i < len(preview_items):
            rows.append(row_fn(preview_items[i]))
        elif i == 0 and not preview_items and empty_message:
            rows.append(f'<tr><td colspan="{colspan}" class="empty">{escape(empty_message)}</td></tr>')
        else:
            rows.append(f'<tr class="row-pad"><td colspan="{colspan}">&nbsp;</td></tr>')

    expand_block = ""
    if len(items) > _PANEL_PREVIEW_ROWS:
        more_rows = "".join(row_fn(it) for it in items[_PANEL_PREVIEW_ROWS:50])
        expand_block = f"""<details class="panel-expand">
            <summary class="panel-expand-summary muted tiny">{escape(expand_summary)}</summary>
            <div class="table-wrap panel-expand-table">
                <table class="panel-fixed-rows">
                    {colgroup_html}
                    <tbody>{more_rows}</tbody>
                </table>
            </div>
        </details>"""

    return f"""<div class="table-wrap">
        <table class="panel-fixed-rows">
            {colgroup_html}
            {thead_html}
            <tbody class="panel-preview">{"".join(rows)}</tbody>
        </table>
    </div>
    {expand_block}"""


def _followup_status_label(status: str | None) -> str:
    if not status:
        return "—"
    return FOLLOWUP_STATUS_LABELS.get(status, status)


def _followup_panel_summary(
    events: list,
    followup_case: dict | None,
    summary: dict,
    trust_mark: dict,
    followup_entries: list | None = None,
) -> str:
    entries = followup_entries or []
    if entries:
        status_label = _followup_status_label(entries[0].get("status_snapshot"))
    else:
        case_status = (followup_case or {}).get("status")
        if case_status:
            status_label = _followup_status_label(case_status)
        else:
            status_label = (trust_mark or {}).get("internal_status") or "—"
    last_at = _fmt_date_only(summary.get("last_follow_up_at"))
    followup_count = len([e for e in events if e.get("event_type") == "followup"])
    return (
        f"跟进记录状态 {escape(str(status_label))} · "
        f"最近跟进 {escape(last_at)} · "
        f"跟进记录 {followup_count} 条"
    )


def _panel_repayment(rep: dict) -> str:
    items = rep.get("items") or []
    colgroup = """<colgroup>
        <col class="col-repay-custody">
        <col class="col-repay-date">
        <col class="col-repay-amt">
    </colgroup>"""
    thead = f"""<thead><tr>
        <th>{CUSTODY_ASSET_CODE_LABEL}</th><th>还款日</th><th>实还</th>
    </tr></thead>"""
    table_html = _build_panel_preview_table(
        colgroup_html=colgroup,
        thead_html=thead,
        items=items,
        row_fn=_repayment_table_row,
        colspan=3,
        expand_summary=f"查看全部还款明细（{len(items)} 条）",
        empty_message="缺少还款明细，逾期天数可能无法重算",
    )
    recent = _fmt_date_only(rep.get("recent_repayment_date"))
    return f"""<div class="info-card panel-dual">
        <h3 class="info-card-title">还款情况</h3>
        <div class="info-card-body">
            <p class="panel-summary-line">累计实还 <strong>{fmt_money(rep.get('total_repaid'))}</strong>
            · 最近还款日 {escape(recent)}
            · 期次 {rep.get('period_count', 0)}</p>
            {table_html}
        </div>
    </div>"""


def _panel_monitor(mon: dict, summary: dict, data_date: str | None) -> str:
    asset_agg = mon.get("custody") or mon.get("asset") or {}
    splits = mon.get("splits") or []
    rows = ""
    for s in splits:
        sod = s.get("overdue_days")
        rows += f"""<tr>
            <td>{escape(str(s.get('custody_asset_code') or '—'))}</td>
            <td class="num">{fmt_money(s.get('initial_transfer_amount'))}</td>
            <td class="num">{fmt_money(s.get('repaid_amount'))}</td>
            <td class="num">{fmt_money(s.get('remaining_amount'))}</td>
            <td>{sod if sod is not None else '—'}</td>
            <td>{fmt_delinquency_badge(s.get('delinquency_bucket'))}</td>
        </tr>"""
    table = f"""<div class="table-wrap"><table>
        <thead><tr><th>{CUSTODY_ASSET_CODE_LABEL}</th><th>初始</th><th>已还</th><th>剩余</th><th>逾期天</th><th>M级</th></tr></thead>
        <tbody>{rows or '<tr><td colspan="6" class="empty">无</td></tr>'}</tbody></table></div>"""
    return f"""<div class="info-card info-card-primary">
        <h3 class="info-card-title">当前监控</h3>
        <div class="info-card-body">
            <p class="muted tiny">数据日期 {escape(str(data_date or '—'))}</p>
            {table}
        </div>
    </div>"""


def _panel_trust_mark(mark: dict, dto: dict, asset: dict) -> str:
    pid = dto.get("trust_product_id")
    ac_raw = asset.get("asset_code") or dto.get("asset_code") or ""
    data_date = dto.get("data_date")
    marker = mark.get("trust_marker") or "未标记"
    internal = mark.get("internal_status") or "待跟进"
    note = escape(str(mark.get("marker_note") or "—"))
    marker_opts = "".join(
        f'<option value="{escape(m)}"{" selected" if m == marker else ""}>{escape(m)}</option>'
        for m in TRUST_MARKER_OPTIONS
    )
    status_opts = "".join(
        f'<option value="{escape(s)}"{" selected" if s == internal else ""}>{escape(s)}</option>'
        for s in INTERNAL_STATUS_OPTIONS
    )
    return f"""<div class="info-card" id="trust-mark-panel">
        <h3 class="info-card-title">信托标注</h3>
        <div class="info-card-body">
            <div class="mark-readonly">
                <p><span class="lbl">信托标记</span><strong>{escape(marker)}</strong></p>
                <p><span class="lbl">内部状态</span><strong>{escape(internal)}</strong></p>
                <p><span class="lbl">备注</span>{note}</p>
            </div>
            <p class="muted tiny">标注按 {ASSET_CODE_LABEL} {escape(str(ac_raw or '—'))} 保存</p>
            <div class="mark-edit muted tiny">修改标注</div>
            <p><span class="lbl">信托标记</span>
            <select class="mark-select" data-field="trust_marker"
                    data-product="{pid}" data-asset-code="{escape(str(ac_raw))}" data-date="{escape(str(data_date))}">
            {marker_opts}</select></p>
            <p><span class="lbl">内部状态</span>
            <select class="mark-select" data-field="internal_status"
                    data-product="{pid}" data-asset-code="{escape(str(ac_raw))}" data-date="{escape(str(data_date))}">
            {status_opts}</select></p>
            <p class="muted tiny">修改后自动保存</p>
        </div>
    </div>"""


def _panel_ops(ops: dict | None, summary: dict) -> str:
    alert_cls = " ops-panel-alert" if summary.get("has_check_anomaly") else ""
    if not ops:
        return f"""<div class="info-card ops-panel{alert_cls}"><h3 class="info-card-title">Ops 建议（只读）</h3>
            <p class="empty">暂无建议</p></div>"""
    actions = ops.get("recommended_actions") or []
    action_rows = "".join(
        f"<li>{escape(str(a.get('label') or a.get('action_type') or '—'))}</li>" for a in actions
    ) or "<li>—</li>"
    sla = ops.get("sla") or {}
    sla_txt = escape(str(sla.get("due_date") or "—"))
    breached = sla.get("is_breached")
    sla_badge = (
        '<span class="badge fail-badge">已超期</span>'
        if breached
        else '<span class="badge ok-badge">正常</span>'
    )
    return f"""<div class="info-card ops-panel{alert_cls}">
        <h3 class="info-card-title">Ops 建议（只读）</h3>
        <div class="info-card-body">
            <p><span class="lbl">逾期阶段</span>{fmt_delinquency_badge(ops.get('bucket'))}</p>
            <p><span class="lbl">风险</span>{fmt_risk_badge(ops.get('risk_level'))}</p>
            <p>SLA 截止 {sla_txt} {sla_badge}</p>
            <p class="lbl">建议动作</p><ul class="ops-list">{action_rows}</ul>
            <p class="muted tiny">建议不等于已执行，请在底栏录入跟进</p>
        </div>
    </div>"""


def _timeline_type_label(ev: dict) -> str:
    if ev.get("event_type") == "repayment":
        return "还款"
    if ev.get("event_type") == "followup":
        return "跟进"
    return "—"


def _truncate_summary(text: str | None, max_len: int = 24) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def _timeline_summary(ev: dict) -> str:
    legacy = ""
    if ev.get("legacy"):
        legacy = f' <span class="badge">{escape(ev.get("legacy_label") or "历史")}</span>'

    if ev.get("event_type") == "repayment":
        period = ev.get("period_no")
        custody = str(ev.get("custody_asset_code") or "")
        tail = custody[-4:] if len(custody) >= 4 else custody
        if period is not None and str(period) != "—":
            summary = f"期次 {period}"
            if tail:
                summary += f" · {tail}"
            return escape(summary)
        return escape(f"还款 · {_fmt_date_only(ev.get('occurred_at'))}")

    status = _followup_status_label(ev.get("status_snapshot"))
    snippet = _truncate_summary(ev.get("overdue_reason"))
    if not snippet:
        snippet = _truncate_summary(ev.get("follow_up_plan"))
    if not snippet and ev.get("owner_name"):
        snippet = _truncate_summary(f"负责人 {ev.get('owner_name')}")
    if snippet:
        return f"{escape(status)} · {escape(snippet)}{legacy}"
    return f"{escape(status)}{legacy}"


def _timeline_detail_cell(ev: dict) -> str:
    if ev.get("event_type") == "repayment":
        return f'<span class="num">{fmt_money(ev.get("amount"))}</span>'

    entry_id = ev.get("entry_id")
    label = escape(str(ev.get("owner_name") or "查看"))
    if entry_id:
        pane_id = f"followup-pane-entry-{entry_id}"
        return (
            f'<button type="button" class="timeline-goto-entry timeline-detail-link" '
            f'data-entry-pane="{pane_id}">{label} ▾</button>'
        )
    return label


def _timeline_rows(ev: dict) -> str:
    return f"""<tr class="timeline-main-row">
        <td>{escape(_fmt_date_only(ev.get('occurred_at')))}</td>
        <td>{escape(_timeline_type_label(ev))}</td>
        <td>{_timeline_summary(ev)}</td>
        <td>{_timeline_detail_cell(ev)}</td>
    </tr>"""


def _timeline_row(ev: dict) -> str:
    return _timeline_rows(ev)


def _panel_timeline(
    events: list,
    followup_case: dict | None = None,
    summary: dict | None = None,
    trust_mark: dict | None = None,
    followup_entries: list | None = None,
) -> str:
    summary = summary or {}
    trust_mark = trust_mark or {}
    colgroup = """<colgroup>
        <col class="col-tl-time">
        <col class="col-tl-type">
        <col class="col-tl-title">
        <col class="col-tl-detail">
    </colgroup>"""
    thead = """<thead><tr><th>时间</th><th>类型</th><th>摘要</th><th>详情</th></tr></thead>"""
    table_html = _build_panel_preview_table(
        colgroup_html=colgroup,
        thead_html=thead,
        items=events,
        row_fn=_timeline_row,
        colspan=4,
        expand_summary=f"查看全部 {len(events)} 条",
        empty_message="暂无事件",
    )
    summary_line = _followup_panel_summary(
        events, followup_case, summary, trust_mark, followup_entries
    )
    return f"""<div class="info-card panel-dual">
        <h3 class="info-card-title">跟进历史</h3>
        <div class="info-card-body">
            <p class="panel-summary-line">{summary_line}</p>
            {table_html}
        </div>
    </div>"""


def _followup_status_options(current: str | None) -> str:
    options = ""
    for value, label in FOLLOWUP_STATUS_LABELS.items():
        selected = " selected" if value == current else ""
        options += f'<option value="{value}"{selected}>{escape(label)}</option>'
    return options


def _followup_entry_tab_label(entry: dict) -> str:
    return f"{_fmt_date_only(entry.get('created_at'))} · {_followup_status_label(entry.get('status_snapshot'))}"


def _followup_entry_is_editable(entry: dict) -> bool:
    return entry.get("status_snapshot") == "in_progress"


def _render_followup_entry_readonly(entry: dict) -> str:
    eid = int(entry["id"])
    att_parts = []
    for att in entry.get("attachments") or []:
        aid = att.get("id")
        fname = escape(str(att.get("file_name") or ""))
        att_parts.append(f'<a href="/overdue/workbench/attachments/{aid}">{fname}</a>')
    att_html = " ".join(att_parts) if att_parts else "—"

    def ro_field(label: str, value) -> str:
        text = escape(str(value)) if value not in (None, "") else "—"
        return f'<p><span class="lbl">{escape(label)}</span>{text}</p>'

    cite_attrs = (
        f'data-status="{escape(str(entry.get("status_snapshot") or ""))}" '
        f'data-owner="{escape(str(entry.get("owner_name") or ""))}" '
        f'data-reason="{escape(str(entry.get("overdue_reason") or ""))}" '
        f'data-plan="{escape(str(entry.get("follow_up_plan") or ""))}" '
        f'data-feedback="{escape(str(entry.get("trust_feedback") or ""))}" '
        f'data-note="{escape(str(entry.get("note") or ""))}"'
    )
    return f"""<div class="followup-readonly">
        <p class="readonly-hint muted tiny">历史记录只读 · 如需补充请切换至「＋ 新建跟进」</p>
        {ro_field("跟进时间", _fmt_date_only(entry.get("created_at")))}
        {ro_field("跟进记录状态", _followup_status_label(entry.get("status_snapshot")))}
        {ro_field("负责人", entry.get("owner_name"))}
        {ro_field("逾期原因", entry.get("overdue_reason"))}
        {ro_field("跟进方案", entry.get("follow_up_plan"))}
        {ro_field("信托反馈", entry.get("trust_feedback"))}
        {ro_field("补充说明", entry.get("note"))}
        <p><span class="lbl">附件</span>{att_html}</p>
        <button type="button" class="btn btn-compact entry-cite-btn" {cite_attrs}>引用此条到新建</button>
    </div>"""


def _render_followup_entry_editable(
    entry: dict,
    product_hidden: str,
    asset_hidden: str,
    bucket_hidden: str,
    workbench_qs,
    data_date: str,
) -> str:
    eid = int(entry["id"])
    status = entry.get("status_snapshot") or "in_progress"
    owner_val = escape(entry.get("owner_name") or "")
    reason = escape(str(entry.get("overdue_reason") or ""))
    plan = escape(str(entry.get("follow_up_plan") or ""))
    feedback = escape(str(entry.get("trust_feedback") or ""))
    note = escape(str(entry.get("note") or ""))
    created = escape(_fmt_date_only(entry.get("created_at")))

    att_parts = []
    for att in entry.get("attachments") or []:
        aid = att.get("id")
        fname = escape(str(att.get("file_name") or ""))
        att_parts.append(f'<a href="/overdue/workbench/attachments/{aid}">{fname}</a>')
    att_html = " ".join(att_parts) if att_parts else "—"

    return f"""<div class="followup-editable">
        <p class="readonly-hint muted tiny">跟进中记录可修改 · 保存后更新本条（不新增记录）</p>
        <p class="muted tiny">跟进时间 {created} · 已有附件 {att_html}</p>
        <form class="followup-form followup-edit-form" method="post" enctype="multipart/form-data"
              action="/overdue/workbench/followups/entries/{eid}{workbench_qs()}">
            <input type="hidden" name="redirect_to_workbench" value="1">
            {product_hidden}
            {asset_hidden}
            {bucket_hidden}
            <input type="hidden" name="data_date" value="{data_date}">
            <div class="followup-form-grid">
                <label>跟进记录状态
                    <select name="status">{_followup_status_options(status)}</select>
                </label>
                <label>负责人 <input name="owner_name" value="{owner_val}"></label>
                <label>逾期原因<textarea name="overdue_reason" rows="2">{reason}</textarea></label>
                <label>跟进方案<textarea name="follow_up_plan" rows="2">{plan}</textarea></label>
                <label>信托反馈<textarea name="trust_feedback" rows="2">{feedback}</textarea></label>
                <label>补充说明<textarea name="note" rows="2">{note}</textarea></label>
                <label class="span-2">追加附件（图片/PDF 等，最多 10 个）
                    <input type="file" name="files" class="followup-edit-files" multiple>
                </label>
            </div>
            <div class="form-actions">
                <button type="submit" class="btn primary">保存修改</button>
            </div>
        </form>
    </div>"""


def _render_followup_entry_panel(
    entry: dict,
    product_hidden: str,
    asset_hidden: str,
    bucket_hidden: str,
    workbench_qs,
    data_date: str,
) -> str:
    if _followup_entry_is_editable(entry):
        return _render_followup_entry_editable(
            entry, product_hidden, asset_hidden, bucket_hidden, workbench_qs, data_date
        )
    return _render_followup_entry_readonly(entry)


def _panel_followup_write(
    product_hidden,
    asset_hidden,
    bucket_hidden,
    workbench_qs,
    dto,
    *,
    new_followup: bool = False,
) -> str:
    data_date = escape(str(dto.get("data_date") or ""))
    asset = dto.get("asset") or {}
    case = asset.get("followup_case") or {}
    current_status = case.get("status") or "in_progress"
    owner_val = escape(case.get("owner_name") or "")
    asset_code = escape(str(dto.get("asset_code") or asset.get("asset_code") or ""))
    expanded = "1" if new_followup else "0"
    followup_entries = asset.get("followup_entries") or []

    last_reason = ""
    last_plan = ""
    if followup_entries:
        last_reason = followup_entries[0].get("overdue_reason") or ""
        last_plan = followup_entries[0].get("follow_up_plan") or ""
    else:
        for ev in asset.get("timeline") or []:
            if ev.get("event_type") == "followup" and not ev.get("legacy"):
                last_reason = ev.get("overdue_reason") or ""
                last_plan = ev.get("follow_up_plan") or ""
                break

    entry_tabs = (
        '<button type="button" class="entry-tab active" data-pane="followup-pane-new">'
        "＋ 新建跟进</button>"
    )
    entry_panes = ""
    for entry in followup_entries:
        eid = int(entry["id"])
        pane_id = f"followup-pane-entry-{eid}"
        entry_tabs += (
            f'<button type="button" class="entry-tab" data-pane="{pane_id}">'
            f"{escape(_followup_entry_tab_label(entry))}</button>"
        )
        entry_panes += (
            f'<div class="followup-pane" id="{pane_id}">'
            f"{_render_followup_entry_panel(entry, product_hidden, asset_hidden, bucket_hidden, workbench_qs, data_date)}"
            f"</div>"
        )

    return f"""
    <div class="sticky-write-bar" id="followup-entry-form" data-expanded="{expanded}">
        <div class="sticky-write-collapsed">
            <button type="button" class="write-toggle" id="followup-expand" aria-expanded="{"true" if new_followup else "false"}">
                <span class="write-toggle-icon" aria-hidden="true">▶</span>
                <span class="sticky-write-title">记录跟进 · {ASSET_CODE_LABEL} {asset_code}</span>
            </button>
            <span class="sticky-write-actions">
                <button type="button" class="btn primary btn-compact" id="followup-expand-btn">展开录入</button>
                <button type="button" class="btn btn-compact write-collapse-btn" id="followup-collapse">收起</button>
            </span>
        </div>
        <div class="sticky-write-panel" id="followup-write-panel">
            <div class="sticky-write-inner">
                <p class="muted tiny">跟进时间于保存时自动生成 · 每次保存追加一条跟进记录（V2.2 entries）</p>
                <div class="entry-tabs" role="tablist">{entry_tabs}</div>
                <div class="followup-pane active" id="followup-pane-new">
                    <form class="followup-form" id="followup-form" method="post" enctype="multipart/form-data"
                          action="/overdue/workbench/followups/entries{workbench_qs()}">
                        <input type="hidden" name="redirect_to_workbench" value="1">
                        {product_hidden}
                        {asset_hidden}
                        {bucket_hidden}
                        <input type="hidden" name="data_date" value="{data_date}">
                        <div class="followup-form-grid">
                            <label>跟进记录状态
                                <select name="status">{_followup_status_options(current_status)}</select>
                            </label>
                            <label>负责人 <input name="owner_name" value="{owner_val}"></label>
                            <label>逾期原因<textarea name="overdue_reason" rows="2">{escape(str(last_reason))}</textarea></label>
                            <label>跟进方案<textarea name="follow_up_plan" rows="2">{escape(str(last_plan))}</textarea></label>
                            <label>信托反馈<textarea name="trust_feedback" rows="2"></textarea></label>
                            <label>补充说明<textarea name="note" rows="2"></textarea></label>
                            <label class="span-2">附件（图片/PDF 等，最多 10 个）
                                <input type="file" name="files" id="followup-files" multiple>
                            </label>
                            <div class="span-2 file-preview" id="file-preview"></div>
                        </div>
                        <div class="form-actions" id="followup-form-actions">
                            <button type="submit" class="btn primary">保存本次跟进</button>
                            <button type="button" class="btn" id="followup-clear">清空</button>
                        </div>
                    </form>
                </div>
                {entry_panes}
            </div>
        </div>
    </div>
    """


_WORKBENCH_SCRIPTS = """
<script>
document.addEventListener('DOMContentLoaded', function() {
    var writeBar = document.getElementById('followup-entry-form');
    var expandBtn = document.getElementById('followup-expand-btn');
    var expandToggle = document.getElementById('followup-expand');
    var collapseBtn = document.getElementById('followup-collapse');

    function setWriteExpanded(expanded) {
        if (!writeBar) return;
        writeBar.dataset.expanded = expanded ? '1' : '0';
        var toggles = [expandToggle, expandBtn, collapseBtn];
        toggles.forEach(function(el) {
            if (el) el.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        });
        var icon = writeBar.querySelector('.write-toggle-icon');
        if (icon) icon.textContent = expanded ? '▼' : '▶';
    }

    function expandWriteBar() {
        setWriteExpanded(true);
        if (writeBar) writeBar.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    if (expandBtn) expandBtn.addEventListener('click', expandWriteBar);
    if (expandToggle) {
        expandToggle.addEventListener('click', function() {
            if (writeBar && writeBar.dataset.expanded === '1') {
                setWriteExpanded(false);
            } else {
                expandWriteBar();
            }
        });
    }
    if (collapseBtn) collapseBtn.addEventListener('click', function() { setWriteExpanded(false); });

    if (document.body.dataset.scrollFollowup === '1') {
        expandWriteBar();
    }

    function switchFollowupPane(paneId) {
        document.querySelectorAll('.followup-pane').forEach(function(pane) {
            pane.classList.toggle('active', pane.id === paneId);
        });
        document.querySelectorAll('.entry-tab').forEach(function(tab) {
            tab.classList.toggle('active', tab.dataset.pane === paneId);
        });
        var formActions = document.getElementById('followup-form-actions');
        if (formActions) {
            formActions.style.display = paneId === 'followup-pane-new' ? '' : 'none';
        }
    }

    document.querySelectorAll('.entry-tab').forEach(function(tab) {
        tab.addEventListener('click', function() {
            switchFollowupPane(tab.dataset.pane);
        });
    });

    document.querySelectorAll('.entry-cite-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var form = document.getElementById('followup-form');
            if (!form) return;
            var status = form.querySelector('[name="status"]');
            var owner = form.querySelector('[name="owner_name"]');
            var reason = form.querySelector('[name="overdue_reason"]');
            var plan = form.querySelector('[name="follow_up_plan"]');
            var feedback = form.querySelector('[name="trust_feedback"]');
            var note = form.querySelector('[name="note"]');
            if (status && btn.dataset.status) status.value = btn.dataset.status;
            if (owner) owner.value = btn.dataset.owner || '';
            if (reason) reason.value = btn.dataset.reason || '';
            if (plan) plan.value = btn.dataset.plan || '';
            if (feedback) feedback.value = btn.dataset.feedback || '';
            if (note) note.value = btn.dataset.note || '';
            switchFollowupPane('followup-pane-new');
            if (writeBar) writeBar.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
    });

    switchFollowupPane('followup-pane-new');

    document.querySelectorAll('.timeline-goto-entry').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var paneId = btn.dataset.entryPane;
            if (paneId) switchFollowupPane(paneId);
            expandWriteBar();
            if (writeBar) writeBar.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
    });

    var activeQueueItem = document.querySelector('.compact-queue .queue-item.active');
    if (activeQueueItem) {
        // Only scroll on fresh load (sessionStorage already handled the click-navigation case)
        if (!sessionStorage.getItem('_queueScroll')) {
            activeQueueItem.scrollIntoView({ block: 'nearest', behavior: 'instant' });
        }
    }

    // Save scroll position before navigating to a new asset
    var assetQueue = document.getElementById('asset-queue');
    if (assetQueue) {
        assetQueue.addEventListener('mousedown', function(e) {
            if (e.target.closest('.queue-item')) {
                sessionStorage.setItem('_queueScroll', assetQueue.scrollTop);
            }
        });
    }

    var filterForm = document.querySelector('.workbench-filter');
    if (filterForm) {
        filterForm.addEventListener('submit', function() {
            var productSel = filterForm.querySelector('[name="list_product_id"]');
            if (productSel && !productSel.value) {
                var emptyList = document.createElement('input');
                emptyList.type = 'hidden';
                emptyList.name = 'list_product_id';
                emptyList.value = '';
                filterForm.appendChild(emptyList);
                ['asset_code', 'custody_asset_code', 'trust_asset_id'].forEach(function(name) {
                    var el = filterForm.querySelector('[name="' + name + '"]');
                    if (el) el.remove();
                });
            }
        });
    }

    document.querySelectorAll('.mark-select').forEach(function(sel) {
        sel.addEventListener('change', function() {
            var payload = {
                trust_product_id: parseInt(this.dataset.product, 10),
                asset_code: this.dataset.assetCode,
                data_date: this.dataset.date
            };
            payload[this.dataset.field] = this.value;
            fetch('/overdue/custody-marks', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).catch(function() { alert('标注保存失败'); });
        });
    });

    // Double-click to edit inline mark fields in Summary Card
    document.querySelectorAll('.mark-inline-group').forEach(function(group) {
        var display = group.querySelector('.mark-display');
        var sel = group.querySelector('.mark-select');
        if (!display || !sel) return;
        display.addEventListener('dblclick', function() {
            display.classList.add('mark-edit-hidden');
            sel.classList.remove('mark-edit-hidden');
            sel.focus();
        });
        sel.addEventListener('change', function() {
            display.textContent = this.options[this.selectedIndex].text;
            sel.classList.add('mark-edit-hidden');
            display.classList.remove('mark-edit-hidden');
        });
        sel.addEventListener('blur', function() {
            sel.classList.add('mark-edit-hidden');
            display.classList.remove('mark-edit-hidden');
        });
    });

    // Double-click to edit sidebar filter items (auto-submit on change)
    document.querySelectorAll('.sf-item').forEach(function(item) {
        var display = item.querySelector('.sf-display');
        var sel = item.querySelector('.sf-select');
        if (!display || !sel) return;
        display.addEventListener('dblclick', function() {
            sel.style.display = 'block';   // overlay on top; do NOT hide display
            sel.focus();
        });
        sel.addEventListener('change', function() {
            display.textContent = this.options[this.selectedIndex].text;
            sel.style.display = 'none';
            var form = document.getElementById('sf-form');
            if (form) form.submit();
        });
        sel.addEventListener('blur', function() {
            sel.style.display = 'none';
        });
    });
    var form = document.getElementById('followup-form');
    var fileInput = document.getElementById('followup-files');
    var preview = document.getElementById('file-preview');
    var clearBtn = document.getElementById('followup-clear');
    if (clearBtn && form) {
        clearBtn.addEventListener('click', function() {
            form.reset();
            if (preview) preview.innerHTML = '';
        });
    }
    if (fileInput && preview) {
        fileInput.addEventListener('change', function() {
            preview.innerHTML = '';
            Array.prototype.forEach.call(fileInput.files || [], function(file) {
                var chip = document.createElement('span');
                chip.className = 'file-chip';
                chip.textContent = file.name + ' (' + Math.round(file.size / 1024) + ' KB)';
                if (file.type && file.type.indexOf('image/') === 0) {
                    var img = document.createElement('img');
                    img.className = 'file-thumb';
                    img.alt = file.name;
                    var reader = new FileReader();
                    reader.onload = function(e) { img.src = e.target.result; };
                    reader.readAsDataURL(file);
                    var wrap = document.createElement('div');
                    wrap.className = 'file-chip-img';
                    wrap.appendChild(img);
                    wrap.appendChild(chip);
                    preview.appendChild(wrap);
                } else {
                    preview.appendChild(chip);
                }
            });
        });
    }
});
</script>
"""

_WORKBENCH_SPECIFIC_CSS = """
    .page-wrap { padding: 0; }
    .container { padding-bottom: 1.5rem; }
    .page-header { margin-bottom: 0.25rem; }
    .header-row { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; }
    .header-actions {
        display: flex; flex-direction: column; align-items: flex-end;
        gap: 0.35rem; flex-shrink: 0;
    }
    .header-tool-links {
        display: flex; gap: 0.65rem; font-size: 0.8rem;
    }
    .header-tool-link { color: #38bdf8; }
    .header-action-btns { display: flex; gap: 0.5rem; }
    .header-sub { color: #94a3b8; margin-top: 0.35rem; font-size: 0.9rem; }
    .header-data-date { font-size: 12px; color: #475569; font-weight: 400; white-space: nowrap; }
    /* Sidebar compact inline-edit filter row */
    .sidebar-filter {
        display: flex; flex-wrap: wrap; gap: 3px 4px; align-items: center;
        padding: 6px 0.85rem 8px; border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    .sf-item { display: inline-flex; align-items: center; position: relative; }
    .sf-display {
        font-size: 12px; color: #e2e8f0; cursor: default; user-select: none;
        border-bottom: 1px dashed rgba(255,255,255,0.18); padding: 1px 0;
    }
    .sf-display:hover { border-bottom-color: rgba(99,179,237,0.55); color: #93c5fd; }
    .sf-select {
        display: none;
        position: absolute; top: -2px; left: -4px; z-index: 200;
        font-size: 12px; color: #e2e8f0; height: 26px;
        min-width: 80px; max-width: 140px;
        background: rgba(15,23,42,0.97);
        border: 1px solid rgba(99,179,237,0.4); border-radius: 5px;
        padding: 0 4px; cursor: pointer; outline: none; box-sizing: border-box;
    }
    .sf-sep { color: #475569; padding: 0 2px; font-size: 11px; line-height: 1; }
    .ok-text { color: #4ade80; }
    .warn-text { color: #f87171; }
    .workbench {
        display: grid; grid-template-columns: 300px 1fr; gap: 1rem;
        margin-top: 1rem; align-items: start;
    }
    @media (max-width: 960px) { .workbench { grid-template-columns: 1fr; } }
    .panel {
        background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
        border-radius: 12px; overflow: hidden;
    }
    .panel-hd {
        padding: 0.65rem 0.85rem; border-bottom: 1px solid rgba(255,255,255,0.08);
        font-weight: 600; font-size: 0.85rem;
    }
    .detail-main {
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }
    /* ── Detail Grid: summary | issuance, repay | timeline, ops ─ */
    .detail-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        grid-template-areas:
            "summary   summary   issuance  issuance"
            "repay     repay     timeline  timeline"
            "ops       ops       ops       ops";
        gap: 16px;
        align-items: stretch;
    }
    .grid-summary  { grid-area: summary; }
    .grid-issuance { grid-area: issuance; }
    .grid-repay    { grid-area: repay; }
    .grid-timeline { grid-area: timeline; }
    .grid-ops      { grid-area: ops; }
    @media (max-width: 960px) {
        .detail-grid {
            grid-template-columns: 1fr;
            grid-template-areas:
                "summary" "issuance"
                "repay" "timeline"
                "ops";
        }
    }
    .panel-dual { height: 100%; display: flex; flex-direction: column; }
    .panel-dual .info-card-body { flex: 1; display: flex; flex-direction: column; min-height: 0; }
    .panel-summary-line {
        margin: 0 0 0.65rem; font-size: 0.875rem; line-height: 1.45;
        min-height: 2.5rem;
    }
    .panel-fixed-rows {
        width: 100%; table-layout: fixed; border-collapse: collapse;
    }
    .panel-fixed-rows th,
    .panel-fixed-rows td {
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .panel-fixed-rows tbody tr { height: 2rem; }
    .panel-fixed-rows tbody tr.row-pad td {
        color: transparent; border-color: rgba(255,255,255,0.04);
    }
    .col-repay-custody { width: 38%; }
    .col-repay-date { width: 28%; }
    .col-repay-amt { width: 34%; }
    .col-tl-time { width: 22%; }
    .col-tl-type { width: 12%; }
    .col-tl-title { width: 44%; }
    .col-tl-detail { width: 22%; }
    .timeline-goto-entry, .timeline-detail-link {
        background: none; border: none; color: #38bdf8; cursor: pointer;
        padding: 0; font: inherit; font-size: inherit;
    }
    .timeline-goto-entry:hover, .timeline-detail-link:hover { text-decoration: underline; }
    .panel-expand { margin-top: 0.5rem; }
    .panel-expand-summary { cursor: pointer; color: #38bdf8; font-size: 0.85rem; }
    .panel-expand-table { margin-top: 0; }
    .panel-expand-table table { border-top: none; }
    /* ── Summary Card (4-line scan + hover tips) ─────────────── */
    .card-summary {
        background: rgba(255,255,255,0.06); border: 1px solid rgba(56,189,248,0.2);
        border-radius: 12px; padding: 12px 14px;
    }
    .card-summary-anomaly { border-left: 3px solid #f87171; }
    .card-summary-v2 .summary-line {
        display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px;
        font-size: 13px; color: #cbd5e1; line-height: 1.5;
    }
    .card-summary-v2 .summary-line + .summary-line {
        margin-top: 8px; padding-top: 8px;
        border-top: 1px solid rgba(255,255,255,0.06);
    }
    .summary-line-money { font-variant-numeric: tabular-nums; }
    .summary-em { font-weight: 700; color: #f8fafc; font-size: 15px; }
    .summary-sep { color: #64748b; user-select: none; padding: 0 1px; }
    .summary-warn { color: #f87171; font-weight: 600; }
    .summary-chip { position: relative; display: inline-flex; align-items: center; max-width: 100%; }
    .summary-chip.has-tip { cursor: help; border-bottom: 1px dotted rgba(148,163,184,0.35); }
    .summary-chip.has-tip:hover { border-bottom-color: rgba(56,189,248,0.55); color: #e2e8f0; }
    .summary-chip .tip-panel {
        display: none; position: absolute; left: 0; top: calc(100% + 6px); z-index: 60;
        min-width: 210px; max-width: 340px; padding: 8px 10px;
        background: #1e293b; border: 1px solid rgba(56,189,248,0.25); border-radius: 8px;
        font-size: 12px; line-height: 1.45; color: #e2e8f0; font-weight: 400;
        box-shadow: 0 8px 24px rgba(0,0,0,0.35); white-space: normal;
    }
    .summary-chip.has-tip:hover .tip-panel,
    .summary-chip.has-tip:focus-within .tip-panel { display: block; }
    .summary-chip-editable .mark-display { font-size: 13px; }
    .summary-chip-line { max-width: 100%; }
    .check-ok { color: #34d399; font-weight: 600; }
    .check-bad { color: #f87171; font-weight: 600; }
    .tiny-badge { font-size: 10px; padding: 1px 6px; margin-left: 4px; vertical-align: middle; }
    /* legacy summary tiers (hero wrapper) */
    .info-group { display: flex; flex-direction: column; gap: 2px; }
    .info-label { font-size: 12px; color: #94a3b8; line-height: 1.2; }
    .detail-primary {
        display: flex; flex-wrap: wrap; gap: 8px 24px;
        padding-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.08);
        margin-bottom: 12px;
    }
    .info-value-xl {
        font-size: 22px; font-weight: 700; color: #f8fafc;
        font-variant-numeric: tabular-nums; line-height: 1.2;
    }
    .info-value-sm { font-size: 13px; color: #94a3b8; line-height: 1.3; }
    .check-icon-pass { color: #34d399; font-weight: 600; }
    .check-icon-fail { color: #f87171; font-weight: 600; }
    .info-warn { color: #f87171; }
    .summary-select {
        font-size: 12px; color: #e2e8f0; background: rgba(255,255,255,0.07);
        border: 1px solid rgba(255,255,255,0.12); border-radius: 5px;
        padding: 2px 6px; cursor: pointer; outline: none; max-width: 120px;
    }
    .summary-select:focus { border-color: rgba(99,179,237,0.5); }
    .summary-custody-note { font-size: 11px; color: #475569; width: 100%; margin-top: 2px; }
    .mark-edit-hidden { display: none; }
    .mark-display {
        font-size: 12px; color: #e2e8f0; cursor: default;
        border-bottom: 1px dashed rgba(255,255,255,0.18);
        padding: 1px 0; user-select: none;
    }
    .mark-display:hover { border-bottom-color: rgba(99,179,237,0.55); color: #93c5fd; }
    /* kept for sidebar asset-info card */
    .hero-lbl { display: block; font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.25rem; }
    .sidebar-section + .sidebar-section { border-top: 1px solid rgba(255,255,255,0.08); }
    .sidebar-asset-info { padding-bottom: 0.5rem; }
    .compact-queue { max-height: 72vh; overflow-y: auto; }
    .queue-line3 { font-size: 0.68rem; margin-top: 0.15rem; }
    .selection-notice {
        margin-top: 0.5rem; padding: 0.45rem 0.75rem;
        background: rgba(56,189,248,0.08); border: 1px solid rgba(56,189,248,0.2);
        border-radius: 8px; color: #bae6fd;
    }
    .asset-card {
        padding: 0.75rem; margin: 0.5rem 0.75rem;
        background: rgba(56,189,248,0.06); border: 1px solid rgba(56,189,248,0.15);
        border-radius: 10px; font-size: 0.85rem;
    }
    .asset-card p { margin-bottom: 0.35rem; }
    .asset-card-followup { margin-top: 0.4rem; }
    .split-list { max-height: 200px; overflow-y: auto; }
    .queue-item {
        display: block; padding: 0.55rem 0.75rem;
        border-bottom: 1px solid rgba(255,255,255,0.06);
        color: inherit; text-decoration: none;
    }
    .queue-item:hover { background: rgba(56,189,248,0.08); }
    .queue-item.active {
        background: rgba(56,189,248,0.16);
        box-shadow: inset 3px 0 0 #38bdf8;
    }
    .queue-line1 {
        font-size: 0.82rem; font-weight: 500; line-height: 1.3; word-break: break-all;
        display: flex; justify-content: space-between; align-items: flex-start; gap: 0.35rem;
    }
    .queue-line2 {
        font-size: 0.72rem; color: #94a3b8; margin-top: 0.2rem;
        display: flex; flex-wrap: wrap; gap: 0.35rem 0.5rem; align-items: center;
    }
    .custody-card {
        padding: 0.75rem; margin: 0.5rem 0.75rem;
        background: rgba(56,189,248,0.06); border: 1px solid rgba(56,189,248,0.15);
        border-radius: 10px; min-height: 72px;
    }
    .custody-card-multi { margin-bottom: 0; border-radius: 10px 10px 0 0; }
    .custody-card-code { font-size: 0.95rem; font-weight: 600; word-break: break-all; }
    .custody-card-meta {
        font-size: 0.75rem; color: #94a3b8; margin-top: 0.35rem;
        display: flex; flex-wrap: wrap; gap: 0.25rem 0.5rem; align-items: center;
    }
    .custody-card-followup { margin-top: 0.4rem; }
    .info-card {
        background: rgba(0,0,0,0.18); border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px; padding: 1rem 1.1rem; height: 100%;
    }
    .info-card-primary { border-color: rgba(56,189,248,0.25); background: rgba(56,189,248,0.05); }
    .info-card-alert { border-color: rgba(239,68,68,0.3); }
    .info-card-title { font-size: 0.95rem; margin-bottom: 0.65rem; color: #f1f5f9; font-weight: 600; }
    details.info-card { padding: 0; height: auto; }
    details.info-card > summary.info-card-title {
        padding: 1rem 1.1rem; margin: 0; cursor: pointer; list-style: none;
    }
    details.info-card > summary.info-card-title::-webkit-details-marker { display: none; }
    details.info-card > summary.info-card-title::before { content: "▶ "; font-size: 0.7rem; color: #94a3b8; }
    details.info-card[open] > summary.info-card-title::before { content: "▼ "; }
    details.info-card .info-card-body { padding: 0 1.1rem 1rem; }
    .ops-panel { background: rgba(251,191,36,0.06); border-color: rgba(251,191,36,0.15); }
    .ops-panel-alert { border-color: rgba(239,68,68,0.35); box-shadow: inset 3px 0 0 #f87171; }
    .ops-list { margin: 0.35rem 0 0 1.1rem; font-size: 0.85rem; }
    .mark-readonly { margin-bottom: 0.65rem; padding-bottom: 0.65rem; border-bottom: 1px solid rgba(255,255,255,0.06); font-size: 0.85rem; }
    .mark-edit { margin-bottom: 0.35rem; }
    .sub-card { background: rgba(0,0,0,0.15); padding: 0.65rem; border-radius: 8px; margin-bottom: 0.5rem; }
    .sub-hd { font-weight: 600; margin-bottom: 0.35rem; }
    /* Issuance panel */
    .issuance-group { margin-bottom: 10px; }
    .issuance-group-hd {
        font-size: 12px; font-weight: 600; color: #64748b;
        text-transform: uppercase; letter-spacing: 0.05em;
        cursor: pointer; padding: 4px 0; margin-bottom: 6px;
        list-style: none;
    }
    .issuance-group-hd::-webkit-details-marker { display: none; }
    .issuance-group > summary.issuance-group-hd::before { content: "▶ "; font-size: 10px; }
    details.issuance-group[open] > summary.issuance-group-hd::before { content: "▼ "; }
    .issuance-custody { color: #94a3b8; font-variant-numeric: tabular-nums; }
    .issuance-record {
        background: rgba(0,0,0,0.15); border-radius: 8px;
        padding: 8px 12px; margin-bottom: 6px;
    }
    .issuance-issue-date { font-size: 13px; font-weight: 700; color: #e2e8f0; margin-bottom: 4px; }
    .issuance-line { font-size: 12px; color: #94a3b8; line-height: 1.7; word-break: break-all; }
    .monitor-summary { margin-bottom: 0.5rem; }
    .muted { color: #94a3b8; }
    .tiny { font-size: 0.75rem; }
    .lbl { color: #94a3b8; font-size: 0.8rem; margin-right: 0.35rem; }
    .empty { color: #64748b; padding: 0.5rem 0; }
    .badge { display: inline-block; padding: 0.15rem 0.45rem; border-radius: 4px; font-size: 0.75rem; border: 1px solid rgba(255,255,255,0.15); }
    .ok-badge { background: rgba(34,197,94,0.15); color: #4ade80; }
    .fail-badge { background: rgba(239,68,68,0.15); color: #f87171; }
    table { font-size: 0.8rem; }
    th, td { padding: 0.4rem 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.06); text-align: left; vertical-align: middle; }
    th { color: #94a3b8; font-weight: 500; }
    .num { text-align: right; font-variant-numeric: tabular-nums; }
    .sticky-write-bar {
        position: sticky; bottom: 0; z-index: 30;
        width: 100%;
        background: rgba(15,23,42,0.96); border: 1px solid rgba(56,189,248,0.25);
        border-radius: 12px;
        backdrop-filter: blur(8px); margin-top: auto;
        box-shadow: 0 -4px 24px rgba(0,0,0,0.35);
        overflow: hidden;
    }
    .sticky-write-collapsed {
        display: flex; align-items: center; justify-content: space-between; gap: 0.65rem;
        padding: 0.55rem 0.85rem;
    }
    .sticky-write-actions { display: flex; align-items: center; gap: 0.5rem; flex-shrink: 0; }
    .write-toggle {
        display: inline-flex; align-items: center; gap: 0.35rem;
        background: none; border: none; color: #f8fafc; cursor: pointer;
        font-size: 0.95rem; font-weight: 600; padding: 0;
        min-width: 0; flex: 1 1 auto;
    }
    .write-toggle-icon { font-size: 0.65rem; color: #94a3b8; }
    .sticky-write-bar[data-expanded="0"] .sticky-write-panel { display: none; }
    .sticky-write-bar[data-expanded="0"] .write-collapse-btn { display: none; }
    .sticky-write-bar[data-expanded="1"] #followup-expand-btn { display: none; }
    .sticky-write-panel { border-top: 1px solid rgba(255,255,255,0.06); }
    .sticky-write-inner {
        padding: 0.85rem 0.85rem 1rem;
        max-height: 45vh; overflow-y: auto;
    }
    .sticky-write-title { font-size: 0.95rem; color: #f8fafc; }
    .entry-tabs {
        display: flex; flex-wrap: nowrap; gap: 0.35rem;
        overflow-x: auto; margin: 0.5rem 0 0.65rem;
        padding-bottom: 0.15rem;
    }
    .entry-tab {
        flex-shrink: 0; padding: 0.35rem 0.7rem; border-radius: 999px;
        border: 1px solid rgba(255,255,255,0.15); background: rgba(255,255,255,0.04);
        color: #94a3b8; cursor: pointer; font-size: 0.8rem; white-space: nowrap;
    }
    .entry-tab.active {
        background: rgba(56,189,248,0.2); border-color: rgba(56,189,248,0.45); color: #e2e8f0;
    }
    .followup-pane { display: none; }
    .followup-pane.active { display: block; }
    .followup-readonly p { margin-bottom: 0.45rem; font-size: 0.85rem; }
    .readonly-hint { margin-bottom: 0.65rem !important; }
    .entry-cite-btn { margin-top: 0.35rem; }
    .followup-form-grid {
        display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem 0.75rem;
        margin: 0.5rem 0;
    }
    .followup-form-grid .span-2 { grid-column: span 2; }
    @media (max-width: 700px) {
        .followup-form-grid { grid-template-columns: 1fr; }
        .followup-form-grid .span-2 { grid-column: span 1; }
    }
    .followup-form label { display: block; font-size: 0.82rem; }
    .followup-form input, .followup-form textarea, .followup-form select {
        width: 100%; margin-top: 0.2rem; padding: 0.4rem; border-radius: 6px;
        border: 1px solid rgba(255,255,255,0.15); background: rgba(0,0,0,0.25); color: #e2e8f0;
    }
    .form-actions { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
    .btn {
        padding: 0.5rem 1rem; border-radius: 6px; border: 1px solid rgba(255,255,255,0.2);
        background: rgba(255,255,255,0.08); color: #e2e8f0; cursor: pointer; font-size: 0.85rem;
        height: 36px; box-sizing: border-box; display: inline-flex; align-items: center;
    }
    .btn.primary { background: #0ea5e9; border-color: #0ea5e9; font-weight: 600; }
    .btn-ghost { display: inline-block; text-align: center; }
    .mark-select {
        padding: 0.35rem; border-radius: 6px; background: rgba(0,0,0,0.2);
        color: #e2e8f0; border: 1px solid rgba(255,255,255,0.15);
    }
    .file-preview { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.25rem; }
    .file-chip {
        display: inline-block; padding: 0.25rem 0.5rem; border-radius: 6px;
        background: rgba(255,255,255,0.08); font-size: 0.75rem;
    }
    .file-chip-img { display: flex; flex-direction: column; gap: 0.25rem; align-items: flex-start; }
    .file-thumb { max-width: 64px; max-height: 64px; border-radius: 4px; object-fit: cover; }
"""

_WORKBENCH_CSS = f"""
<style>
{PAGE_CHROME_CSS}
{WORKBENCH_BODY_CSS}
{STANDARD_HEADER_CSS}
{BTN_CSS}
{TABLE_SCROLL_CSS}
{_WORKBENCH_SPECIFIC_CSS}
</style>
"""
