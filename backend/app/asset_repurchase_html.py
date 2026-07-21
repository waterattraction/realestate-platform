"""资产回购页面 — 选资产 → 选回购单位 → 预览监控 → 确认回购。"""

from __future__ import annotations

from html import escape

from app.ui_css import (
    BTN_CSS,
    FORM_FIELD_CSS,
    PAGE_CHROME_CSS,
    STANDARD_HEADER_CSS,
    TABLE_SCROLL_CSS,
)


def render_repurchase_page(products: list[dict], *, username: str = "") -> str:
    product_options = '<option value="">请选择信托产品</option>'
    for p in products:
        product_options += (
            f'<option value="{int(p["id"])}">{escape(str(p["name"]))}</option>'
        )
    _ = username

    body = f"""
    <div class="container">
    <nav class="breadcrumb"><a href="/">首页</a> / 资产回购</nav>
    <h1>资产回购</h1>
    <p class="muted">选择资产与回购单位后先预览再确认。确认回购仅写入回购新表，不修改资产监控导入表、发行表与还款表。回购金额默认等于监控剩余金额，确认前可修改。回购单可失效；若回购后该信托产品已有新的资产监控表导入，则不可失效。</p>

    <div class="rp-grid">
        <div class="card panel">
            <h2>1 · 选择资产（按资产主编号）</h2>
            <div class="rp-toolbar">
                <div class="rp-field">
                    <label for="rp-product">信托产品</label>
                    <select id="rp-product">{product_options}</select>
                </div>
                <div class="rp-field rp-field-grow">
                    <label for="rp-asset-filter">筛选（编号 / 城市 / M级 / 状态）</label>
                    <input type="text" id="rp-asset-filter" class="rp-input" placeholder="输入关键字过滤" disabled>
                </div>
            </div>
            <div id="rp-asset-summary" class="stat-chips"></div>
            <div id="rp-asset-error" class="form-error" style="display:none"></div>
            <div id="rp-asset-loading" class="muted" style="display:none">加载中…</div>
            <div id="rp-asset-table-wrap" class="rp-table-scroll" style="display:none"></div>
            <div id="rp-asset-empty" class="muted" style="display:none">该产品暂无最新监控资产</div>
        </div>

        <div class="card panel">
            <h2>2 · 回购单位</h2>
            <div class="rp-field">
                <label for="rp-unit">回购单位（仅启用中）</label>
                <select id="rp-unit"><option value="">请选择回购单位</option></select>
            </div>
            <div id="rp-unit-info" class="muted rp-unit-info"></div>

            <div class="rp-unit-manage">
                <div class="rp-unit-manage-head">
                    <h3>单位管理</h3>
                    <button type="button" class="btn-ghost btn-sm" id="rp-unit-add-btn">+ 新增单位</button>
                </div>
                <div id="rp-unit-form" class="rp-unit-form" style="display:none">
                    <input type="hidden" id="rp-unit-form-id" value="">
                    <div class="rp-field"><label>公司名称</label>
                        <input type="text" id="rp-unit-company" class="rp-input" placeholder="公司名称（唯一）"></div>
                    <div class="rp-field"><label>联系人</label>
                        <input type="text" id="rp-unit-contact" class="rp-input" placeholder="联系人"></div>
                    <div class="rp-field"><label>邮箱</label>
                        <input type="email" id="rp-unit-email" class="rp-input" placeholder="name@example.com"></div>
                    <div class="rp-field" id="rp-unit-status-field" style="display:none"><label>状态</label>
                        <select id="rp-unit-status">
                            <option value="active">启用</option>
                            <option value="inactive">停用</option>
                        </select></div>
                    <div id="rp-unit-form-error" class="form-error" style="display:none"></div>
                    <div class="rp-unit-form-actions">
                        <button type="button" class="btn-primary btn-sm" id="rp-unit-save-btn">保存</button>
                        <button type="button" class="btn-ghost btn-sm" id="rp-unit-cancel-btn">取消</button>
                    </div>
                </div>
                <div id="rp-unit-table-wrap"></div>
            </div>
        </div>
    </div>

    <div class="card">
        <h2>3 · 预览与确认</h2>
        <div class="rp-execute-form">
            <div class="rp-execute-fields">
                <div class="rp-field">
                    <label for="rp-biz-date">回购业务日</label>
                    <input type="date" id="rp-biz-date" class="rp-input">
                </div>
                <div class="rp-field rp-field-grow">
                    <label for="rp-note">备注（可选）</label>
                    <input type="text" id="rp-note" class="rp-input" placeholder="回购说明">
                </div>
            </div>
            <div class="rp-execute-actions">
                <button type="button" class="btn-secondary" id="rp-preview-btn" disabled>预览回购</button>
                <button type="button" class="btn-primary" id="rp-confirm-btn" disabled>确认回购</button>
            </div>
        </div>
        <div id="rp-preview-error" class="form-error" style="display:none"></div>
        <div id="rp-preview-result" class="rp-preview-result" style="display:none"></div>
        <div id="rp-execute-status" class="rp-execute-status" style="display:none"></div>
    </div>

    <div class="card">
        <h2>回购记录</h2>
        <div id="rp-orders-loading" class="muted">加载中…</div>
        <div id="rp-orders-table-wrap" class="rp-table-scroll" style="display:none"></div>
        <div id="rp-orders-empty" class="muted" style="display:none">暂无回购记录</div>
        <div id="rp-order-detail" class="rp-order-detail" style="display:none">
            <div class="rp-order-detail-head">
                <h3 id="rp-order-detail-title">回购单详情</h3>
                <button type="button" class="btn-ghost btn-sm" id="rp-order-detail-close">关闭</button>
            </div>
            <div id="rp-order-detail-body"></div>
        </div>
    </div>
    </div>

    <script>
    const STATUS_LABELS = {{ completed: '已完成', voided: '已失效' }};
    const UNIT_STATUS_LABELS = {{ active: '启用', inactive: '停用' }};

    let assetItems = [];
    let selectedCodes = new Set();
    let amountOverrides = {{}};
    let units = [];
    let previewData = null;
    let previewKey = '';

    const el = (id) => document.getElementById(id);
    const esc = (s) => String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    const money = (v) => {{
        if (v == null || v === '') return '—';
        return Number(v).toLocaleString('zh-CN', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
    }};
    const monitorValue = (column, value) => {{
        if (value == null || value === '') return '—';
        if (column.format === 'money') return money(value);
        if (column.format === 'rate') {{
            const number = Number(value);
            return Number.isFinite(number)
                ? (number * 100).toLocaleString('zh-CN', {{ maximumFractionDigits: 4 }}) + '%'
                : String(value);
        }}
        if (typeof value === 'boolean') return value ? '是' : '否';
        return String(value).replace('T', ' ');
    }};

    function showError(id, msg) {{
        const box = el(id);
        if (!box) return;
        if (msg) {{ box.textContent = msg; box.style.display = ''; }}
        else {{ box.textContent = ''; box.style.display = 'none'; }}
    }}

    async function fetchJson(url, options) {{
        const res = await fetch(url, Object.assign({{ credentials: 'same-origin' }}, options || {{}}));
        const text = await res.text();
        let data = {{}};
        if (text) {{
            try {{ data = JSON.parse(text); }} catch (e) {{ data = {{ detail: text }}; }}
        }}
        if (!res.ok) {{
            let msg = data.detail;
            if (Array.isArray(msg)) msg = msg.map(d => d.msg || JSON.stringify(d)).join('; ');
            throw new Error(msg || ('请求失败（' + res.status + '）'));
        }}
        return data;
    }}

    // ── 预览指纹：任何输入变化即失效 ─────────────────────
    function currentKey() {{
        const codes = Array.from(selectedCodes).sort();
        const amounts = codes.map(c => c + '=' + (amountOverrides[c] != null ? amountOverrides[c] : ''));
        return [el('rp-product').value, el('rp-unit').value, el('rp-biz-date').value,
                codes.join('|'), amounts.join('|')].join('##');
    }}

    function invalidatePreview() {{
        previewData = null;
        previewKey = '';
        el('rp-confirm-btn').disabled = true;
        el('rp-preview-btn').disabled = !(el('rp-product').value && el('rp-unit').value && selectedCodes.size > 0);
        const box = el('rp-preview-result');
        if (box.style.display !== 'none' && box.dataset.stale !== '1') {{
            box.dataset.stale = '1';
            const tip = document.createElement('div');
            tip.className = 'rp-stale-tip';
            tip.textContent = '选择或金额已变更，预览已失效，请重新预览。';
            box.prepend(tip);
        }}
    }}

    // ── 资产列表 ─────────────────────────────────────────
    async function loadAssets() {{
        const pid = el('rp-product').value;
        selectedCodes = new Set();
        amountOverrides = {{}};
        invalidatePreview();
        el('rp-preview-result').style.display = 'none';
        showError('rp-asset-error', '');
        el('rp-asset-table-wrap').style.display = 'none';
        el('rp-asset-empty').style.display = 'none';
        el('rp-asset-summary').innerHTML = '';
        el('rp-asset-filter').disabled = !pid;
        el('rp-asset-filter').value = '';
        if (!pid) return;
        el('rp-asset-loading').style.display = '';
        try {{
            const data = await fetchJson('/asset-repurchase/assets?trust_product_id=' + encodeURIComponent(pid));
            assetItems = data.items || [];
            renderAssetTable();
        }} catch (err) {{
            assetItems = [];
            showError('rp-asset-error', err.message);
        }} finally {{
            el('rp-asset-loading').style.display = 'none';
        }}
    }}

    function assetMatchesFilter(item, kw) {{
        if (!kw) return true;
        const hay = [item.asset_code, item.city, item.delinquency_bucket_display,
                     item.asset_status, item.historical_property_codes].join(' ').toLowerCase();
        return hay.indexOf(kw.toLowerCase()) >= 0;
    }}

    function renderAssetSummary() {{
        let total = 0;
        selectedCodes.forEach(code => {{
            const item = assetItems.find(a => a.asset_code === code);
            if (item) total += Number(item.remaining_amount || 0);
        }});
        el('rp-asset-summary').innerHTML =
            '<span class="chip">资产 <strong>' + assetItems.length + '</strong> 项</span>' +
            '<span class="chip">已选 <strong>' + selectedCodes.size + '</strong> 项</span>' +
            '<span class="chip">已选剩余合计 <strong>¥' + money(total) + '</strong></span>';
    }}

    function renderAssetTable() {{
        const kw = el('rp-asset-filter').value.trim();
        const rows = assetItems.filter(a => assetMatchesFilter(a, kw));
        if (!assetItems.length) {{
            el('rp-asset-empty').style.display = '';
            el('rp-asset-table-wrap').style.display = 'none';
            renderAssetSummary();
            return;
        }}
        let html = '<table class="rp-table"><thead><tr>' +
            '<th class="col-check"></th><th>资产主编号</th><th>城市</th><th>M级 · 逾期</th>' +
            '<th class="col-num">剩余金额</th><th class="col-num">分笔</th><th>数据日期</th><th>状态</th>' +
            '</tr></thead><tbody>';
        rows.forEach(item => {{
            const disabled = item.already_repurchased;
            const checked = selectedCodes.has(item.asset_code);
            html += '<tr class="' + (disabled ? 'row-disabled' : '') + (checked ? ' row-checked' : '') + '">' +
                '<td class="col-check"><input type="checkbox" class="rp-asset-check" value="' + esc(item.asset_code) + '"' +
                    (checked ? ' checked' : '') + (disabled ? ' disabled title="已存在生效回购单"' : '') + '></td>' +
                '<td class="col-code" title="历史房源号：' + esc(item.historical_property_codes || '—') + '">' + esc(item.asset_code) + '</td>' +
                '<td>' + esc(item.city) + '</td>' +
                '<td>' + esc(item.delinquency_bucket_display) + '</td>' +
                '<td class="col-num">' + money(item.remaining_amount) + '</td>' +
                '<td class="col-num">' + esc(item.split_count) + '</td>' +
                '<td>' + esc(item.monitor_data_date || '—') + '</td>' +
                '<td>' + (disabled ? '<span class="status-badge status-voided">已回购</span>' : esc(item.asset_status || '—')) + '</td>' +
                '</tr>';
        }});
        html += '</tbody></table>';
        el('rp-asset-table-wrap').innerHTML = html;
        el('rp-asset-table-wrap').style.display = '';
        el('rp-asset-empty').style.display = 'none';
        el('rp-asset-table-wrap').querySelectorAll('.rp-asset-check').forEach(box => {{
            box.addEventListener('change', () => {{
                if (box.checked) selectedCodes.add(box.value);
                else {{ selectedCodes.delete(box.value); delete amountOverrides[box.value]; }}
                renderAssetSummary();
                invalidatePreview();
            }});
        }});
        renderAssetSummary();
    }}

    // ── 回购单位 ─────────────────────────────────────────
    function renderUnitSelect() {{
        const sel = el('rp-unit');
        const prev = sel.value;
        let html = '<option value="">请选择回购单位</option>';
        units.filter(u => u.status === 'active').forEach(u => {{
            html += '<option value="' + u.id + '">' + esc(u.company_name) + '</option>';
        }});
        sel.innerHTML = html;
        if (prev && units.some(u => String(u.id) === prev && u.status === 'active')) sel.value = prev;
        renderUnitInfo();
    }}

    function renderUnitInfo() {{
        const id = el('rp-unit').value;
        const u = units.find(x => String(x.id) === id);
        el('rp-unit-info').textContent = u
            ? ('联系人：' + u.contact_name + ' · 邮箱：' + u.contact_email)
            : '';
    }}

    function renderUnitTable() {{
        if (!units.length) {{
            el('rp-unit-table-wrap').innerHTML = '<div class="muted">暂无回购单位，请先新增</div>';
            return;
        }}
        let html = '<table class="rp-table rp-table-units"><thead><tr>' +
            '<th>公司</th><th>联系人</th><th>邮箱</th><th>状态</th><th></th></tr></thead><tbody>';
        units.forEach(u => {{
            html += '<tr>' +
                '<td>' + esc(u.company_name) + '</td>' +
                '<td>' + esc(u.contact_name) + '</td>' +
                '<td>' + esc(u.contact_email) + '</td>' +
                '<td><span class="status-badge ' + (u.status === 'active' ? 'status-completed' : 'status-voided') + '">' +
                    (UNIT_STATUS_LABELS[u.status] || u.status) + '</span></td>' +
                '<td><button type="button" class="btn-ghost btn-sm rp-unit-edit" data-id="' + u.id + '">编辑</button></td>' +
                '</tr>';
        }});
        html += '</tbody></table>';
        el('rp-unit-table-wrap').innerHTML = html;
        el('rp-unit-table-wrap').querySelectorAll('.rp-unit-edit').forEach(btn => {{
            btn.addEventListener('click', () => openUnitForm(btn.dataset.id));
        }});
    }}

    async function loadUnits() {{
        try {{
            const data = await fetchJson('/asset-repurchase/units');
            units = data.items || [];
            renderUnitSelect();
            renderUnitTable();
        }} catch (err) {{
            el('rp-unit-table-wrap').innerHTML = '<div class="form-error">' + esc(err.message) + '</div>';
        }}
    }}

    function openUnitForm(id) {{
        const u = id ? units.find(x => String(x.id) === String(id)) : null;
        el('rp-unit-form-id').value = u ? u.id : '';
        el('rp-unit-company').value = u ? u.company_name : '';
        el('rp-unit-contact').value = u ? u.contact_name : '';
        el('rp-unit-email').value = u ? u.contact_email : '';
        el('rp-unit-status').value = u ? u.status : 'active';
        el('rp-unit-status-field').style.display = u ? '' : 'none';
        showError('rp-unit-form-error', '');
        el('rp-unit-form').style.display = '';
    }}

    async function saveUnit() {{
        const id = el('rp-unit-form-id').value;
        const payload = {{
            company_name: el('rp-unit-company').value,
            contact_name: el('rp-unit-contact').value,
            contact_email: el('rp-unit-email').value
        }};
        if (id) payload.status = el('rp-unit-status').value;
        try {{
            await fetchJson(id ? '/asset-repurchase/units/' + id : '/asset-repurchase/units', {{
                method: id ? 'PUT' : 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(payload)
            }});
            el('rp-unit-form').style.display = 'none';
            await loadUnits();
            invalidatePreview();
        }} catch (err) {{
            showError('rp-unit-form-error', err.message);
        }}
    }}

    // ── 预览 / 确认 ──────────────────────────────────────
    function buildPayload() {{
        return {{
            trust_product_id: Number(el('rp-product').value),
            asset_codes: Array.from(selectedCodes),
            repurchase_unit_id: Number(el('rp-unit').value),
            repurchase_business_date: el('rp-biz-date').value,
            amounts: amountOverrides,
            note: el('rp-note').value
        }};
    }}

    async function doPreview() {{
        showError('rp-preview-error', '');
        el('rp-execute-status').style.display = 'none';
        if (!el('rp-biz-date').value) {{
            showError('rp-preview-error', '请选择回购业务日');
            return;
        }}
        el('rp-preview-btn').disabled = true;
        try {{
            previewData = await fetchJson('/asset-repurchase/preview', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(buildPayload())
            }});
            previewKey = currentKey();
            renderPreview();
            el('rp-confirm-btn').disabled = false;
        }} catch (err) {{
            previewData = null;
            el('rp-confirm-btn').disabled = true;
            showError('rp-preview-error', err.message);
        }} finally {{
            el('rp-preview-btn').disabled = false;
        }}
    }}

    function renderPreview() {{
        const p = previewData;
        const box = el('rp-preview-result');
        box.dataset.stale = '0';
        let html = '<div class="stat-chips">' +
            '<span class="chip">产品 <strong>' + esc(p.trust_product_name) + '</strong></span>' +
            '<span class="chip">回购单位 <strong>' + esc(p.unit_company_name) + '</strong></span>' +
            '<span class="chip">联系人 <strong>' + esc(p.unit_contact_name) + ' · ' + esc(p.unit_contact_email) + '</strong></span>' +
            '<span class="chip">业务日 <strong>' + esc(p.repurchase_business_date) + '</strong></span>' +
            '<span class="chip">资产 <strong>' + p.asset_count + '</strong> 项</span>' +
            '<span class="chip">剩余合计 <strong>¥' + money(p.total_remaining) + '</strong></span>' +
            '<span class="chip chip-good">回购合计 <strong>¥' + money(p.total_repurchase_amount) + '</strong></span>' +
            '</div>';
        html += '<div class="rp-table-scroll"><table class="rp-table"><thead><tr>' +
            '<th>资产主编号</th><th>历史房源号</th><th>城市</th><th>M级 · 逾期</th><th>数据日期</th>' +
            '<th class="col-num">初始受让</th><th class="col-num">已还</th><th class="col-num">剩余</th>' +
            '<th class="col-num">分笔</th><th>状态</th><th class="col-num">实际回购金额（可改）</th>' +
            '</tr></thead><tbody>';
        p.assets.forEach(a => {{
            html += '<tr>' +
                '<td class="col-code">' + esc(a.asset_code) + '</td>' +
                '<td class="col-code col-hist" title="' + esc(a.historical_property_codes || '—') + '">' +
                    esc(a.historical_property_codes || '—') + '</td>' +
                '<td>' + esc(a.city) + '</td>' +
                '<td>' + esc(a.delinquency_bucket_display) + '</td>' +
                '<td>' + esc(a.monitor_data_date || '—') + '</td>' +
                '<td class="col-num">' + money(a.initial_transfer_amount) + '</td>' +
                '<td class="col-num">' + money(a.repaid_amount) + '</td>' +
                '<td class="col-num">' + money(a.remaining_amount) + '</td>' +
                '<td class="col-num">' + esc(a.split_count) + '</td>' +
                '<td>' + esc(a.asset_status || '—') + '</td>' +
                '<td class="col-num"><input type="number" step="0.01" min="0" class="rp-amount-input" ' +
                    'data-code="' + esc(a.asset_code) + '" value="' + Number(a.repurchase_amount).toFixed(2) + '"></td>' +
                '</tr>';
        }});
        html += '</tbody></table></div>';
        const monitorColumns = p.monitor_columns || [];
        const monitorRecords = p.monitor_records || [];
        html += '<div class="rp-monitor-preview-head">' +
            '<h3>资产监控明细（完整字段）</h3>' +
            '<span>按最新监控快照逐分笔展示 · ' + monitorRecords.length + ' 条</span>' +
            '</div>';
        if (monitorRecords.length && monitorColumns.length) {{
            html += '<div class="rp-table-scroll rp-monitor-table-scroll"><table class="rp-table rp-monitor-table"><thead><tr>';
            monitorColumns.forEach(column => {{
                html += '<th' + (column.format === 'money' || column.format === 'rate' ? ' class="col-num"' : '') +
                    '>' + esc(column.label) + '</th>';
            }});
            html += '</tr></thead><tbody>';
            monitorRecords.forEach(record => {{
                html += '<tr>';
                monitorColumns.forEach(column => {{
                    const numeric = column.format === 'money' || column.format === 'rate';
                    const code = ['source_asset_code', 'asset_code', 'custody_asset_code'].includes(column.key);
                    html += '<td class="' + (numeric ? 'col-num ' : '') + (code ? 'col-code' : '') + '">' +
                        esc(monitorValue(column, record[column.key])) + '</td>';
                }});
                html += '</tr>';
            }});
            html += '</tbody></table></div>';
        }} else {{
            html += '<div class="muted">未找到资产监控明细</div>';
        }}
        html += '<p class="muted rp-preview-note">' + esc(p.note) + '</p>';
        box.innerHTML = html;
        box.style.display = '';
        box.querySelectorAll('.rp-amount-input').forEach(input => {{
            input.addEventListener('input', () => {{
                const v = input.value.trim();
                if (v === '') delete amountOverrides[input.dataset.code];
                else amountOverrides[input.dataset.code] = v;
                invalidatePreview();
            }});
        }});
    }}

    async function doExecute() {{
        if (!previewData || previewKey !== currentKey()) {{
            showError('rp-preview-error', '预览已失效，请重新预览后再确认');
            el('rp-confirm-btn').disabled = true;
            return;
        }}
        const msg = '确认回购？\\n产品：' + previewData.trust_product_name +
            '\\n回购单位：' + previewData.unit_company_name +
            '（' + previewData.unit_contact_name + ' · ' + previewData.unit_contact_email + '）' +
            '\\n业务日：' + previewData.repurchase_business_date +
            '\\n资产：' + previewData.asset_count + ' 项' +
            '\\n剩余合计：¥' + money(previewData.total_remaining) +
            '\\n实际回购合计：¥' + money(previewData.total_repurchase_amount);
        if (!window.confirm(msg)) return;
        el('rp-confirm-btn').disabled = true;
        try {{
            const result = await fetchJson('/asset-repurchase/execute', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(buildPayload())
            }});
            const status = el('rp-execute-status');
            status.className = 'rp-execute-status execute-ok';
            status.textContent = '回购完成：单号 #' + result.order_id +
                ' · ' + result.asset_count + ' 项资产 · 回购合计 ¥' + money(result.total_repurchase_amount);
            status.style.display = '';
            previewData = null;
            previewKey = '';
            amountOverrides = {{}};
            el('rp-preview-result').style.display = 'none';
            await Promise.all([loadAssets(), loadOrders()]);
        }} catch (err) {{
            const status = el('rp-execute-status');
            status.className = 'rp-execute-status execute-err';
            status.textContent = '回购失败：' + err.message;
            status.style.display = '';
            el('rp-confirm-btn').disabled = true;
        }}
    }}

    // ── 回购记录 ─────────────────────────────────────────
    async function loadOrders() {{
        el('rp-orders-loading').style.display = '';
        try {{
            const data = await fetchJson('/asset-repurchase/orders');
            const items = data.items || [];
            if (!items.length) {{
                el('rp-orders-empty').style.display = '';
                el('rp-orders-table-wrap').style.display = 'none';
                return;
            }}
            el('rp-orders-empty').style.display = 'none';
            let html = '<table class="rp-table"><thead><tr>' +
                '<th>单号</th><th>产品</th><th>回购单位</th><th>业务日</th>' +
                '<th class="col-num">资产</th><th class="col-num">回购合计</th>' +
                '<th>状态</th><th>执行</th><th></th></tr></thead><tbody>';
            items.forEach(o => {{
                html += '<tr>' +
                    '<td>#' + o.id + '</td>' +
                    '<td>' + esc(o.trust_product_name) + '</td>' +
                    '<td>' + esc(o.unit_company_name) + '</td>' +
                    '<td>' + esc(o.repurchase_business_date) + '</td>' +
                    '<td class="col-num">' + o.asset_count + '</td>' +
                    '<td class="col-num">' + money(o.total_repurchase_amount) + '</td>' +
                    '<td><span class="status-badge status-' + o.status + '">' + (STATUS_LABELS[o.status] || o.status) + '</span></td>' +
                    '<td>' + esc((o.executed_at || '').slice(0, 19).replace('T', ' ')) +
                        (o.executed_by ? ' · ' + esc(o.executed_by) : '') + '</td>' +
                    '<td class="col-actions">' +
                        '<button type="button" class="btn-ghost btn-sm rp-order-view" data-id="' + o.id + '">详情</button> ' +
                        (o.status === 'completed'
                            ? (o.can_void
                                ? '<button type="button" class="btn-danger btn-sm rp-order-void" data-id="' + o.id + '">失效</button>'
                                : '<span class="void-blocked" title="' + esc(o.void_block_reason || '') + '">不可失效</span>')
                            : '') +
                    '</td></tr>';
            }});
            html += '</tbody></table>';
            el('rp-orders-table-wrap').innerHTML = html;
            el('rp-orders-table-wrap').style.display = '';
            el('rp-orders-table-wrap').querySelectorAll('.rp-order-view').forEach(btn => {{
                btn.addEventListener('click', () => showOrderDetail(btn.dataset.id));
            }});
            el('rp-orders-table-wrap').querySelectorAll('.rp-order-void').forEach(btn => {{
                btn.addEventListener('click', () => voidOrder(btn.dataset.id));
            }});
        }} catch (err) {{
            el('rp-orders-table-wrap').innerHTML = '<div class="form-error">' + esc(err.message) + '</div>';
            el('rp-orders-table-wrap').style.display = '';
        }} finally {{
            el('rp-orders-loading').style.display = 'none';
        }}
    }}

    async function showOrderDetail(id) {{
        try {{
            const o = await fetchJson('/asset-repurchase/orders/' + id);
            el('rp-order-detail-title').textContent = '回购单 #' + o.id + ' · ' + o.trust_product_name;
            let html = '<div class="stat-chips">' +
                '<span class="chip">回购单位 <strong>' + esc(o.unit_company_name) + '</strong></span>' +
                '<span class="chip">联系人 <strong>' + esc(o.unit_contact_name || '—') + ' · ' + esc(o.unit_contact_email || '—') + '</strong></span>' +
                '<span class="chip">业务日 <strong>' + esc(o.repurchase_business_date) + '</strong></span>' +
                '<span class="chip">状态 <strong>' + (STATUS_LABELS[o.status] || o.status) + '</strong></span>' +
                '<span class="chip">剩余合计 <strong>¥' + money(o.total_remaining) + '</strong></span>' +
                '<span class="chip chip-good">回购合计 <strong>¥' + money(o.total_repurchase_amount) + '</strong></span>' +
                '</div>';
            if (o.note) html += '<p class="muted">备注：' + esc(o.note) + '</p>';
            if (o.status === 'voided') {{
                html += '<p class="muted">失效：' + esc((o.voided_at || '').slice(0, 19).replace('T', ' ')) +
                    (o.voided_by ? ' · ' + esc(o.voided_by) : '') + '</p>';
            }}
            html += '<div class="rp-table-scroll"><table class="rp-table"><thead><tr>' +
                '<th>资产主编号</th><th>历史房源号</th><th>城市</th><th>M级 · 逾期</th><th>数据日期</th>' +
                '<th class="col-num">初始受让</th><th class="col-num">已还</th><th class="col-num">剩余</th>' +
                '<th class="col-num">回购金额</th><th class="col-num">分笔</th><th>状态</th>' +
                '</tr></thead><tbody>';
            (o.assets || []).forEach(a => {{
                html += '<tr>' +
                    '<td class="col-code">' + esc(a.asset_code) + '</td>' +
                    '<td class="col-code col-hist" title="' + esc(a.historical_property_codes || '—') + '">' +
                        esc(a.historical_property_codes || '—') + '</td>' +
                    '<td>' + esc(a.city || '—') + '</td>' +
                    '<td>' + esc(a.delinquency_bucket_display || '—') + '</td>' +
                    '<td>' + esc(a.monitor_data_date || '—') + '</td>' +
                    '<td class="col-num">' + money(a.initial_transfer_amount) + '</td>' +
                    '<td class="col-num">' + money(a.repaid_amount) + '</td>' +
                    '<td class="col-num">' + money(a.remaining_amount) + '</td>' +
                    '<td class="col-num">' + money(a.repurchase_amount) + '</td>' +
                    '<td class="col-num">' + esc(a.split_count) + '</td>' +
                    '<td>' + esc(a.asset_status || '—') + '</td>' +
                    '</tr>';
            }});
            html += '</tbody></table></div>';
            el('rp-order-detail-body').innerHTML = html;
            el('rp-order-detail').style.display = '';
            el('rp-order-detail').scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
        }} catch (err) {{
            alert(err.message);
        }}
    }}

    async function voidOrder(id) {{
        if (!window.confirm('确认将回购单 #' + id + ' 置为失效？失效后资产可重新发起回购。')) return;
        try {{
            await fetchJson('/asset-repurchase/orders/' + id + '/void', {{ method: 'POST' }});
            await Promise.all([loadOrders(), loadAssets()]);
        }} catch (err) {{
            alert('失效失败：' + err.message);
        }}
    }}

    // ── 初始化 ───────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {{
        el('rp-biz-date').value = new Date().toISOString().slice(0, 10);
        el('rp-product').addEventListener('change', loadAssets);
        el('rp-asset-filter').addEventListener('input', renderAssetTable);
        el('rp-unit').addEventListener('change', () => {{ renderUnitInfo(); invalidatePreview(); }});
        el('rp-biz-date').addEventListener('change', invalidatePreview);
        el('rp-unit-add-btn').addEventListener('click', () => openUnitForm(null));
        el('rp-unit-cancel-btn').addEventListener('click', () => {{ el('rp-unit-form').style.display = 'none'; }});
        el('rp-unit-save-btn').addEventListener('click', saveUnit);
        el('rp-preview-btn').addEventListener('click', doPreview);
        el('rp-confirm-btn').addEventListener('click', doExecute);
        el('rp-order-detail-close').addEventListener('click', () => {{ el('rp-order-detail').style.display = 'none'; }});
        loadUnits();
        loadOrders();
    }});
    </script>
    """
    return _page_shell("资产回购", body)


def _page_shell(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(title)} · 房地产资产证券化平台</title>
    <style>
        {PAGE_CHROME_CSS}
        {STANDARD_HEADER_CSS}
        {FORM_FIELD_CSS}
        {BTN_CSS}
        {TABLE_SCROLL_CSS}
        h1 {{ font-size: 1.5rem; color: #f8fafc; margin: 0 0 0.5rem; }}
        p.muted {{ color: #94a3b8; margin-bottom: 1rem; font-size: 0.9rem; }}
        .card {{
            background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px; padding: 1.25rem; margin-bottom: 1rem;
        }}
        .panel h2, .card h2 {{ font-size: 1.1rem; color: #e2e8f0; margin: 0 0 1rem; }}
        .rp-grid {{
            display: grid;
            grid-template-columns: minmax(360px, 1.25fr) minmax(300px, 0.75fr);
            gap: 1rem; align-items: start;
        }}
        @media (max-width: 960px) {{ .rp-grid {{ grid-template-columns: 1fr; }} }}
        .rp-toolbar {{ display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 0.65rem; }}
        .rp-field {{ margin-bottom: 0.65rem; min-width: 12rem; }}
        .rp-field-grow {{ flex: 1; }}
        .rp-field label {{ display: block; color: #cbd5e1; font-size: 0.88rem; margin-bottom: 0.2rem; }}
        .rp-input, .rp-field select {{
            width: 100%; box-sizing: border-box;
            padding: 0.5rem 0.6rem; border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.14);
            background: rgba(15,23,42,0.55); color: #e2e8f0; font-size: 0.88rem;
        }}
        .rp-input:focus, .rp-field select:focus {{
            outline: none; border-color: rgba(59,130,246,0.55);
            box-shadow: 0 0 0 2px rgba(59,130,246,0.15);
        }}
        .stat-chips {{ display: flex; flex-wrap: wrap; gap: 0.4rem 0.65rem; margin-bottom: 0.6rem; }}
        .chip {{
            display: inline-flex; align-items: center; gap: 0.25rem;
            padding: 0.2rem 0.55rem; border-radius: 6px;
            background: rgba(255,255,255,0.05); font-size: 0.82rem; color: #94a3b8;
        }}
        .chip strong {{ color: #e2e8f0; font-variant-numeric: tabular-nums; }}
        .chip-good {{ background: rgba(34,197,94,0.12); color: #86efac; }}
        .chip-good strong {{ color: #bbf7d0; }}
        .rp-table-scroll {{
            overflow-x: auto; max-height: 26rem; overflow-y: auto;
            border: 1px solid rgba(255,255,255,0.08); border-radius: 8px;
            background: rgba(0,0,0,0.12);
        }}
        .rp-table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; }}
        .rp-table th, .rp-table td {{
            padding: 0.4rem 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.08);
            white-space: nowrap; vertical-align: middle; text-align: left;
        }}
        .rp-table th {{
            position: sticky; top: 0; background: #1e293b; z-index: 1;
            color: #94a3b8; font-weight: 600; font-size: 0.75rem;
        }}
        .rp-table tbody tr:hover {{ background: rgba(255,255,255,0.03); }}
        .rp-table .col-num {{ text-align: right; font-variant-numeric: tabular-nums; }}
        .rp-table .col-check {{ width: 1.8rem; text-align: center; }}
        .rp-table .col-code {{
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.75rem;
        }}
        .rp-table .col-hist {{ max-width: 14rem; overflow: hidden; text-overflow: ellipsis; }}
        .rp-table .col-actions {{ white-space: nowrap; }}
        .rp-table tr.row-disabled td {{ color: #64748b; }}
        .rp-table tr.row-checked td {{ background: rgba(59,130,246,0.07); }}
        .rp-unit-info {{ font-size: 0.85rem; margin-bottom: 0.75rem; }}
        .rp-unit-manage {{ border-top: 1px dashed rgba(148,163,184,0.25); padding-top: 0.85rem; }}
        .rp-unit-manage-head {{
            display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;
        }}
        .rp-unit-manage-head h3 {{ margin: 0; font-size: 0.92rem; color: #cbd5e1; }}
        .rp-unit-form {{
            border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;
            padding: 0.75rem; margin-bottom: 0.75rem; background: rgba(15,23,42,0.35);
        }}
        .rp-unit-form-actions {{ display: flex; gap: 0.5rem; }}
        .rp-execute-form {{
            display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-end;
            justify-content: space-between; margin-bottom: 0.75rem;
        }}
        .rp-execute-fields {{ display: flex; gap: 0.75rem; flex-wrap: wrap; flex: 1; }}
        .rp-execute-actions {{ display: flex; gap: 0.5rem; flex-wrap: wrap; }}
        .rp-preview-result {{ margin-top: 0.75rem; }}
        .rp-preview-note {{ margin-top: 0.6rem; font-size: 0.8rem; }}
        .rp-monitor-preview-head {{
            display: flex; align-items: baseline; justify-content: space-between;
            gap: 0.75rem; margin: 1rem 0 0.5rem;
        }}
        .rp-monitor-preview-head h3 {{
            margin: 0; color: #e2e8f0; font-size: 0.95rem;
        }}
        .rp-monitor-preview-head span {{ color: #64748b; font-size: 0.78rem; }}
        .rp-monitor-table-scroll {{ max-height: 32rem; }}
        .rp-monitor-table {{ width: max-content; min-width: 100%; }}
        .rp-stale-tip {{
            color: #fbbf24; font-size: 0.85rem; margin-bottom: 0.6rem;
            padding: 0.45rem 0.6rem; border-radius: 8px;
            background: rgba(251,191,36,0.1); border: 1px solid rgba(251,191,36,0.3);
        }}
        .rp-amount-input {{
            width: 9rem; box-sizing: border-box; text-align: right;
            padding: 0.3rem 0.45rem; border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.16);
            background: rgba(15,23,42,0.6); color: #e2e8f0;
            font-variant-numeric: tabular-nums; font-size: 0.8rem;
        }}
        .rp-amount-input:focus {{
            outline: none; border-color: rgba(59,130,246,0.55);
            box-shadow: 0 0 0 2px rgba(59,130,246,0.15);
        }}
        .form-error {{
            color: #fca5a5; font-size: 0.85rem; margin-bottom: 0.65rem;
            padding: 0.5rem 0.65rem; border-radius: 8px;
            background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.25);
            white-space: pre-line; line-height: 1.45;
        }}
        .rp-execute-status {{
            margin-top: 0.75rem; font-size: 0.85rem;
            padding: 0.5rem 0.65rem; border-radius: 8px; line-height: 1.45;
        }}
        .execute-ok {{
            color: #86efac; background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.25);
        }}
        .execute-err {{
            color: #fca5a5; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.25);
        }}
        .status-badge {{
            display: inline-block; padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.76rem;
        }}
        .status-completed {{ background: rgba(34,197,94,0.15); color: #86efac; }}
        .status-voided {{ background: rgba(148,163,184,0.15); color: #94a3b8; }}
        .btn-sm {{ padding: 0.25rem 0.55rem; font-size: 0.78rem; }}
        .btn-ghost {{
            padding: 0.35rem 0.75rem; border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.12); background: transparent;
            color: #cbd5e1; cursor: pointer;
        }}
        .btn-ghost:hover {{ background: rgba(255,255,255,0.06); color: #e2e8f0; }}
        .btn-danger {{
            padding: 0.25rem 0.55rem; border-radius: 8px; border: 1px solid rgba(239,68,68,0.45);
            background: rgba(239,68,68,0.15); color: #fca5a5; cursor: pointer; font-size: 0.78rem;
        }}
        .btn-danger:hover {{ background: rgba(239,68,68,0.25); color: #fecaca; }}
        .void-blocked {{ font-size: 0.76rem; color: #64748b; }}
        .btn-primary:disabled, .btn-secondary:disabled {{ opacity: 0.6; cursor: not-allowed; }}
        .rp-order-detail {{
            margin-top: 1rem; padding-top: 1rem; border-top: 1px solid rgba(255,255,255,0.1);
        }}
        .rp-order-detail-head {{
            display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.65rem;
        }}
        .rp-order-detail-head h3 {{ margin: 0; font-size: 1rem; color: #e2e8f0; }}
    </style>
</head>
<body>
    {body}
</body>
</html>"""
