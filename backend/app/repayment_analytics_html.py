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
        按信托产品汇总还款流量（周/月/年）与存量；发行资产按<strong>托管编号</strong>统计，
        已还清/未还清按监控<strong>资产主编号（左12位）</strong>关联，不含已转出资产。
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
        <div class="kpi-grid kpi-grid-baseline-1" id="baseline-row-1"></div>
        <div class="kpi-grid kpi-grid-baseline-2" id="baseline-row-2"></div>
        <h3 class="subsection-h">资产监控数据</h3>
        <div class="kpi-grid kpi-grid-monitor" id="monitor-row"></div>
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
                        <th class="col-num">已还款金额累计</th>
                        <th class="col-num">剩余还款金额</th>
                        <th class="col-num">未还清资产数</th>
                        <th class="col-num">还款资产占比</th>
                        <th class="col-num">还款金额占比</th>
                        <th class="col-num">累计还款占比</th>
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

    let issueDateItems = [];

    async function loadIssueDates(pid) {{
        const sel = document.getElementById('issue_date');
        sel.innerHTML = '<option value="">自动（最新发行日）</option>';
        issueDateItems = [];
        if (!pid) return;
        const res = await fetch('/assetinfo/asset-stats/issue-dates?trust_product_id=' + pid, {{ credentials: 'same-origin' }});
        if (!res.ok) return;
        const data = await res.json();
        if (data.all) {{
            const allOpt = document.createElement('option');
            allOpt.value = 'all';
            allOpt.textContent = data.all.label;
            sel.appendChild(allOpt);
        }}
        issueDateItems = data.items || [];
        issueDateItems.forEach(item => {{
            const opt = document.createElement('option');
            opt.value = item.issue_date;
            opt.textContent = item.label;
            sel.appendChild(opt);
        }});
        if (initialIssueDate) sel.value = initialIssueDate;
    }}

    function issueDateForCities() {{
        const sel = document.getElementById('issue_date');
        const val = sel.value;
        if (val === 'all') return 'all';
        if (val) return val;
        return issueDateItems[0]?.issue_date || null;
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
            tbody.innerHTML = '<tr><td colspan="9" class="muted">所选区间无还款记录</td></tr>';
            return;
        }}
        periods.forEach(row => {{
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${{row.period_label}}</td>
                <td class="col-num">${{fmtInt(row.repaid_asset_count)}}</td>
                <td class="col-num">${{fmtNum(row.repayment_amount)}}</td>
                <td class="col-num">${{fmtNum(row.cumulative_repayment)}}</td>
                <td class="col-num">${{fmtNum(row.remaining_repayment)}}</td>
                <td class="col-num">${{fmtInt(row.unpaid_asset_count)}}</td>
                <td class="col-num">${{fmtRatio(row.repaid_asset_ratio)}}</td>
                <td class="col-num">${{fmtRatio(row.repayment_amount_ratio)}}</td>
                <td class="col-num">${{fmtRatio(row.cumulative_repayment_ratio)}}</td>`;
            tbody.appendChild(tr);
        }});
    }}

    function kpiCard(label, value, kind, fullLabel) {{
        const tip = fullLabel ? ` title="${{fullLabel}}"` : '';
        return `<div class="kpi kpi-${{kind}}"><span class="kpi-label"${{tip}}>${{label}}</span><strong>${{value}}</strong></div>`;
    }}

    function renderMinIdentityFormula(base) {{
        const derived = Number(base.min_transferable_total || 0)
            - Number(base.transferred_min_transferable_total || 0)
            - Number(base.pre_transfer_repaid_total || 0);
        const active = Number(base.active_min_transferable_total || 0);
        const ok = Math.abs(derived - active) < 0.02;
        const mark = ok ? '✓' : '⚠';
        const cls = ok ? 'kpi-formula' : 'kpi-formula kpi-formula-warn';
        return `<div class="${{cls}}">`
            + '<span class="kpi-formula-eq">=</span> '
            + '<span class="kpi-formula-part">MIN可转让金额合计</span> '
            + '<span class="kpi-formula-op">−</span> '
            + '<span class="kpi-formula-part">MIN可转让（转出）</span> '
            + '<span class="kpi-formula-op">−</span> '
            + '<span class="kpi-formula-part">转出前已还款</span> '
            + '<span class="kpi-formula-arrow">→</span> '
            + `<strong>${{fmtNum(base.active_min_transferable_total)}}</strong> `
            + `<span class="kpi-formula-mark">${{mark}}</span>`
            + '</div>';
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
        const mon = data.monitor_summary || {{}};
        const baseCard = document.getElementById('baseline-card');
        if (base) {{
            baseCard.style.display = 'block';
            document.getElementById('baseline-row-1').innerHTML = `
                ${{kpiCard('发行基准日', base.issue_date, 'date')}}
                ${{kpiCard('发行资产数', fmtInt(base.issued_asset_count), 'count')}}
                ${{kpiCard('已转出资产数', fmtInt(base.transferred_out_count), 'count')}}
                ${{kpiCard('MIN可转让金额合计', fmtNum(base.min_transferable_total), 'amount')}}
                ${{kpiCard('MIN可转让（转出）', fmtNum(base.transferred_min_transferable_total), 'amount', 'MIN金融机构可转让（转出金额）')}}
                ${{kpiCard('转出前已还款', fmtNum(base.pre_transfer_repaid_total), 'amount', '转出前已还款金额')}}
                ${{kpiCard('应收账款合计', fmtNum(base.receivable_transfer_total), 'amount', '应收账款转让价款合计')}}
                ${{kpiCard('应收账款（转出）', fmtNum(base.transferred_receivable_transfer_total), 'amount', '应收账款转让价款（转出金额）')}}
                ${{kpiCard('应收账款（未转出）', fmtNum(base.active_receivable_transfer_total), 'amount', '应收账款转让价款合计（未转出）')}}`;
            document.getElementById('baseline-row-2').innerHTML = `
                ${{kpiCard('有效资产数', fmtInt(base.effective_asset_count), 'count')}}
                ${{kpiCard('已还清', fmtInt(base.paid_off_count), 'count', '已还清资产数')}}
                ${{kpiCard('未还清', fmtInt(base.unpaid_count), 'count', '未还清资产数')}}
                ${{kpiCard('MIN可转让（未转出）', fmtNum(base.active_min_transferable_total), 'amount', 'MIN可转让金额合计（未转出）')}}
                ${{renderMinIdentityFormula(base)}}`;
            document.getElementById('monitor-row').innerHTML = `
                ${{kpiCard('监控资产数', fmtInt(mon.monitor_asset_count), 'count')}}
                ${{kpiCard('已还清', fmtInt(mon.paid_off_count), 'count', '已还清资产数')}}
                ${{kpiCard('未还清', fmtInt(mon.unpaid_count), 'count', '未还清资产数')}}
                ${{kpiCard('初始受让金额', fmtNum(mon.initial_transfer_total), 'amount')}}
                ${{kpiCard('已还款金额', fmtNum(mon.repaid_total), 'amount')}}
                ${{kpiCard('剩余还款金额', fmtNum(mon.remaining_total), 'amount')}}`;
            const snap = mon.monitor_snapshot_date || '—';
            document.getElementById('monitor-footnote').textContent =
                '有效资产数 = 发行资产数 − 已转出资产数。转出 MIN/应收账款取自转入目标产品发行表。'
                + '已还清/未还清截至监控快照日：' + snap
                + '；不含已转出资产。周期表累计还款占比分母为初始受让金额。';
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
                const bm = block.monitor_summary || {{}};
                wrap.innerHTML = `<h3>${{block.city}}</h3>
                    <p class="muted">发行 ${{fmtInt(b.issued_asset_count)}} · 已转出 ${{fmtInt(b.transferred_out_count)}} · MIN（未转出） ${{fmtNum(b.active_min_transferable_total)}} · 初始受让 ${{fmtNum(bm.initial_transfer_total)}}</p>`;
                const table = document.createElement('table');
                table.className = 'records-table';
                table.innerHTML = `<thead><tr>
                    <th>周期</th><th class="col-num">还款资产数</th><th class="col-num">还款金额</th>
                    <th class="col-num">已还款累计</th><th class="col-num">剩余还款</th>
                    <th class="col-num">未还清</th><th class="col-num">资产占比</th><th class="col-num">金额占比</th><th class="col-num">累计还款占比</th>
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
        await loadCities(pid, issueDateForCities());
    }});
    document.getElementById('issue_date').addEventListener('change', async function() {{
        const pid = document.getElementById('trust_product_id').value;
        await loadCities(pid, issueDateForCities());
    }});

    (async function init() {{
        if (initialProductId) {{
            await loadIssueDates(initialProductId);
            await loadCities(initialProductId, issueDateForCities());
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
        h3.subsection-h {{ font-size: 0.95rem; color: #cbd5e1; margin: 1.25rem 0 0.75rem; }}
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
            gap: 0.75rem;
        }}
        .kpi-grid-baseline-1 {{
            grid-template-columns: 72px repeat(2, 68px) repeat(6, minmax(112px, 1fr));
            margin-bottom: 0.75rem;
        }}
        .kpi-grid-baseline-2 {{
            grid-template-columns: repeat(3, 68px) minmax(112px, 0.95fr) minmax(180px, 2fr);
            margin-bottom: 0.75rem;
            align-items: stretch;
        }}
        .kpi-grid-monitor {{
            grid-template-columns: repeat(3, 68px) repeat(3, minmax(112px, 1fr));
            margin-bottom: 0.75rem;
        }}
        @media (max-width: 1280px) {{
            .kpi-grid-baseline-1 {{
                grid-template-columns: 72px repeat(2, 68px) repeat(3, minmax(108px, 1fr));
            }}
            .kpi-grid-baseline-2 {{
                grid-template-columns: repeat(4, minmax(68px, 0.7fr));
            }}
            .kpi-formula {{
                grid-column: 1 / -1;
            }}
            .kpi-grid-monitor {{
                grid-template-columns: repeat(3, 68px) repeat(3, minmax(100px, 1fr));
            }}
        }}
        @media (max-width: 960px) {{
            .kpi-grid-baseline-1,
            .kpi-grid-baseline-2,
            .kpi-grid-monitor {{
                grid-template-columns: repeat(3, minmax(0, 1fr));
            }}
            .kpi-formula {{
                grid-column: 1 / -1;
            }}
        }}
        .kpi {{
            background: rgba(15,23,42,0.5);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            padding: 0.75rem;
            min-width: 0;
        }}
        .kpi-count {{
            padding: 0.75rem 0.5rem;
            text-align: center;
        }}
        .kpi-count .kpi-label {{
            font-size: 0.72rem;
            white-space: nowrap;
        }}
        .kpi-count strong {{
            font-size: 1.15rem;
        }}
        .kpi-date {{
            padding: 0.75rem 0.5rem;
            text-align: center;
        }}
        .kpi-date .kpi-label {{
            font-size: 0.72rem;
            white-space: nowrap;
        }}
        .kpi-amount .kpi-label {{
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            font-size: 0.74rem;
        }}
        .kpi-formula {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.35rem 0.5rem;
            padding: 0.75rem 1rem;
            background: rgba(15,23,42,0.35);
            border: 1px dashed rgba(255,255,255,0.12);
            border-radius: 8px;
            font-size: 0.78rem;
            color: #94a3b8;
            min-width: 0;
        }}
        .kpi-formula-warn {{
            border-color: rgba(251,191,36,0.45);
            color: #fde68a;
        }}
        .kpi-formula-eq,
        .kpi-formula-op,
        .kpi-formula-arrow {{
            color: #64748b;
        }}
        .kpi-formula-part {{
            white-space: nowrap;
        }}
        .kpi-formula strong {{
            color: #f1f5f9;
            font-size: 0.95rem;
        }}
        .kpi-formula-mark {{
            color: #4ade80;
            font-weight: 600;
        }}
        .kpi-formula-warn .kpi-formula-mark {{
            color: #fbbf24;
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
