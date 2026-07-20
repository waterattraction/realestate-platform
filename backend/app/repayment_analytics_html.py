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
        <div class="stats-overview" id="stats-overview"></div>
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

    function checkOk(a, b) {{
        return Math.abs(Number(a || 0) - Number(b || 0)) < 0.02;
    }}

    function bucket(mon, name) {{
        const b = (mon.by_bucket || {{}})[name];
        return b || {{ asset_count: 0, initial_transfer_total: 0, repaid_total: 0, remaining_total: 0 }};
    }}

    function unpaidMetric(mon, field) {{
        return Number(bucket(mon, 'current')[field] || 0)
            + Number(bucket(mon, 'overdue')[field] || 0)
            + Number(bucket(mon, 'no_monitor')[field] || 0);
    }}

    let lockedCheckId = null;

    function setActiveChecks(ids, locked) {{
        const overview = document.getElementById('stats-overview');
        if (!overview) return;
        const active = (ids || []).filter(Boolean);
        overview.classList.toggle('check-highlight-on', active.length > 0);
        overview.classList.toggle('check-locked', !!locked);
        const anyFailed = active.some(id => {{
            const line = overview.querySelector('.check-line[data-check-id="' + id + '"]');
            return line && line.classList.contains('check-warn');
        }});
        const tone = anyFailed ? 'warn' : 'ok';
        overview.querySelectorAll('[data-check-cells]').forEach(el => {{
            el.classList.remove(
                'check-cell-active', 'check-cell-dim', 'check-cell-ok', 'check-cell-warn'
            );
            if (!active.length) return;
            const cellChecks = (el.dataset.checkCells || '').split(/\\s+/).filter(Boolean);
            const matched = active.filter(id => cellChecks.includes(id));
            if (matched.length) {{
                el.classList.add('check-cell-active', 'check-cell-' + tone);
            }} else {{
                el.classList.add('check-cell-dim');
            }}
        }});
        overview.querySelectorAll('.check-line[data-check-id]').forEach(line => {{
            const on = active.includes(line.dataset.checkId);
            line.classList.toggle('check-line-active', on);
            line.classList.toggle('check-line-dim', active.length > 0 && !on);
            line.classList.toggle('check-line-locked', !!locked && on);
        }});
    }}

    function clearActiveCheck() {{
        lockedCheckId = null;
        setActiveChecks([], false);
    }}

    function bindCheckLinking() {{
        const card = document.getElementById('baseline-card');
        if (!card || card.dataset.checkLinkBound) return;
        card.dataset.checkLinkBound = '1';

        card.addEventListener('click', (e) => {{
            const line = e.target.closest('.check-line[data-check-id]');
            if (line) {{
                e.preventDefault();
                const id = line.dataset.checkId;
                if (lockedCheckId === id) {{
                    clearActiveCheck();
                }} else {{
                    lockedCheckId = id;
                    setActiveChecks([id], true);
                }}
                return;
            }}
            if (lockedCheckId && !e.target.closest('[data-check-cells]')) {{
                clearActiveCheck();
            }}
        }});

        card.addEventListener('mouseover', (e) => {{
            if (lockedCheckId) return;
            const line = e.target.closest('.check-line[data-check-id]');
            if (line) {{
                setActiveChecks([line.dataset.checkId], false);
                return;
            }}
            const cell = e.target.closest('[data-check-cells]');
            if (cell) {{
                const ids = (cell.dataset.checkCells || '').split(/\\s+/).filter(Boolean);
                setActiveChecks(ids, false);
            }}
        }});

        card.addEventListener('mouseout', (e) => {{
            if (lockedCheckId) return;
            const to = e.relatedTarget;
            if (to && card.contains(to) && (to.closest('[data-check-cells]') || to.closest('.check-line[data-check-id]'))) {{
                return;
            }}
            setActiveChecks([], false);
        }});

        card.addEventListener('keydown', (e) => {{
            const line = e.target.closest('.check-line[data-check-id]');
            if (!line) return;
            if (e.key === 'Enter' || e.key === ' ') {{
                e.preventDefault();
                line.click();
            }}
        }});

        document.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape' && lockedCheckId) clearActiveCheck();
        }});
    }}

    function fieldTag(label) {{
        return `<span class="field-tag">${{label}}</span>`;
    }}

    function renderCheckLineHtml(html, ok, checkId) {{
        const cls = ok ? 'check-ok' : 'check-warn';
        const mark = ok ? '✓' : '⚠';
        return `<div class="check-line ${{cls}}" data-check-id="${{checkId}}" role="button" tabindex="0" title="悬停或点击高亮源数据">`
            + `${{html}} <span class="check-mark">${{mark}}</span></div>`;
    }}

    function renderTransferCheck(base) {{
        const outCount = Number(base.transferred_out_count || 0);
        const destCount = Number(base.transferred_out_dest_count || 0);
        const ok = outCount === destCount;
        const html = `${{fieldTag('资产数（已转出）')}} = ${{fieldTag('资产数（已在其他产品发行）')}}`
            + ` <span class="check-values">(${{fmtInt(outCount)}} = ${{fmtInt(destCount)}})</span>`;
        return renderCheckLineHtml(html, ok, 'c4');
    }}

    function renderMonitorMeta(base) {{
        const destCount = Number(base.transferred_out_dest_count || 0);
        return `<div class="stats-meta-item">
                <span class="stats-meta-label">资产数（已在其他产品发行）</span>
                <span class="stats-meta-value" data-check-cells="c4">${{fmtInt(destCount)}}</span>
            </div>
            <div class="stats-meta-item">
                <span class="stats-meta-label">还款金额（转出前）</span>
                <span class="stats-meta-value" data-check-cells="c1">${{fmtNum(base.pre_transfer_repaid_total)}}</span>
            </div>`;
    }}

    function renderIssuanceMatrix(base, mon) {{
        const minOk = checkOk(
            Number(base.min_transferable_total || 0)
                - Number(base.transferred_min_transferable_total || 0)
                - Number(base.active_min_transferable_total || 0),
            base.pre_transfer_repaid_total
        );
        const countOk = checkOk(base.effective_asset_count, mon.monitor_asset_count);
        const minRetainOk = checkOk(base.active_min_transferable_total, mon.initial_transfer_total);
        const checks = renderCheckLineHtml(
            `${{fieldTag('MIN（发行）')}} − ${{fieldTag('MIN（已转出）')}} − ${{fieldTag('MIN（留存）')}} = ${{fieldTag('还款金额（转出前）')}}`,
            minOk,
            'c1'
        ) + renderCheckLineHtml(
            `${{fieldTag('资产数（留存）')}} = ${{fieldTag('资产数（监控合计）')}}`,
            countOk,
            'c2'
        ) + renderCheckLineHtml(
            `${{fieldTag('MIN（留存）')}} = ${{fieldTag('初始受让金额')}}`,
            minRetainOk,
            'c3'
        ) + renderTransferCheck(base);
        return `<div class="stats-panel">
            <div class="stats-panel-title">发行基准</div>
            <div class="stats-panel-date">发行日期：${{base.issue_date || '—'}}</div>
            <div class="stats-panel-scroll">
            <table class="stats-matrix">
                <thead>
                    <tr>
                        <th class="row-label">指标</th>
                        <th class="col-num">发行（全量）</th>
                        <th class="col-num">已转出</th>
                        <th class="col-num">留存</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <th class="row-label">资产数</th>
                        <td class="col-num">${{fmtInt(base.issued_asset_count)}}</td>
                        <td class="col-num" data-check-cells="c4">${{fmtInt(base.transferred_out_count)}}</td>
                        <td class="col-num" data-check-cells="c2">${{fmtInt(base.effective_asset_count)}}</td>
                    </tr>
                    <tr>
                        <th class="row-label">MIN可转让金额</th>
                        <td class="col-num" data-check-cells="c1">${{fmtNum(base.min_transferable_total)}}</td>
                        <td class="col-num" data-check-cells="c1">${{fmtNum(base.transferred_min_transferable_total)}}</td>
                        <td class="col-num" data-check-cells="c1 c3">${{fmtNum(base.active_min_transferable_total)}}</td>
                    </tr>
                    <tr>
                        <th class="row-label">应收账款转让金额</th>
                        <td class="col-num">${{fmtNum(base.receivable_transfer_total)}}</td>
                        <td class="col-num">${{fmtNum(base.transferred_receivable_transfer_total)}}</td>
                        <td class="col-num">${{fmtNum(base.active_receivable_transfer_total)}}</td>
                    </tr>
                </tbody>
            </table>
            </div>
            <div class="stats-checks">
                <div class="stats-checks-hint">悬停或点击检查公式高亮源数据；再次点击或 Esc 取消锁定</div>
                ${{checks}}
            </div>
        </div>`;
    }}

    function renderMonitorMatrix(base, mon) {{
        const paid = bucket(mon, 'paid_off');
        const current = bucket(mon, 'current');
        const overdue = bucket(mon, 'overdue');
        const snap = mon.monitor_snapshot_date || '—';
        return `<div class="stats-panel">
            <div class="stats-panel-title">资产监控</div>
            <div class="stats-panel-date">资产监控日期：${{snap}}</div>
            <div class="stats-meta-bar">
                ${{renderMonitorMeta(base)}}
            </div>
            <div class="stats-panel-scroll">
            <table class="stats-matrix">
                <thead>
                    <tr>
                        <th class="row-label">指标</th>
                        <th class="col-num">合计</th>
                        <th class="col-num">已还清</th>
                        <th class="col-num">未还清</th>
                        <th class="col-num">正常</th>
                        <th class="col-num">未付款</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <th class="row-label">资产数</th>
                        <td class="col-num" data-check-cells="c2">${{fmtInt(mon.monitor_asset_count)}}</td>
                        <td class="col-num">${{fmtInt(paid.asset_count)}}</td>
                        <td class="col-num">${{fmtInt(mon.unpaid_count)}}</td>
                        <td class="col-num">${{fmtInt(mon.current_count)}}</td>
                        <td class="col-num">${{fmtInt(mon.overdue_count)}}</td>
                    </tr>
                    <tr>
                        <th class="row-label">初始受让金额</th>
                        <td class="col-num" data-check-cells="c3">${{fmtNum(mon.initial_transfer_total)}}</td>
                        <td class="col-num">${{fmtNum(paid.initial_transfer_total)}}</td>
                        <td class="col-num">${{fmtNum(unpaidMetric(mon, 'initial_transfer_total'))}}</td>
                        <td class="col-num">${{fmtNum(current.initial_transfer_total)}}</td>
                        <td class="col-num">${{fmtNum(overdue.initial_transfer_total)}}</td>
                    </tr>
                    <tr>
                        <th class="row-label">还款金额</th>
                        <td class="col-num">${{fmtNum(mon.repaid_total)}}</td>
                        <td class="col-num">${{fmtNum(paid.repaid_total)}}</td>
                        <td class="col-num">${{fmtNum(unpaidMetric(mon, 'repaid_total'))}}</td>
                        <td class="col-num">${{fmtNum(current.repaid_total)}}</td>
                        <td class="col-num">${{fmtNum(overdue.repaid_total)}}</td>
                    </tr>
                    <tr>
                        <th class="row-label">剩余还款金额</th>
                        <td class="col-num">${{fmtNum(mon.remaining_total)}}</td>
                        <td class="col-num">${{fmtNum(paid.remaining_total)}}</td>
                        <td class="col-num">${{fmtNum(unpaidMetric(mon, 'remaining_total'))}}</td>
                        <td class="col-num">${{fmtNum(current.remaining_total)}}</td>
                        <td class="col-num">${{fmtNum(overdue.remaining_total)}}</td>
                    </tr>
                </tbody>
            </table>
            </div>
        </div>`;
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
            clearActiveCheck();
            baseCard.style.display = 'block';
            document.getElementById('stats-overview').innerHTML =
                renderIssuanceMatrix(base, mon) + renderMonitorMatrix(base, mon);
            const snap = mon.monitor_snapshot_date || '—';
            document.getElementById('monitor-footnote').textContent =
                '留存资产数 = 发行资产数 − 已转出资产数。转出 MIN/应收账款转让金额取自转入目标产品发行表。'
                + '正常：逾期天数 ≤ 0（M0）；逾期：逾期天数 > 0（M0+）。'
                + '已还清/未还清/未付款细分截至监控快照日：' + snap
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
                    <p class="muted">发行 ${{fmtInt(b.issued_asset_count)}} · 已转出 ${{fmtInt(b.transferred_out_count)}} · MIN（留存） ${{fmtNum(b.active_min_transferable_total)}} · 初始受让 ${{fmtNum(bm.initial_transfer_total)}}</p>`;
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
        bindCheckLinking();
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
        .stats-overview {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
            align-items: start;
        }}
        @media (max-width: 1100px) {{
            .stats-overview {{ grid-template-columns: 1fr; }}
        }}
        .stats-panel {{
            background: rgba(15,23,42,0.35);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px;
            padding: 0.85rem;
            min-width: 0;
            overflow: hidden;
        }}
        .stats-panel-scroll {{
            overflow-x: auto;
            margin-bottom: 0.5rem;
        }}
        .stats-meta-bar {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem 1.25rem;
            margin-bottom: 0.65rem;
            padding: 0.55rem 0.65rem;
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 6px;
        }}
        .stats-meta-item {{
            display: flex;
            flex-wrap: wrap;
            align-items: baseline;
            gap: 0.35rem 0.5rem;
            min-width: 0;
        }}
        .stats-meta-label {{
            color: #94a3b8;
            font-size: 0.74rem;
            white-space: nowrap;
        }}
        .stats-meta-value {{
            color: #f1f5f9;
            font-size: 0.82rem;
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }}
        .stats-panel-title {{
            font-size: 1rem;
            font-weight: 600;
            color: #e2e8f0;
            margin-bottom: 0.25rem;
        }}
        .stats-panel-date {{
            font-size: 0.78rem;
            color: #94a3b8;
            margin-bottom: 0.65rem;
        }}
        .stats-matrix {{
            width: 100%;
            min-width: 420px;
            border-collapse: collapse;
            font-size: 0.78rem;
            table-layout: auto;
        }}
        .stats-matrix th,
        .stats-matrix td {{
            border: 1px solid rgba(255,255,255,0.08);
            padding: 0.45rem 0.55rem;
            vertical-align: middle;
            overflow: hidden;
        }}
        .stats-matrix thead th {{
            background: rgba(255,255,255,0.04);
            color: #94a3b8;
            font-weight: 500;
            text-align: center;
            white-space: nowrap;
        }}
        .stats-matrix .row-label {{
            color: #94a3b8;
            font-weight: 500;
            text-align: left;
            white-space: nowrap;
            background: rgba(255,255,255,0.02);
            min-width: 88px;
            max-width: 120px;
        }}
        .stats-matrix .col-num {{
            text-align: right;
            color: #f1f5f9;
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
            min-width: 72px;
        }}
        .stats-checks {{
            margin-top: 0.65rem;
            padding: 0.55rem 0.65rem;
            background: rgba(255,255,255,0.03);
            border: 1px dashed rgba(255,255,255,0.1);
            border-radius: 6px;
            font-size: 0.72rem;
        }}
        .stats-checks-hint {{
            color: #64748b;
            font-size: 0.66rem;
            margin-bottom: 0.45rem;
        }}
        .check-line {{
            margin-bottom: 0.35rem;
            line-height: 1.5;
            word-break: break-word;
            cursor: pointer;
            border-radius: 4px;
            padding: 0.2rem 0.35rem 0.2rem 0.45rem;
            border-left: 3px solid transparent;
            transition: background 0.12s, border-color 0.12s, opacity 0.12s, color 0.12s;
            color: #cbd5e1;
        }}
        .check-line:hover {{
            background: rgba(255,255,255,0.04);
        }}
        .check-line:last-child {{ margin-bottom: 0; }}
        .check-line-active.check-ok {{
            border-left-color: #4ade80;
            background: rgba(74, 222, 128, 0.1);
            color: #bbf7d0;
        }}
        .check-line-active.check-ok .field-tag {{ color: #86efac; }}
        .check-line-active.check-warn {{
            border-left-color: #fb923c;
            background: rgba(251, 146, 60, 0.1);
            color: #fed7aa;
        }}
        .check-line-active.check-warn .field-tag {{ color: #fdba74; }}
        .check-line-locked {{
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.12);
        }}
        .check-line-dim {{ opacity: 0.42; }}
        .check-info {{ color: #94a3b8; }}
        .check-info .check-hint {{ color: #64748b; font-size: 0.68rem; }}
        .check-values {{ color: inherit; font-variant-numeric: tabular-nums; opacity: 0.85; }}
        .check-line .check-mark {{ color: #64748b; font-weight: 600; }}
        .check-line-active.check-ok .check-mark {{ color: #4ade80; }}
        .check-line-active.check-warn .check-mark {{ color: #fb923c; }}
        #stats-overview.check-highlight-on [data-check-cells] {{
            transition: opacity 0.12s, background 0.12s, box-shadow 0.12s, color 0.12s;
        }}
        .check-cell-dim {{ opacity: 0.28; }}
        .check-cell-active {{
            opacity: 1;
            font-weight: 600;
            border-radius: 4px;
        }}
        .stats-matrix .check-cell-active {{ padding: 0.45rem 0.55rem; }}
        .stats-meta-value.check-cell-active {{
            padding: 0.12rem 0.4rem;
            border-radius: 4px;
        }}
        .check-cell-ok {{
            background: rgba(74, 222, 128, 0.18);
            box-shadow: inset 0 0 0 2px rgba(74, 222, 128, 0.5);
            color: #bbf7d0;
        }}
        .check-cell-warn {{
            background: rgba(251, 146, 60, 0.18);
            box-shadow: inset 0 0 0 2px rgba(251, 146, 60, 0.55);
            color: #fed7aa;
        }}
        .field-tag {{
            display: inline;
            font-weight: 500;
            white-space: nowrap;
            color: inherit;
        }}
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
