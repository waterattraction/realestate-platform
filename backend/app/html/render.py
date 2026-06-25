"""Overdue workbench HTML — dumb render from get_detail() DTO only."""

from html import escape
from urllib.parse import quote

from app.html.formatters import (
    fmt_check_result,
    fmt_delinquency_badge,
    fmt_money,
    fmt_risk_badge,
)
from app.overdue.ui_constants import (
    FOLLOWUP_STATUS_LABELS,
    INTERNAL_STATUS_OPTIONS,
    TRUST_MARKER_OPTIONS,
)
from app.service.checks_service import RECONCILIATION_BASIS_LABEL

_TIMELINE_PREVIEW = 3
_REPAYMENT_PREVIEW = 5


def render_overdue_workbench_html(
    dto: dict,
    trust_product_id: int | None = None,
    custody_asset_code: str | None = None,
    new_followup: bool = False,
) -> str:
    queue = dto.get("queue") or []
    detail = dto.get("detail")
    data_date = dto.get("data_date") or "—"
    resolved_custody = custody_asset_code or dto.get("custody_asset_code")

    def workbench_qs(trust_asset_id: int | None = None) -> str:
        parts = []
        if trust_product_id is not None:
            parts.append(f"trust_product_id={trust_product_id}")
        if resolved_custody:
            parts.append(f"custody_asset_code={quote(str(resolved_custody))}")
        if trust_asset_id is not None:
            parts.append(f"trust_asset_id={trust_asset_id}")
        return "?" + "&".join(parts) if parts else ""

    product_hidden = (
        f'<input type="hidden" name="trust_product_id" value="{trust_product_id}">'
        if trust_product_id is not None
        else ""
    )
    custody_hidden = (
        f'<input type="hidden" name="custody_asset_code" value="{escape(resolved_custody)}">'
        if resolved_custody
        else ""
    )

    sidebar_html = _render_sidebar(
        dto, queue, trust_product_id, resolved_custody, workbench_qs
    )
    panels = _render_panels(dto, detail, resolved_custody)
    header_actions = _render_header_actions(trust_product_id)
    top_bar = _render_top_bar(dto, data_date)
    write_bar = ""
    if detail:
        write_bar = _panel_followup_write(
            product_hidden, custody_hidden, workbench_qs, dto, new_followup=new_followup
        )

    json_qs = workbench_qs()
    identity_id = dto.get("identity_id")
    identity_link = ""
    if identity_id:
        identity_link = f' · <a href="/asset-workbench/{identity_id}">Asset Workbench</a>'

    scroll_flag = "1" if new_followup else "0"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>逾期跟进工作台 · 房地产资产证券化平台</title>
    {_WORKBENCH_CSS}
</head>
<body data-scroll-followup="{scroll_flag}">
<div class="page-wrap">
<div class="container">
    <div class="breadcrumb">
        <a href="/overdue">逾期管理</a> / 托管房源跟进工作台
    </div>
    <header class="page-header">
        <div class="header-row">
            <h1>托管房源逾期跟进工作台</h1>
            {header_actions}
        </div>
        {top_bar}
        <p class="muted header-meta">数据只读区 + 底栏录入 · <a href="/overdue/workbench/detail{json_qs}">JSON</a>{identity_link}</p>
    </header>
    <div class="workbench">
        <aside class="sidebar panel">
            {sidebar_html}
        </aside>
        <main class="workbench-main">
            <div class="main-body">{panels}</div>
        </main>
    </div>
</div>
{write_bar}
</div>
{_WORKBENCH_SCRIPTS}
</body>
</html>"""


def _render_header_actions(trust_product_id: int | None) -> str:
    back_href = "/overdue"
    if trust_product_id is not None:
        back_href = f"/overdue?trust_product_id={trust_product_id}"
    return f"""<div class="header-actions">
        <a class="btn btn-ghost" href="{back_href}">返回列表</a>
        <button type="button" class="btn btn-ghost" onclick="location.reload()">刷新数据</button>
    </div>"""


def _render_top_bar(dto: dict, data_date: str) -> str:
    summary = dto.get("summary") or {}
    product = escape(str(summary.get("trust_product_name") or "—"))
    return f"""<p class="header-sub">产品 <strong>{product}</strong> · 数据日期 {escape(data_date)}</p>"""


def _overdue_label(summary: dict) -> str:
    bucket = summary.get("delinquency_bucket")
    od = summary.get("overdue_days")
    if bucket == "ES":
        return "提前结清"
    if od is not None:
        return f"逾期 {od} 天"
    return "—"


def _render_hero_overdue_card(dto: dict, custody: str | None, checks: dict | None) -> str:
    summary = dto.get("summary") or {}
    custody_esc = escape(str(custody or "—"))
    bucket = summary.get("delinquency_bucket")
    od_label = escape(_overdue_label(summary))
    internal = escape(str(summary.get("internal_status") or "待跟进"))
    initial = summary.get("initial_transfer_amount")
    repaid = summary.get("repaid_amount")
    remaining = summary.get("remaining_amount")
    formula = (
        f"初始 {fmt_money(initial)} − 已还 {fmt_money(repaid)} = 剩余 {fmt_money(remaining)}"
    )
    od_cls = "hero-stat-warn" if summary.get("overdue_days") and bucket != "ES" else ""
    checks_inline = _render_hero_checks_inline(checks)
    return f"""<div class="hero-overdue-card">
        <div class="hero-main">
            <div class="hero-remaining-block">
                <span class="hero-lbl">剩余金额</span>
                <span class="hero-remaining-val">{fmt_money(remaining)}</span>
                <span class="hero-formula muted tiny">{formula}</span>
            </div>
            <div class="hero-stats">
                <div class="hero-stat"><span class="hero-stat-lbl">托管号</span><span class="hero-stat-val">{custody_esc}</span></div>
                <div class="hero-stat"><span class="hero-stat-lbl">累计已还</span><span class="hero-stat-val num">{fmt_money(repaid)}</span></div>
                <div class="hero-stat"><span class="hero-stat-lbl">逾期</span><span class="hero-stat-val {od_cls}">{od_label}</span></div>
                <div class="hero-stat"><span class="hero-stat-lbl">M 级</span><span class="hero-stat-val">{fmt_delinquency_badge(bucket)}</span></div>
                <div class="hero-stat"><span class="hero-stat-lbl">内部状态</span><span class="hero-stat-val">{internal}</span></div>
                <div class="hero-stat"><span class="hero-stat-lbl">分笔</span><span class="hero-stat-val">{summary.get('split_count', 0)} 笔</span></div>
            </div>
        </div>
        {checks_inline}
    </div>"""


def _hero_check_segment(label: str, passed: bool, tooltip: str, diff) -> str:
    diff_cls = "hero-check-diff-warn" if not passed else ""
    return f"""<span class="hero-check-segment" title="{escape(tooltip)}">
        <span class="hero-check-name">{escape(label)}</span>
        {fmt_check_result(passed)}
        <span class="hero-check-diff {diff_cls}">差额 {fmt_money(diff)}</span>
    </span>"""


def _render_hero_checks_inline(checks: dict | None) -> str:
    if not checks:
        return """<div class="hero-checks-inline">
            <div class="hero-checks-row muted tiny">金额检查：—</div>
        </div>"""
    bal = checks["balance_equation"]
    cross = checks["cross_sheet_repayment"]
    bal_tip = (
        f"剩余 {fmt_money(bal['left_amount'])} vs 初始−已还 {fmt_money(bal['right_amount'])}"
    )
    cross_tip = (
        f"监控已还 {fmt_money(cross['left_amount'])} vs 还款明细 "
        f"{fmt_money(cross['right_amount'])}"
    )
    has_anomaly = not (bal["passed"] and cross["passed"])
    alert_cls = " hero-checks-alert" if has_anomaly else ""
    seg_bal = _hero_check_segment("余额等式", bal["passed"], bal_tip, bal["diff_amount"])
    seg_cross = _hero_check_segment("跨表已还", cross["passed"], cross_tip, cross["diff_amount"])
    return f"""<div class="hero-checks-inline{alert_cls}">
        <div class="hero-checks-row">
            {seg_bal}
            <span class="hero-check-sep" aria-hidden="true">·</span>
            {seg_cross}
        </div>
        <p class="hero-check-basis muted tiny">核对基准：{escape(RECONCILIATION_BASIS_LABEL)}</p>
    </div>"""


def _render_sidebar(
    dto: dict,
    queue: list,
    trust_product_id: int | None,
    current_custody: str | None,
    workbench_qs,
) -> str:
    product_queue_html = _render_product_queue(
        dto.get("product_queue") or {}, trust_product_id, current_custody
    )
    custody_block = _render_custody_block(
        queue,
        dto.get("selected_asset_id"),
        workbench_qs,
        current_custody,
        dto.get("trust_mark") or {},
        dto.get("summary") or {},
    )
    return f"""
        <div class="sidebar-section">
            <div class="panel-hd">产品跟进清单 M2+</div>
            <div class="queue-body compact-queue">{product_queue_html}</div>
        </div>
        <div class="sidebar-section sidebar-custody">
            {custody_block}
        </div>
    """


def _render_product_queue(
    product_queue: dict, trust_product_id: int | None, current_custody: str | None
) -> str:
    items = product_queue.get("items") or []
    if not items:
        return '<div class="empty">暂无 M2+ 待跟进</div>'
    html = ""
    for it in items:
        custody = it.get("custody_asset_code") or ""
        active = "active" if custody == current_custody else ""
        pid = trust_product_id or product_queue.get("trust_product_id")
        href = f"/overdue/workbench?trust_product_id={pid}&custody_asset_code={quote(str(custody))}"
        bucket = it.get("delinquency_bucket")
        bucket_html = fmt_delinquency_badge(bucket) if bucket else "—"
        html += f"""
        <a class="queue-item compact {active}" href="{href}">
            <div class="queue-line1">{escape(str(custody))}</div>
            <div class="queue-line2">
                <span>逾期 {it.get('overdue_days', '—')} 天</span>
                <span>{bucket_html}</span>
                <span>跟进 {it.get('followup_count', 0)} 次</span>
                <span>{escape(str(it.get('internal_status') or '—'))}</span>
            </div>
        </a>
        """
    return html


def _last_followup_html(summary: dict) -> str:
    at = summary.get("last_follow_up_at")
    owner = summary.get("last_follow_up_owner")
    if not at and not owner:
        return '<div class="custody-card-followup muted tiny">最近跟进：—</div>'
    at_esc = escape(str(at or "—"))
    owner_esc = escape(str(owner or "—"))
    return f'<div class="custody-card-followup muted tiny">最近跟进：{at_esc} · {owner_esc}</div>'


def _render_custody_block(
    queue: list,
    selected_id: int | None,
    workbench_qs,
    resolved_custody: str | None,
    trust_mark: dict,
    summary: dict,
) -> str:
    if not queue:
        msg = "暂无房源" if resolved_custody else "暂无逾期房源"
        return f'<div class="panel-hd">当前托管</div><div class="empty">{msg}</div>'

    custody_esc = escape(str(resolved_custody or queue[0].get("custody_asset_code") or "—"))
    split_count = len(queue)
    bucket = summary.get("delinquency_bucket") or queue[0].get("delinquency_bucket")
    bucket_html = fmt_delinquency_badge(bucket) if bucket else "—"
    internal = escape(str(trust_mark.get("internal_status") or summary.get("internal_status") or "待跟进"))
    followup_line = _last_followup_html(summary)

    if split_count == 1:
        item = queue[0]
        recon_flag = "" if item["checks"]["cross_sheet_repayment"]["passed"] else " ⚠"
        return f"""
        <div class="panel-hd">当前托管</div>
        <div class="custody-card">
            <div class="custody-card-code">{custody_esc}{recon_flag}</div>
            <div class="custody-card-meta">共 1 笔 · {bucket_html} · {internal}</div>
            {followup_line}
        </div>
        """

    list_html = _render_split_list(queue, selected_id, workbench_qs)
    return f"""
    <div class="panel-hd">当前托管</div>
    <div class="custody-card custody-card-multi">
        <div class="custody-card-code">{custody_esc}</div>
        <div class="custody-card-meta">共 {split_count} 笔 · {bucket_html} · {internal}</div>
        {followup_line}
    </div>
    <div class="split-list">{list_html}</div>
    """


def _render_split_list(queue: list, selected_id: int | None, workbench_qs) -> str:
    items = ""
    for item in queue:
        active = "active" if item["trust_asset_id"] == selected_id else ""
        recon_flag = "" if item["checks"]["cross_sheet_repayment"]["passed"] else " ⚠"
        custody = escape(str(item.get("custody_asset_code") or "—"))
        source = escape(str(item.get("source_asset_code") or item.get("asset_code") or "—"))
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
                <span class="queue-code"><span title="托管">{custody}</span>
                <span class="muted">/ {source}</span>{recon_flag}</span>
                {badge}
            </div>
            <div class="queue-line2">
                <span>{od_label}</span>
                <span>评分 {score}</span>
                <span>{follow_label}</span>
            </div>
        </a>
        """
    return items


def _render_panels(dto: dict, detail: dict | None, custody: str | None) -> str:
    if not detail:
        return '<div class="empty">请从左侧选择房源</div>'
    hero = _render_hero_overdue_card(dto, custody, dto.get("checks"))
    grid = f"""
    <div class="panel-grid">
        <div class="grid-monitor">{_panel_monitor(dto.get("monitor") or {}, dto.get("summary") or {}, dto.get("data_date"))}</div>
        <div class="grid-ops">{_panel_ops(dto.get("ops"), dto.get("summary") or {})}</div>
        <div class="grid-repayment">{_panel_repayment(dto.get("repayment") or {})}</div>
        <div class="grid-trust">{_panel_trust_mark(dto.get("trust_mark") or {}, dto)}</div>
        <div class="grid-timeline">{_panel_timeline(dto.get("timeline") or [])}</div>
        <div class="grid-issuance">{_panel_issuance(dto.get("issuance_records") or [])}</div>
    </div>
    """
    return hero + grid


def _panel_issuance(records: list) -> str:
    count = len(records)
    if not records:
        inner = '<p class="empty">暂无发行明细 · <a href="/issuance/records">发行记录</a></p>'
    else:
        cards = ""
        for rec in records:
            issue = escape(str(rec.get("issue_date") or "—"))
            cards += f"""
            <div class="sub-card">
                <p class="sub-hd">发行日 {issue}</p>
                <p><span class="lbl">合同</span>{escape(str(rec.get('contract_name') or '—'))}</p>
                <p><span class="lbl">债务人</span>{escape(str(rec.get('debtor_name') or '—'))}</p>
                <p><span class="lbl">地址</span>{escape(str(rec.get('property_address') or '—'))}</p>
                <p><span class="lbl">城市</span>{escape(str(rec.get('city') or '—'))}</p>
                <p><span class="lbl">转让价款</span>{fmt_money(rec.get('receivable_transfer_amount'))}</p>
                <p><span class="lbl">合同金额</span>{fmt_money(rec.get('receivable_contract_amount'))}</p>
                <p><span class="lbl">代扣租比</span>{escape(str(rec.get('rent_withholding_ratio') or '—'))}</p>
                <p class="muted tiny">来源 {escape(str(rec.get('source_file_name') or ''))}</p>
            </div>
            """
        inner = cards
    return f"""<details class="info-card info-card-folded">
        <summary class="info-card-title">发行信息（{count} 条）</summary>
        <div class="info-card-body">{inner}</div>
    </details>"""


def _panel_repayment(rep: dict) -> str:
    items = rep.get("items") or []
    preview_rows = ""
    for it in items[:_REPAYMENT_PREVIEW]:
        preview_rows += f"""<tr>
            <td>{escape(str(it.get('period_no') or '—'))}</td>
            <td>{escape(str(it.get('repayment_date') or '—'))}</td>
            <td class="num">{fmt_money(it.get('actual_repayment_amount'))}</td>
            <td>{escape(str(it.get('source_asset_code') or it.get('asset_code') or '—'))}</td>
        </tr>"""
    if not preview_rows:
        preview_rows = '<tr><td colspan="4" class="empty">缺少还款明细，逾期天数可能无法重算</td></tr>'
    preview_table = f"""<div class="table-wrap"><table>
        <thead><tr><th>期次</th><th>还款日</th><th>实还</th><th>分笔</th></tr></thead>
        <tbody>{preview_rows}</tbody></table></div>"""
    rest_block = ""
    if len(items) > _REPAYMENT_PREVIEW:
        rest_rows = ""
        for it in items[_REPAYMENT_PREVIEW:50]:
            rest_rows += f"""<tr>
                <td>{escape(str(it.get('period_no') or '—'))}</td>
                <td>{escape(str(it.get('repayment_date') or '—'))}</td>
                <td class="num">{fmt_money(it.get('actual_repayment_amount'))}</td>
                <td>{escape(str(it.get('source_asset_code') or it.get('asset_code') or '—'))}</td>
            </tr>"""
        rest_block = f"""<details class="repayment-details">
            <summary class="muted tiny">查看全部还款明细（{len(items)} 条）</summary>
            <div class="table-wrap"><table>
            <thead><tr><th>期次</th><th>还款日</th><th>实还</th><th>分笔</th></tr></thead>
            <tbody>{rest_rows}</tbody></table></div>
        </details>"""
    return f"""<div class="info-card">
        <h3 class="info-card-title">还款情况</h3>
        <div class="info-card-body">
            <p>累计实还 <strong>{fmt_money(rep.get('total_repaid'))}</strong>
            · 最近还款日 {escape(str(rep.get('recent_repayment_date') or '—'))}
            · 期次 {rep.get('period_count', 0)}</p>
            {preview_table}
            {rest_block}
        </div>
    </div>"""


def _panel_monitor(mon: dict, summary: dict, data_date: str | None) -> str:
    custody = mon.get("custody") or {}
    splits = mon.get("splits") or []
    rows = ""
    for s in splits:
        sod = s.get("overdue_days")
        rows += f"""<tr>
            <td>{escape(str(s.get('source_asset_code') or s.get('asset_code') or '—'))}</td>
            <td class="num">{fmt_money(s.get('initial_transfer_amount'))}</td>
            <td class="num">{fmt_money(s.get('repaid_amount'))}</td>
            <td class="num">{fmt_money(s.get('remaining_amount'))}</td>
            <td>{sod if sod is not None else '—'}</td>
            <td>{fmt_delinquency_badge(s.get('delinquency_bucket'))}</td>
        </tr>"""
    table = f"""<div class="table-wrap"><table>
        <thead><tr><th>分笔</th><th>初始</th><th>已还</th><th>剩余</th><th>逾期天</th><th>M级</th></tr></thead>
        <tbody>{rows or '<tr><td colspan="6" class="empty">无</td></tr>'}</tbody></table></div>"""
    return f"""<div class="info-card info-card-primary">
        <h3 class="info-card-title">当前监控</h3>
        <div class="info-card-body">
            <p class="muted tiny">分笔 {custody.get('split_count', 0)} 笔 · 数据日期 {escape(str(data_date or '—'))}</p>
            <p class="muted tiny monitor-summary">托管汇总：初始 {fmt_money(custody.get('initial_transfer_amount'))}
                · 已还 {fmt_money(custody.get('repaid_amount'))}
                · 剩余 {fmt_money(custody.get('remaining_amount'))}
                · 逾期 {escape(_overdue_label(summary))}</p>
            {table}
        </div>
    </div>"""


def _panel_trust_mark(mark: dict, dto: dict) -> str:
    pid = dto.get("trust_product_id")
    custody = dto.get("custody_asset_code")
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
            <div class="mark-edit muted tiny">修改标注</div>
            <p><span class="lbl">信托标记</span>
            <select class="mark-select" data-field="trust_marker"
                    data-product="{pid}" data-custody="{escape(str(custody))}" data-date="{escape(str(data_date))}">
            {marker_opts}</select></p>
            <p><span class="lbl">内部状态</span>
            <select class="mark-select" data-field="internal_status"
                    data-product="{pid}" data-custody="{escape(str(custody))}" data-date="{escape(str(data_date))}">
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


def _timeline_row(ev: dict) -> str:
    legacy = ""
    if ev.get("legacy"):
        legacy = f' <span class="badge">{escape(ev.get("legacy_label") or "历史")}</span>'
    att_html = ""
    for att in ev.get("attachments") or []:
        aid = att.get("id")
        fname = escape(str(att.get("file_name") or ""))
        att_html += f' <a href="/overdue/workbench/attachments/{aid}">{fname}</a>'
    return f"""<tr>
        <td>{escape(str(ev.get('occurred_at') or '—'))}</td>
        <td>{escape(str(ev.get('event_type') or '—'))}</td>
        <td>{escape(str(ev.get('title') or '—'))}{legacy}{att_html}</td>
        <td>{escape(str(ev.get('owner_name') or ev.get('amount') or '—'))}</td>
    </tr>"""


def _panel_timeline(events: list) -> str:
    if not events:
        return """<div class="info-card"><h3 class="info-card-title">跟进历史（最近 3 条）</h3>
            <p class="empty">暂无事件</p></div>"""
    preview = events[:_TIMELINE_PREVIEW]
    preview_rows = "".join(_timeline_row(ev) for ev in preview)
    table_head = """<thead><tr><th>时间</th><th>类型</th><th>摘要</th><th>详情</th></tr></thead>"""
    preview_table = f"""<div class="table-wrap"><table>
        {table_head}<tbody>{preview_rows}</tbody></table></div>"""
    rest = events[_TIMELINE_PREVIEW:]
    rest_block = ""
    if rest:
        rest_rows = "".join(_timeline_row(ev) for ev in rest)
        rest_block = f"""<details class="timeline-more">
            <summary class="timeline-more-summary">查看全部 {len(events)} 条</summary>
            <div class="table-wrap"><table>
            {table_head}<tbody>{rest_rows}</tbody></table></div>
        </details>"""
    return f"""<div class="info-card">
        <h3 class="info-card-title">跟进历史（最近 {_TIMELINE_PREVIEW} 条）</h3>
        <div class="info-card-body">
            {preview_table}
            {rest_block}
        </div>
    </div>"""


def _followup_status_options(current: str | None) -> str:
    options = ""
    for value, label in FOLLOWUP_STATUS_LABELS.items():
        selected = " selected" if value == current else ""
        options += f'<option value="{value}"{selected}>{escape(label)}</option>'
    return options


def _panel_followup_write(
    product_hidden, custody_hidden, workbench_qs, dto, *, new_followup: bool = False
) -> str:
    data_date = escape(str(dto.get("data_date") or ""))
    case = dto.get("followup_case") or {}
    current_status = case.get("status") or "in_progress"
    status_label = escape(FOLLOWUP_STATUS_LABELS.get(current_status, current_status))
    owner_val = escape(case.get("owner_name") or "")
    owner_display = owner_val if owner_val else "—"
    summary = dto.get("summary") or {}
    internal = escape(str(summary.get("internal_status") or "待跟进"))
    expanded = "1" if new_followup else "0"
    last_entry = dto.get("timeline") or []
    last_reason = ""
    last_plan = ""
    for ev in last_entry:
        if ev.get("event_type") == "followup" and not ev.get("legacy"):
            last_reason = ev.get("overdue_reason") or ""
            last_plan = ev.get("follow_up_plan") or ""
            break

    return f"""
    <div class="sticky-write-bar" id="followup-entry-form" data-expanded="{expanded}">
        <div class="sticky-write-collapsed">
            <button type="button" class="write-toggle" id="followup-expand" aria-expanded="{"true" if new_followup else "false"}">
                <span class="write-toggle-icon" aria-hidden="true">▶</span>
                <span class="sticky-write-title">本次跟进（新增）</span>
            </button>
            <span class="write-summary muted tiny">案件状态：{status_label} · 负责人：{owner_display} · 内部状态：{internal}</span>
            <button type="button" class="btn primary btn-compact" id="followup-expand-btn">展开录入</button>
            <button type="button" class="btn btn-compact write-collapse-btn" id="followup-collapse">收起</button>
        </div>
        <div class="sticky-write-panel" id="followup-write-panel">
            <div class="sticky-write-inner">
                <p class="muted tiny">跟进时间于保存时自动生成 · 每次保存追加一条跟进记录（V2.2 entries）</p>
                <form class="followup-form" id="followup-form" method="post" enctype="multipart/form-data"
                      action="/overdue/workbench/followups/entries{workbench_qs()}">
                    <input type="hidden" name="redirect_to_workbench" value="1">
                    {product_hidden}
                    {custody_hidden}
                    <input type="hidden" name="data_date" value="{data_date}">
                    <div class="followup-form-grid">
                        <label>案件状态
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
                    <div class="form-actions">
                        <button type="submit" class="btn primary">保存本次跟进</button>
                        <button type="button" class="btn" id="followup-clear">清空</button>
                    </div>
                </form>
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

    document.querySelectorAll('.mark-select').forEach(function(sel) {
        sel.addEventListener('change', function() {
            var payload = {
                trust_product_id: parseInt(this.dataset.product, 10),
                custody_asset_code: this.dataset.custody,
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

_WORKBENCH_CSS = """
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
        min-height: 100vh; color: #e2e8f0;
    }
    a { color: #38bdf8; text-decoration: none; }
    .page-wrap { padding: 1.5rem 1rem 0; padding-bottom: 0; }
    .container { max-width: 1400px; margin: 0 auto; padding-bottom: 1.5rem; }
    .breadcrumb { font-size: 0.85rem; color: #94a3b8; margin-bottom: 1rem; }
    .page-header { margin-bottom: 0.25rem; }
    .header-row { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; }
    header h1 { font-size: 1.5rem; color: #f8fafc; }
    .header-actions { display: flex; gap: 0.5rem; flex-shrink: 0; }
    .header-sub { color: #94a3b8; margin-top: 0.35rem; font-size: 0.9rem; }
    .header-meta { margin-top: 0.5rem; font-size: 0.85rem; }
    .ok-text { color: #4ade80; }
    .warn-text { color: #f87171; }
    .workbench {
        display: grid; grid-template-columns: 270px 1fr; gap: 1rem;
        margin-top: 1rem; align-items: start;
    }
    @media (max-width: 900px) { .workbench { grid-template-columns: 1fr; } }
    .panel {
        background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
        border-radius: 12px; overflow: hidden;
    }
    .panel-hd {
        padding: 0.65rem 0.85rem; border-bottom: 1px solid rgba(255,255,255,0.08);
        font-weight: 600; font-size: 0.85rem;
    }
    .main-body { display: flex; flex-direction: column; gap: 1rem; }
    .hero-overdue-card {
        background: rgba(255,255,255,0.06); border: 1px solid rgba(56,189,248,0.3);
        border-radius: 12px; padding: 1rem 1.15rem;
        display: flex; flex-direction: column; gap: 0.65rem;
    }
    .hero-main { display: flex; flex-wrap: wrap; gap: 1.25rem; align-items: flex-start; }
    .hero-remaining-block { flex: 1 1 200px; min-width: 180px; }
    .hero-lbl { display: block; font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.25rem; }
    .hero-remaining-val { font-size: 2rem; font-weight: 700; color: #38bdf8; font-variant-numeric: tabular-nums; line-height: 1.2; }
    .hero-formula { display: block; margin-top: 0.35rem; }
    .hero-stats {
        display: flex; flex-wrap: wrap; gap: 0.65rem 1rem; flex: 2 1 320px;
    }
    .hero-stat { min-width: 72px; }
    .hero-stat-lbl { display: block; font-size: 0.68rem; color: #94a3b8; }
    .hero-stat-val { font-size: 0.88rem; font-weight: 600; }
    .hero-stat-warn { color: #f87171; }
    .hero-checks-inline {
        border-top: 1px solid rgba(255,255,255,0.08);
        padding-top: 0.55rem;
        text-align: right;
    }
    .hero-checks-inline.hero-checks-alert {
        background: rgba(239,68,68,0.06);
        margin: 0 -0.35rem -0.15rem;
        padding: 0.55rem 0.35rem 0.15rem;
        border-radius: 0 0 10px 10px;
        border-left: 3px solid #f87171;
    }
    .hero-checks-row {
        display: flex; flex-wrap: wrap; align-items: center;
        justify-content: flex-end; gap: 0.35rem 0.5rem;
        font-size: 0.78rem; line-height: 1.4;
    }
    .hero-check-segment { display: inline-flex; align-items: center; gap: 0.35rem; flex-wrap: nowrap; }
    .hero-check-name { color: #94a3b8; font-weight: 500; white-space: nowrap; }
    .hero-check-segment .badge { font-size: 0.7rem; padding: 0.1rem 0.35rem; }
    .hero-check-diff { font-variant-numeric: tabular-nums; white-space: nowrap; }
    .hero-check-diff-warn { color: #f87171; font-weight: 600; }
    .hero-check-sep { color: #64748b; user-select: none; }
    .hero-check-basis { margin-top: 0.25rem; text-align: right; font-size: 0.68rem; }
    .panel-grid {
        display: grid;
        grid-template-columns: 2fr 1fr 1fr;
        grid-template-areas:
            "monitor monitor ops"
            "repayment trust timeline"
            "issuance issuance issuance";
        gap: 1rem;
    }
    .grid-monitor { grid-area: monitor; }
    .grid-ops { grid-area: ops; }
    .grid-repayment { grid-area: repayment; }
    .grid-trust { grid-area: trust; }
    .grid-timeline { grid-area: timeline; }
    .grid-issuance { grid-area: issuance; }
    @media (max-width: 1100px) {
        .panel-grid {
            grid-template-columns: 1fr 1fr;
            grid-template-areas:
                "monitor monitor"
                "ops ops"
                "repayment trust"
                "timeline timeline"
                "issuance issuance";
        }
        .hero-checks-row { justify-content: flex-start; }
        .hero-check-basis { text-align: left; }
        .hero-checks-inline { text-align: left; }
    }
    @media (max-width: 700px) {
        .panel-grid {
            grid-template-columns: 1fr;
            grid-template-areas:
                "monitor"
                "ops"
                "repayment"
                "trust"
                "timeline"
                "issuance";
        }
    }
    .sidebar-section + .sidebar-section { border-top: 1px solid rgba(255,255,255,0.08); }
    .sidebar-custody { padding-bottom: 0.5rem; }
    .compact-queue { max-height: 42vh; overflow-y: auto; }
    .split-list { max-height: 200px; overflow-y: auto; }
    .queue-item {
        display: block; padding: 0.55rem 0.75rem;
        border-bottom: 1px solid rgba(255,255,255,0.06);
        color: inherit; text-decoration: none;
    }
    .queue-item:hover, .queue-item.active { background: rgba(56,189,248,0.08); }
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
    .monitor-summary { margin-bottom: 0.5rem; }
    .repayment-details, .timeline-more { margin-top: 0.5rem; }
    .timeline-more-summary { cursor: pointer; color: #38bdf8; font-size: 0.85rem; }
    .muted { color: #94a3b8; }
    .tiny { font-size: 0.75rem; }
    .lbl { color: #94a3b8; font-size: 0.8rem; margin-right: 0.35rem; }
    .empty { color: #64748b; padding: 0.5rem 0; }
    .badge { display: inline-block; padding: 0.15rem 0.45rem; border-radius: 4px; font-size: 0.75rem; border: 1px solid rgba(255,255,255,0.15); }
    .ok-badge { background: rgba(34,197,94,0.15); color: #4ade80; }
    .fail-badge { background: rgba(239,68,68,0.15); color: #f87171; }
    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
    th, td { padding: 0.4rem 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.06); text-align: left; }
    th { color: #94a3b8; font-weight: 500; }
    .num { text-align: right; font-variant-numeric: tabular-nums; }
    .sticky-write-bar {
        position: sticky; bottom: 0; z-index: 30;
        background: rgba(15,23,42,0.96); border-top: 1px solid rgba(56,189,248,0.25);
        backdrop-filter: blur(8px); margin-top: 1rem;
        box-shadow: 0 -4px 24px rgba(0,0,0,0.35);
    }
    .sticky-write-collapsed {
        display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap;
        max-width: 1400px; margin: 0 auto; padding: 0.55rem 1rem;
    }
    .write-toggle {
        display: inline-flex; align-items: center; gap: 0.35rem;
        background: none; border: none; color: #f8fafc; cursor: pointer;
        font-size: 0.95rem; font-weight: 600; padding: 0;
    }
    .write-toggle-icon { font-size: 0.65rem; color: #94a3b8; }
    .write-summary { flex: 1 1 200px; min-width: 0; }
    .btn-compact { padding: 0.35rem 0.75rem; font-size: 0.8rem; }
    .sticky-write-bar[data-expanded="0"] .sticky-write-panel { display: none; }
    .sticky-write-bar[data-expanded="0"] .write-collapse-btn { display: none; }
    .sticky-write-bar[data-expanded="1"] #followup-expand-btn { display: none; }
    .sticky-write-panel { border-top: 1px solid rgba(255,255,255,0.06); }
    .sticky-write-inner {
        max-width: 1400px; margin: 0 auto; padding: 0.85rem 1rem 1rem;
        max-height: 45vh; overflow-y: auto;
    }
    .sticky-write-title { font-size: 0.95rem; color: #f8fafc; }
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
    }
    .btn.primary { background: #0284c7; border-color: #0284c7; font-weight: 600; }
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
    .page-wrap:has(.sticky-write-bar[data-expanded="1"]) .container { padding-bottom: 2rem; }
</style>
"""
