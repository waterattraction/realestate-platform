"""资产情况统计 — HTML 页面."""

from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

from app.ui_css import BTN_CSS, FORM_FIELD_CSS, PAGE_CHROME_CSS, STANDARD_HEADER_CSS, TABLE_SCROLL_CSS


def _fmt_num(value: float | int | None, *, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.{digits}f}"


def _fmt_ratio(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.2f}%"


def _fmt_int(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{int(value):,}"


def _period_options(selected: str) -> str:
    opts = [("week", "周"), ("month", "月"), ("year", "年")]
    parts: list[str] = []
    for val, label in opts:
        sel = " selected" if val == selected else ""
        parts.append(f'<option value="{val}"{sel}>{label}</option>')
    return "\n".join(parts)


def _product_options(products: list[dict], selected_id: int | None) -> str:
    parts: list[str] = ['<option value="">请选择产品</option>']
    for p in products:
        pid = int(p["id"])
        sel = " selected" if selected_id == pid else ""
        parts.append(
            f'<option value="{pid}"{sel}>{escape(str(p["name"]))}</option>'
        )
    return "\n".join(parts)


def render_asset_stats_page(
    products: list[dict],
    *,
    trust_product_id: int | None = None,
    issue_date: str | None = None,
    period: str = "month",
    date_from: str | None = None,
    date_to: str | None = None,
    city: str | None = None,
) -> str:
    today = date.today()
    default_from = date_from or f"{today.year}-01-01"
    default_to = date_to or today.isoformat()

    body = f"""
    <nav class="breadcrumb"><a href="/">首页</a> / 资产情况统计</nav>
    <h1>资产情况统计</h1>
    <p class="muted">
        按信托产品汇总还款流量（周/月/年）与未还清存量；资产数按<strong>资产主编号</strong>统计。
        未还清截至各产品<strong>各自最新监控快照日</strong>。
    </p>

    <div class="card">
        <form id="f" class="filters" method="get" action="/assetinfo/asset-stats">
            <div class="field">
                <label for="trust_product_id">信托产品</label>
                <select name="trust_product_id" id="trust_product_id" required>
                    {_product_options(products, trust_product_id)}
                </select>
            </div>
            <div class="field">
                <label for="issue_date">发行基准日</label>
                <select name="issue_date" id="issue_date">
                    <option value="">自动（最新发行日）</option>
                </select>
            </div>
            <div class="field">
                <label for="period">统计粒度</label>
                <select name="period" id="period">
                    {_period_options(period)}
                </select>
            </div>
            <div class="field">
                <label for="date_from">开始日期</label>
                <input type="date" name="date_from" id="date_from" value="{escape(default_from)}">
            </div>
            <div class="field">
                <label for="date_to">结束日期</label>
                <input type="date" name="date_to" id="date_to" value="{escape(default_to)}">
            </div>
            <div class="field">
                <label for="city">城市</label>
                <select name="city" id="city">
                    <option value="">全部（含分城市表）</option>
                </select>
            </div>
            <div class="field">
                <label>&nbsp;</label>
                <button type="submit" class="btn btn-primary">查询</button>
            </div>
        </form>
    </div>

    <div id="warnings" class="warn-box" style="display:none;"></div>

    <div class="card" id="baseline-card" style="display:none;">
        <h2 class="section-h">发行基准</h2>
        <div class="kpi-grid" id="baseline-kpis"></div>
        <p class="muted" id="monitor-footnote"></p>
    </div>

    <div class="card" id="period-card" style="display:none;">
        <h2 class="section-h">周期汇总</h2>
        <div class="table-scroll">
            <table class="records-table" id="period-table">
                <thead>
                    <tr>
                        <th>周期</th>
                        <th class="col-num">还款资产数</th>
                        <th class="col-num">还款金额</th>
                        <th class="col-num">未还清资产数</th>
                        <th class="col-num">还款资产占比</th>
                        <th class="col-num">还款金额占比</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
    </div>

    <div class="card" id="city-card" style="display:none;">
        <h2 class="section-h">分城市汇总</h2>
        <div id="city-sections"></div>
    </div>

    <script>
    const initialProductId = {trust_product_id or "null"};
    const initialIssueDate = {json_issue_date(issue_date)};
    const initialCity = {json_str(city)};

    function fmtNum(v) {{
        if (v === null || v === undefined) return '—';
        return Number(v).toLocaleString('zh-CN', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
    }}
    function fmtInt(v) {{
        if (v === null || v === undefined) return '—';
        return Number(v).toLocaleString('zh-CN');
    }}
    function fmtRatio(v) {{
        if (v === null || v === undefined) return '—';
        return (Number(v) * 100).toFixed(2) + '%';
    }}

    async function loadIssueDates(pid) {{
        const sel = document.getElementById('issue_date');
        sel.innerHTML = '<option value="">自动（最新发行日）</option>';
        if (!pid) return;
        const res = await fetch('/assetinfo/asset-stats/issue-dates?trust_product_id=' + pid, {{ credentials: 'same-origin' }});
        if (!res.ok) return;
        const data = await res.json();
        (data.items || []).forEach(item => {{
            const opt = document.createElement('option');
            opt.value = item.issue_date;
            opt.textContent = item.label;
            sel.appendChild(opt);
        }});
        if (initialIssueDate) sel.value = initialIssueDate;
    }}

    async function loadCities(pid, issueDate) {{
        const sel = document.getElementById('city');
        const keep = sel.value;
        sel.innerHTML = '<option value="">全部（含分城市表）</option>';
        if (!pid || !issueDate) return;
        const qs = new URLSearchParams({{ trust_product_id: pid, issue_date: issueDate }});
        const res = await fetch('/assetinfo/asset-stats/cities?' + qs, {{ credentials: 'same-origin' }});
        if (!res.ok) return;
        const data = await res.json();
        (data.items || []).forEach(city => {{
            const opt = document.createElement('option');
            opt.value = city;
            opt.textContent = city;
            sel.appendChild(opt);
        }});
        if (initialCity) sel.value = initialCity;
        else if (keep) sel.value = keep;
    }}

    function renderPeriodRows(tbody, periods) {{
        tbody.innerHTML = '';
        if (!periods || !periods.length) {{
            tbody.innerHTML = '<tr><td colspan="6" class="muted">所选区间无还款记录</td></tr>';
            return;
        }}
        periods.forEach(row => {{
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${{row.period_label}}</td>
                <td class="col-num">${{fmtInt(row.repaid_asset_count)}}</td>
                <td class="col-num">${{fmtNum(row.repayment_amount)}}</td>
                <td class="col-num">${{fmtInt(row.unpaid_asset_count)}}</td>
                <td class="col-num">${{fmtRatio(row.repaid_asset_ratio)}}</td>
                <td class="col-num">${{fmtRatio(row.repayment_amount_ratio)}}</td>`;
            tbody.appendChild(tr);
        }});
    }}

    function renderReport(data) {{
        const warnEl = document.getElementById('warnings');
        if (data.warnings && data.warnings.length) {{
            warnEl.style.display = 'block';
            warnEl.innerHTML = data.warnings.map(w => '<div>⚠ ' + w + '</div>').join('');
        }} else {{
            warnEl.style.display = 'none';
        }}

        const base = data.issuance_baseline;
        const stock = data.monitor_stock || {{}};
        const baseCard = document.getElementById('baseline-card');
        if (base) {{
            baseCard.style.display = 'block';
            document.getElementById('baseline-kpis').innerHTML = `
                <div class="kpi"><span class="kpi-label">发行基准日</span><strong>${{base.issue_date}}</strong></div>
                <div class="kpi"><span class="kpi-label">发行资产主编号数</span><strong>${{fmtInt(base.asset_primary_count)}}</strong></div>
                <div class="kpi"><span class="kpi-label">MIN可转让金额合计</span><strong>${{fmtNum(base.min_transferable_total)}}</strong></div>
                <div class="kpi"><span class="kpi-label">总代扣金额合计</span><strong>${{fmtNum(base.receivable_transfer_total)}}</strong></div>
                <div class="kpi"><span class="kpi-label">未还清资产数</span><strong>${{fmtInt(stock.unpaid_asset_count)}}</strong></div>`;
            const snap = stock.monitor_snapshot_date || '—';
            document.getElementById('monitor-footnote').textContent =
                '未还清资产数截至本产品最新监控快照日：' + snap + '（各周期表内未还清列相同）';
        }} else {{
            baseCard.style.display = 'none';
        }}

        const periodCard = document.getElementById('period-card');
        periodCard.style.display = 'block';
        renderPeriodRows(document.querySelector('#period-table tbody'), data.periods);

        const cityCard = document.getElementById('city-card');
        const citySections = document.getElementById('city-sections');
        if (data.by_city && data.by_city.length && !data.city_filter) {{
            cityCard.style.display = 'block';
            citySections.innerHTML = '';
            data.by_city.forEach(block => {{
                const wrap = document.createElement('div');
                wrap.className = 'city-block';
                const b = block.issuance_baseline || {{}};
                wrap.innerHTML = `<h3>${{block.city}}</h3>
                    <p class="muted">发行资产 ${{fmtInt(b.asset_primary_count)}} · MIN ${{fmtNum(b.min_transferable_total)}} · 转让价款 ${{fmtNum(b.receivable_transfer_total)}}</p>`;
                const table = document.createElement('table');
                table.className = 'records-table';
                table.innerHTML = `<thead><tr>
                    <th>周期</th><th class="col-num">还款资产数</th><th class="col-num">还款金额</th>
                    <th class="col-num">未还清</th><th class="col-num">资产占比</th><th class="col-num">金额占比</th>
                </tr></thead><tbody></tbody>`;
                renderPeriodRows(table.querySelector('tbody'), block.periods);
                wrap.appendChild(table);
                citySections.appendChild(wrap);
            }});
        }} else {{
            cityCard.style.display = 'none';
        }}
    }}

    async function loadReportFromQuery() {{
        const params = new URLSearchParams(window.location.search);
        const pid = params.get('trust_product_id');
        if (!pid) return;
        const res = await fetch('/assetinfo/asset-stats/data?' + params.toString(), {{ credentials: 'same-origin' }});
        if (!res.ok) {{
            document.getElementById('warnings').style.display = 'block';
            document.getElementById('warnings').textContent = '加载失败：' + res.status;
            return;
        }}
        renderReport(await res.json());
    }}

    document.getElementById('trust_product_id').addEventListener('change', async function() {{
        const pid = this.value;
        await loadIssueDates(pid);
        const issueDate = document.getElementById('issue_date').value || document.getElementById('issue_date').options[1]?.value;
        await loadCities(pid, issueDate);
    }});
    document.getElementById('issue_date').addEventListener('change', async function() {{
        const pid = document.getElementById('trust_product_id').value;
        await loadCities(pid, this.value);
    }});

    (async function init() {{
        if (initialProductId) {{
            await loadIssueDates(initialProductId);
            const issueSel = document.getElementById('issue_date');
            const issueDate = issueSel.value || issueSel.options[1]?.value;
            await loadCities(initialProductId, issueDate);
        }}
        await loadReportFromQuery();
    }})();
    </script>
    """

    return _page_shell("资产情况统计", body)


def json_issue_date(value: str | None) -> str:
    if not value:
        return "null"
    return f'"{value}"'


def json_str(value: str | None) -> str:
    if not value:
        return "null"
    return f'"{value.replace(chr(34), "")}"'


def _page_shell(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(title)}</title>
    <style>
        {PAGE_CHROME_CSS}
        {STANDARD_HEADER_CSS}
        {FORM_FIELD_CSS}
        {BTN_CSS}
        {TABLE_SCROLL_CSS}
        h1 {{ font-size: 1.5rem; color: #f8fafc; margin: 0 0 0.5rem; }}
        h2.section-h {{ font-size: 1.05rem; color: #e2e8f0; margin: 0 0 0.75rem; }}
        h3 {{ font-size: 0.95rem; color: #cbd5e1; margin: 1rem 0 0.5rem; }}
        p.muted {{ color: #94a3b8; margin-bottom: 1rem; font-size: 0.9rem; }}
        .card {{
            background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px; padding: 1.25rem; margin-bottom: 1rem;
        }}
        .filters {{ display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: flex-end; }}
        th, td {{ padding: 0.5rem 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.08); text-align: left; }}
        th {{ color: #94a3b8; }}
        .records-table {{ font-size: 0.85rem; width: 100%; }}
        .records-table th.col-num, .records-table td.col-num {{ text-align: right; }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 0.75rem;
        }}
        .kpi {{
            background: rgba(15,23,42,0.5);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            padding: 0.75rem;
        }}
        .kpi-label {{ display: block; font-size: 0.8rem; color: #94a3b8; margin-bottom: 0.25rem; }}
        .warn-box {{
            background: rgba(251,191,36,0.08);
            border: 1px solid rgba(251,191,36,0.35);
            border-radius: 8px;
            padding: 0.75rem;
            margin-bottom: 1rem;
            color: #fde68a;
            font-size: 0.9rem;
        }}
        .city-block {{
            margin-bottom: 1.25rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid rgba(255,255,255,0.08);
        }}
        .breadcrumb {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.75rem; }}
        .breadcrumb a {{ color: #38bdf8; text-decoration: none; }}
    </style>
</head>
<body>
<div class="container">{body}</div>
</body>
</html>"""
