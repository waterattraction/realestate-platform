"""资产置换页面."""

from __future__ import annotations

from html import escape

from app.ui_css import BTN_CSS, FORM_FIELD_CSS, PAGE_CHROME_CSS, STANDARD_HEADER_CSS, TABLE_SCROLL_CSS


def render_swap_page(
    products: list[dict],
    *,
    trust_product_id: int | None = None,
    asset_codes_text: str = "",
    exclude_codes_text: str = "",
    username: str = "",
) -> str:
    product_options = ""
    for p in products:
        sel = " selected" if trust_product_id == p["id"] else ""
        product_options += (
            f'<option value="{int(p["id"])}"{sel}>{escape(p["name"])}</option>'
        )
    storage_user = escape(username or "default")

    body = f"""
    <div class="container">
    <nav class="breadcrumb"><a href="/">首页</a> / 资产置换</nav>
    <h1>资产置换</h1>
    <p class="muted">查询推荐为只读，不写入数据库。选定方案后请先预览再执行置换；置换仅写入置换新表，不修改资产监控导入表与发行表。置换业务日可选手动指定（默认当日）。置换单可失效；若置换后相关信托产品已有新的资产监控表导入，则不可失效。</p>

    <div class="swap-grid">
        <div class="card panel panel-source">
            <h2>转出资产</h2>
            <form id="swap-form" class="filters">
                <div><label>信托产品</label>
                <select name="trust_product_id" id="trust_product_id" required>{product_options}</select></div>
                <div class="swap-field">
                    <label for="asset_codes">资产主编号</label>
                    <p class="swap-field-hint">多个编号：每行一个，或用逗号、空格分隔</p>
                    <textarea class="swap-textarea swap-textarea-compact" name="asset_codes" id="asset_codes" rows="2"
                        placeholder="107112235776&#10;107112235777">{escape(asset_codes_text)}</textarea>
                </div>
                <div><button type="submit" class="btn-primary" id="swap-submit-btn">查询推荐</button></div>
            </form>
            <div id="source-summary" class="summary-block"></div>
            <div id="source-table-wrap" class="table-wrap table-wrap-source"></div>
        </div>

        <div class="card panel panel-candidate">
            <h2>推荐候选（美润1号）</h2>
            <div class="swap-input-row">
                <div class="swap-field">
                    <label for="required_asset_codes">手工指定房源（可选）</label>
                    <p class="swap-field-hint">填写后必须进入推荐方案；逾期天数超过 −7 天仍可指定，查询结果会提示</p>
                    <textarea class="swap-textarea swap-textarea-compact" id="required_asset_codes" rows="2"
                        placeholder="必须纳入方案的主编号"></textarea>
                </div>
                <div class="swap-field">
                    <label for="exclude_asset_codes">排除资产编号（可选）</label>
                    <p class="swap-field-hint">保存在本浏览器 · <a href="#" id="clear-exclude-storage">清除已存</a></p>
                    <textarea class="swap-textarea swap-textarea-compact" id="exclude_asset_codes" rows="2"
                        placeholder="不推荐的主编号">{escape(exclude_codes_text)}</textarea>
                </div>
            </div>
            <div class="scheme-tabs" id="scheme-tabs">
                <button type="button" class="scheme-tab active" data-scheme="a" title="最少户数">方案 A</button>
                <button type="button" class="scheme-tab" data-scheme="b" title="快速贪心">方案 B</button>
                <button type="button" class="scheme-tab" data-scheme="c" title="多视角对比">方案 C</button>
            </div>
            <div class="meta-bar" id="meta-line"></div>
            <div id="required-warn" class="required-warn" style="display:none"></div>
            <div id="form-error" class="form-error" style="display:none"></div>
            <div id="scheme-panel-a" class="scheme-panel"></div>
            <div id="scheme-panel-b" class="scheme-panel" style="display:none"></div>
            <div id="scheme-panel-c" class="scheme-panel" style="display:none"></div>
        </div>
    </div>

    <div class="card panel-execute">
        <h2>执行置换</h2>
        <div class="execute-form">
            <div class="execute-fields">
                <div class="swap-field">
                    <label for="swap_business_date">置换业务日</label>
                    <input type="date" id="swap_business_date" class="swap-date-input" />
                </div>
                <div class="swap-field execute-note-field">
                    <label for="swap_note">备注（可选）</label>
                    <input type="text" id="swap_note" class="swap-note-input" placeholder="置换说明" />
                </div>
            </div>
            <div class="execute-actions">
                <button type="button" class="btn-secondary" id="preview-swap-btn" disabled>预览置换</button>
                <button type="button" class="btn-primary" id="confirm-swap-btn" disabled>确认置换</button>
            </div>
        </div>
        <div id="preview-result" class="preview-result" style="display:none"></div>
        <div id="execute-status" class="execute-status" style="display:none"></div>
    </div>

    <div class="card panel-orders">
        <h2>置换记录</h2>
        <div id="orders-loading" class="muted orders-loading">加载中…</div>
        <div id="orders-table-wrap" class="table-wrap orders-table-wrap" style="display:none"></div>
        <div id="orders-empty" class="muted" style="display:none">暂无置换记录</div>
        <div id="order-detail-panel" class="order-detail-panel" style="display:none">
            <div class="order-detail-header">
                <h3 id="order-detail-title">置换单详情</h3>
                <button type="button" class="btn-ghost" id="order-detail-close">关闭</button>
            </div>
            <div id="order-detail-body"></div>
        </div>
    </div>
    </div>

    <script>
    const STORAGE_USER = '{storage_user}';
    const EXCLUDE_STORAGE_KEY = 'asset-swap:exclude:' + STORAGE_USER;
    const STATUS_LABELS = {{ completed: '已完成', voided: '已失效' }};
    const SCHEME_LABELS = {{ a: '方案 A', b: '方案 B', c: '方案 C', manual: '手工' }};

    const fmtNum = (v) => (v == null || v === '') ? '—' : Number(v).toLocaleString('zh-CN', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
    const parseCodeList = (text) => String(text || '')
        .split(/[\\r\\n,，;；\\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);
    const escHtml = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    const codesEqual = (a, b) => {{
        if (!a || !b || a.length !== b.length) return false;
        const sa = [...a].sort();
        const sb = [...b].sort();
        return sa.every((c, i) => c === sb[i]);
    }};

    function formatApiError(data, fallback) {{
        if (!data) return fallback || '请求失败';
        const d = data.detail;
        if (d == null || d === '') return fallback || data.message || '请求失败';
        if (typeof d === 'string') return d;
        if (Array.isArray(d)) {{
            return d.map((x) => {{
                if (typeof x === 'string') return x;
                if (x && x.msg) return x.msg;
                if (x && x.message) return x.message;
                return JSON.stringify(x);
            }}).join('\\n');
        }}
        if (typeof d === 'object' && d.msg) return d.msg;
        return String(d);
    }}

    async function readJsonResponse(resp) {{
        let data = null;
        try {{ data = await resp.json(); }} catch (e) {{ /* non-json */ }}
        if (!resp.ok) throw new Error(formatApiError(data, resp.statusText));
        return data;
    }}

    function todayIso() {{
        const d = new Date();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return d.getFullYear() + '-' + m + '-' + day;
    }}

    let lastData = null;
    let selectedScheme = null;
    let previewValid = false;
    let lastPreviewPayloadKey = '';

    function loadExcludeStorage() {{
        try {{
            const saved = localStorage.getItem(EXCLUDE_STORAGE_KEY);
            if (saved != null) {{
                document.getElementById('exclude_asset_codes').value = saved;
            }}
        }} catch (e) {{ /* ignore */ }}
    }}

    function saveExcludeStorage(text) {{
        try {{
            const val = String(text || '').trim();
            if (val) localStorage.setItem(EXCLUDE_STORAGE_KEY, val);
            else localStorage.removeItem(EXCLUDE_STORAGE_KEY);
        }} catch (e) {{ /* ignore */ }}
    }}

    function showFormError(msg) {{
        const el = document.getElementById('form-error');
        if (!msg) {{ el.style.display = 'none'; el.textContent = ''; return; }}
        el.textContent = msg;
        el.style.display = 'block';
        const warnEl = document.getElementById('required-warn');
        if (warnEl) {{ warnEl.style.display = 'none'; warnEl.textContent = ''; }}
    }}

    function showExecuteStatus(msg, kind) {{
        const el = document.getElementById('execute-status');
        if (!msg) {{ el.style.display = 'none'; el.textContent = ''; el.className = 'execute-status'; return; }}
        el.textContent = msg;
        el.className = 'execute-status' + (kind ? ' execute-status-' + kind : '');
        el.style.display = 'block';
    }}

    function invalidatePreview() {{
        previewValid = false;
        lastPreviewPayloadKey = '';
        document.getElementById('confirm-swap-btn').disabled = true;
        document.getElementById('preview-result').style.display = 'none';
        document.getElementById('preview-result').innerHTML = '';
    }}

    function updateExecuteButtons() {{
        document.getElementById('preview-swap-btn').disabled = !selectedScheme;
    }}

    function buildSwapPayload() {{
        if (!selectedScheme) return null;
        const note = document.getElementById('swap_note').value.trim();
        return {{
            trust_product_id: parseInt(document.getElementById('trust_product_id').value, 10),
            source_asset_codes: parseCodeList(document.getElementById('asset_codes').value),
            candidate_asset_codes: selectedScheme.candidateCodes,
            scheme_id: selectedScheme.schemeId,
            swap_business_date: document.getElementById('swap_business_date').value,
            note: note || undefined,
        }};
    }}

    function payloadKey(payload) {{
        return JSON.stringify(payload);
    }}

    function renderSource(source) {{
        if (!source) return;
        const el = document.getElementById('source-summary');
        el.innerHTML = `
            <div class="stat-chips">
                <span class="chip">转出 <strong>${{source.asset_count}}</strong> 户</span>
                <span class="chip">剩余合计 <strong>${{fmtNum(source.total_remaining)}}</strong></span>
                <span class="chip">参考折扣率 <strong>${{source.reference_discount_rate_display}}</strong></span>
            </div>
            <div class="stat-chips stat-chips-sub">
                <span class="chip">参考加权成本 <strong>${{fmtNum(source.reference_weighted_cost)}}</strong></span>
                <span class="chip">装修款截止日 <strong>${{source.renovation_deadline}}</strong></span>
            </div>`;
        let rows = '';
        (source.assets || []).forEach(a => {{
            const city = a.city || '—';
            rows += `<tr>
                <td class="src-code" title="${{escHtml(a.asset_code)}}">${{escHtml(a.asset_code)}}</td>
                <td class="src-city" title="${{escHtml(city)}}">${{escHtml(city)}}</td>
                <td class="src-date">${{escHtml(a.issue_date)}}</td>
                <td class="src-num">${{fmtNum(a.remaining_amount)}}</td>
                <td class="src-rate">${{escHtml(a.asset_transfer_discount_rate_display)}}</td>
                <td class="src-date">${{escHtml(a.renovation_deadline)}}</td>
            </tr>`;
        }});
        document.getElementById('source-table-wrap').innerHTML = rows ? `
            <table class="swap-table swap-table-source"><thead><tr>
                <th class="src-code">资产主编号</th>
                <th class="src-city">城市</th>
                <th class="src-date">发行日</th>
                <th class="src-num">剩余还款</th>
                <th class="src-rate">折扣率</th>
                <th class="src-date">装修款截止日</th>
            </tr></thead><tbody>${{rows}}</tbody></table>` : '';
    }}

    function comboChips(combo) {{
        const surplusCls = combo.surplus <= 500 ? 'chip-good' : '';
        return `
            <div class="stat-chips combo-chips">
                <span class="chip"><strong>${{combo.asset_count}}</strong> 户</span>
                <span class="chip">合计 <strong>${{fmtNum(combo.total_remaining)}}</strong></span>
                <span class="chip ${{surplusCls}}">盈余 <strong>${{fmtNum(combo.surplus)}}</strong></span>
                <span class="chip">加权成本 <strong>${{fmtNum(combo.weighted_cost)}}</strong></span>
                <span class="chip">成本差 <strong>${{fmtNum(combo.cost_delta)}}</strong></span>
            </div>`;
    }}

    function isComboSelected(ctx, codes) {{
        if (!selectedScheme) return false;
        return selectedScheme.schemeId === ctx.schemeId
            && selectedScheme.label === ctx.label
            && codesEqual(selectedScheme.candidateCodes, codes);
    }}

    function renderCombo(combo, pinnedCodes, selectCtx) {{
        if (!combo) return '<p class="muted">无可行组合</p>';
        const pinned = pinnedCodes || new Set();
        const codes = (combo.assets || []).map((a) => a.asset_code);
        const selected = isComboSelected(selectCtx, codes);
        const selectId = 'combo-select-' + selectCtx.schemeId + '-' + selectCtx.comboKey;
        let rows = '';
        (combo.assets || []).forEach((a, i) => {{
            const isPinned = a.pinned || pinned.has(a.asset_code);
            const city = a.city || '—';
            rows += `<tr class="${{isPinned ? 'row-pinned' : ''}}">
                <td class="col-idx">${{i + 1}}</td>
                <td class="col-code" title="${{escHtml(a.asset_code)}}">${{escHtml(a.asset_code)}}${{isPinned ? '<span class="pin-badge">指定</span>' : ''}}</td>
                <td class="col-city" title="${{escHtml(city)}}">${{escHtml(city)}}</td>
                <td class="col-custody" title="${{escHtml(a.custody_asset_code || '')}}">${{escHtml(a.custody_asset_code || '—')}}</td>
                <td class="col-num">${{fmtNum(a.remaining_amount)}}</td>
                <td class="col-rate">${{escHtml(a.asset_transfer_discount_rate_display)}}</td>
                <td class="col-date">${{escHtml(a.last_renovation_payment_date)}}</td>
                <td class="col-bucket">${{escHtml(a.delinquency_bucket || '—')}}</td>
                <td class="col-overdue">${{a.overdue_days != null ? a.overdue_days + '天' : '—'}}</td>
            </tr>`;
        }});
        return `
            <div class="combo-card${{selected ? ' combo-card-selected' : ''}}"
                 data-scheme-id="${{escHtml(selectCtx.schemeId)}}"
                 data-combo-key="${{escHtml(selectCtx.comboKey)}}"
                 data-label="${{escHtml(selectCtx.label)}}"
                 data-candidate-codes="${{escHtml(JSON.stringify(codes))}}">
                ${{comboChips(combo)}}
                <table class="swap-table swap-table-candidate"><thead><tr>
                    <th class="col-idx">#</th>
                    <th class="col-code">资产主编号</th>
                    <th class="col-city">城市</th>
                    <th class="col-custody">房源托管号</th>
                    <th class="col-num">剩余还款</th>
                    <th class="col-rate">折扣率</th>
                    <th class="col-date">装修款截止日</th>
                    <th class="col-bucket">M级</th>
                    <th class="col-overdue">逾期天数</th>
                </tr></thead><tbody>${{rows}}</tbody></table>
                <label class="combo-select-row" for="${{selectId}}">
                    <input type="radio" name="swap-scheme-select" id="${{selectId}}" value="${{escHtml(selectCtx.comboKey)}}"${{selected ? ' checked' : ''}} />
                    选用此方案
                </label>
            </div>`;
    }}

    function selectComboCard(card) {{
        if (!card || !card.dataset.schemeId) return;
        let codes = [];
        try {{ codes = JSON.parse(card.dataset.candidateCodes || '[]'); }} catch (e) {{ return; }}
        selectedScheme = {{
            schemeId: card.dataset.schemeId,
            candidateCodes: codes,
            label: card.dataset.label || '',
        }};
        document.querySelectorAll('.combo-card').forEach((c) => c.classList.remove('combo-card-selected'));
        document.querySelectorAll('.combo-card input[type=radio]').forEach((r) => {{ r.checked = false; }});
        card.classList.add('combo-card-selected');
        const radio = card.querySelector('input[type=radio]');
        if (radio) radio.checked = true;
        invalidatePreview();
        updateExecuteButtons();
        showExecuteStatus('', null);
    }}

    function attachComboSelection() {{
        document.querySelectorAll('.combo-card').forEach((card) => {{
            card.addEventListener('click', (e) => {{
                if (e.target.closest('input[type=radio]')) return;
                selectComboCard(card);
            }});
            const radio = card.querySelector('input[type=radio]');
            if (radio) {{
                radio.addEventListener('change', () => selectComboCard(card));
            }}
        }});
    }}

    function pinnedSet(data) {{
        return new Set((data.required && data.required.asset_codes) || []);
    }}

    function renderSchemeA(data) {{
        const s = data.schemes.a;
        const ps = pinnedSet(data);
        let html = `<p class="scheme-desc">${{escHtml(s.scheme_label)}}${{s.min_asset_count ? ' · 最少 ' + s.min_asset_count + ' 户' : ''}}</p>`;
        if (!s.combinations || !s.combinations.length) {{
            html += '<p class="warn">未找到满足条件的组合</p>';
        }} else {{
            s.combinations.forEach((c, i) => {{
                html += renderCombo(c, ps, {{
                    schemeId: 'a',
                    comboKey: String(i),
                    label: '方案 A · 组合 ' + (i + 1),
                }});
            }});
        }}
        document.getElementById('scheme-panel-a').innerHTML = html;
    }}

    function renderSchemeB(data) {{
        const s = data.schemes.b;
        const ps = pinnedSet(data);
        let html = `<p class="scheme-desc">${{escHtml(s.scheme_label)}}（启发式）</p>`;
        if (!s.combinations || !s.combinations.length) {{
            html += '<p class="warn">未找到满足条件的组合</p>';
        }} else {{
            s.combinations.forEach((c, i) => {{
                html += renderCombo(c, ps, {{
                    schemeId: 'b',
                    comboKey: String(i),
                    label: '方案 B · 组合 ' + (i + 1),
                }});
            }});
        }}
        document.getElementById('scheme-panel-b').innerHTML = html;
    }}

    function renderSchemeC(data) {{
        const s = data.schemes.c;
        const ps = pinnedSet(data);
        let html = `<p class="scheme-desc">${{escHtml(s.scheme_label)}}</p>`;
        const blocks = [
            ['C1 · 最少户数', s.c1_min_count, 'c1'],
            ['C2 · 金额最贴近（≤3户）', s.c2_min_surplus, 'c2'],
            ['C3 · 加权成本最贴近', s.c3_best_cost_match, 'c3'],
        ];
        blocks.forEach(([title, combo, comboKey]) => {{
            html += `<h3>${{escHtml(title)}}</h3>` + renderCombo(combo, ps, {{
                schemeId: 'c',
                comboKey: comboKey,
                label: title,
            }});
        }});
        document.getElementById('scheme-panel-c').innerHTML = html;
    }}

    function renderAll(data) {{
        lastData = data;
        selectedScheme = null;
        invalidatePreview();
        updateExecuteButtons();
        showFormError('');
        showExecuteStatus('', null);
        renderSource(data.source);
        const m = data.meta;
        const req = data.required;
        const maxOd = m?.candidate_max_overdue_days ?? -7;
        let meta = `候选池 <strong>${{m?.candidate_pool_size ?? 0}}</strong> 户 · 目标产品 <strong>${{escHtml(m?.target_product_name ?? '')}}</strong>`;
        meta += ` · 自动候选逾期 ≤ <strong>${{maxOd}}</strong> 天`;
        if (req?.asset_count) {{
            meta += ` · 指定 <strong>${{req.asset_count}}</strong> 户（${{fmtNum(req.total_remaining)}}）`;
        }}
        document.getElementById('meta-line').innerHTML = meta;
        const warnEl = document.getElementById('required-warn');
        const warns = req?.overdue_warnings || [];
        if (warnEl) {{
            if (warns.length) {{
                warnEl.style.display = 'block';
                warnEl.textContent = '提示：必选房源逾期天数超过 ' + maxOd + ' 天\\n' + warns.join('\\n');
            }} else {{
                warnEl.style.display = 'none';
                warnEl.textContent = '';
            }}
        }}
        renderSchemeA(data);
        renderSchemeB(data);
        renderSchemeC(data);
        attachComboSelection();
    }}

    function cell(v) {{
        if (v == null || v === '') return '—';
        return escHtml(String(v));
    }}

    const PREVIEW_ASSET_COLS = [
        {{ key: 'asset_code', label: '资产主编号', cls: 'col-code' }},
        {{ key: 'custody_asset_code', label: '房源托管号', cls: 'col-custody' }},
        {{ key: 'city', label: '城市', cls: 'col-city' }},
        {{ key: 'flow', label: '产品流向', cls: 'col-flow' }},
        {{ key: 'remaining_amount', label: '剩余还款', cls: 'col-num', num: true }},
        {{ key: 'initial_transfer_amount', label: '初始受让', cls: 'col-num', num: true }},
        {{ key: 'repaid_amount', label: '已还款', cls: 'col-num', num: true }},
        {{ key: 'asset_transfer_discount_rate_display', label: '折扣率', cls: 'col-rate' }},
        {{ key: 'last_renovation_payment_date', label: '装修款截止日', cls: 'col-date' }},
        {{ key: 'monitor_data_date', label: '监控统计日', cls: 'col-date' }},
        {{ key: 'delinquency_bucket_display', label: 'M级/逾期', cls: 'col-bucket' }},
        {{ key: 'asset_status', label: '资产状态', cls: 'col-status' }},
        {{ key: 'community_name', label: '小区名称', cls: 'col-community' }},
    ];

    const MONITOR_PREVIEW_COLS = [
        {{ key: 'trust_product_name', label: '归属产品' }},
        {{ key: 'snapshot_role', label: '角色' }},
        {{ key: 'asset_code', label: '资产主编号' }},
        {{ key: 'custody_asset_code', label: '托管房源编码' }},
        {{ key: 'source_asset_code', label: '资产编号(房源)' }},
        {{ key: 'asset_pool_code', label: '资产包编号' }},
        {{ key: 'renovation_vendor', label: '装修服务商' }},
        {{ key: 'data_date', label: '统计日期' }},
        {{ key: 'initial_transfer_amount', label: '初始受让金额', num: true }},
        {{ key: 'repaid_amount', label: '已还款金额', num: true }},
        {{ key: 'remaining_amount', label: '剩余还款金额', num: true }},
        {{ key: 'asset_status', label: '资产状态' }},
        {{ key: 'last_renovation_payment_date', label: '最后一期装修款付款时间' }},
        {{ key: 'community_name', label: '小区名称' }},
        {{ key: 'city', label: '城市' }},
        {{ key: 'collection_contract_code', label: '收房合同编码' }},
        {{ key: 'custody_agreement_sign_date', label: '托管协议签署日期' }},
        {{ key: 'collection_contract_years', label: '收房合同签约年数' }},
        {{ key: 'owner_code', label: '业主代码' }},
        {{ key: 'withholding_ratio', label: '代扣比例' }},
        {{ key: 'actual_monthly_rent', label: '实际出房月租金', num: true }},
        {{ key: 'overdue_days', label: '逾期天数' }},
    ];

    function roleLabel(role) {{
        if (role === 'exit') return '转出时(exit)';
        if (role === 'entry') return '转入时(entry)';
        return role || '—';
    }}

    function renderPreviewAssetTable(title, legs, rowClass) {{
        if (!legs || !legs.length) return `<p class="muted">${{escHtml(title)}}：无</p>`;
        let rows = '';
        legs.forEach((leg) => {{
            const flow = (leg.from_trust_product_name || '') + ' → ' + (leg.to_trust_product_name || '');
            const trCls = rowClass || (leg.direction === 'out' ? 'row-swap-out' : (leg.direction === 'in' ? 'row-swap-in' : ''));
            rows += `<tr class="${{trCls}}">`;
            PREVIEW_ASSET_COLS.forEach((col) => {{
                let val = leg[col.key];
                if (col.key === 'flow') val = flow;
                if (col.num) {{
                    rows += `<td class="${{col.cls}}">${{fmtNum(val)}}</td>`;
                }} else {{
                    rows += `<td class="${{col.cls}}">${{cell(val)}}</td>`;
                }}
            }});
            rows += '</tr>';
        }});
        const heads = PREVIEW_ASSET_COLS.map((c) => `<th class="${{c.cls}}">${{escHtml(c.label)}}</th>`).join('');
        return `
            <div class="preview-section">
                <h4>${{escHtml(title)}}</h4>
                <div class="preview-table-scroll">
                    <table class="swap-table swap-table-preview">
                        <thead><tr>${{heads}}</tr></thead>
                        <tbody>${{rows}}</tbody>
                    </table>
                </div>
            </div>`;
    }}

    function renderMonitorRows(snaps) {{
        if (!snaps || !snaps.length) return '<p class="muted">无监控快照</p>';
        const ordered = snaps.slice().sort((a, b) => {{
            const ra = a.snapshot_role === 'exit' ? 0 : (a.snapshot_role === 'entry' ? 1 : 2);
            const rb = b.snapshot_role === 'exit' ? 0 : (b.snapshot_role === 'entry' ? 1 : 2);
            if (ra !== rb) return ra - rb;
            return String(a.asset_code || '').localeCompare(String(b.asset_code || ''), 'zh');
        }});
        let rows = '';
        ordered.forEach((snap) => {{
            const role = snap.snapshot_role || '';
            const trCls = role === 'exit' ? 'row-swap-out' : (role === 'entry' ? 'row-swap-in' : '');
            rows += `<tr class="${{trCls}}">`;
            MONITOR_PREVIEW_COLS.forEach((col) => {{
                let val = snap[col.key];
                if (col.key === 'snapshot_role') val = roleLabel(val);
                if (col.num) {{
                    rows += `<td class="col-num">${{fmtNum(val)}}</td>`;
                }} else {{
                    rows += `<td>${{cell(val)}}</td>`;
                }}
            }});
            rows += '</tr>';
        }});
        const heads = MONITOR_PREVIEW_COLS.map((c) => `<th>${{escHtml(c.label)}}</th>`).join('');
        return `
            <div class="preview-table-scroll preview-monitor-scroll">
                <table class="swap-table swap-table-preview swap-table-monitor">
                    <thead><tr>${{heads}}</tr></thead>
                    <tbody>${{rows}}</tbody>
                </table>
            </div>`;
    }}

    function collectMonitorByProduct(data) {{
        /** 按归属信托产品归组；颜色/排序按 snapshot_role=exit|entry */
        const groups = {{}};
        const ensure = (id, name) => {{
            const key = String(id ?? name ?? '');
            if (!groups[key]) {{
                groups[key] = {{
                    product_id: id,
                    product_name: name || String(id),
                    snaps: [],
                }};
            }}
            return groups[key];
        }};
        const pushLeg = (leg) => {{
            [['exit', leg.exit_monitor], ['entry', leg.entry_monitor]].forEach(([role, snap]) => {{
                if (!snap) return;
                const g = ensure(snap.trust_product_id, snap.trust_product_name);
                g.snaps.push({{
                    ...snap,
                    snapshot_role: snap.snapshot_role || role,
                }});
            }});
        }};
        (data.out_assets || []).forEach(pushLeg);
        (data.in_assets || []).forEach(pushLeg);
        // 稳定顺序：转出产品优先，再对手方，其余按名称
        const preferred = [
            data.source_trust_product_id,
            data.counterparty_trust_product_id,
        ].filter((x) => x != null).map(String);
        return Object.values(groups).sort((a, b) => {{
            const ia = preferred.indexOf(String(a.product_id));
            const ib = preferred.indexOf(String(b.product_id));
            if (ia !== -1 || ib !== -1) {{
                if (ia === -1) return 1;
                if (ib === -1) return -1;
                return ia - ib;
            }}
            return String(a.product_name).localeCompare(String(b.product_name), 'zh');
        }});
    }}

    function renderMonitorByProduct(data) {{
        const groups = collectMonitorByProduct(data);
        if (!groups.length) return '<p class="muted">无监控快照</p>';
        let html = `
            <h3 class="preview-monitor-title">资产监控快照预览</h3>
            <p class="muted preview-monitor-hint">
                按信托产品列出。橙色=转出时(exit)，蓝色=转入时(entry)。
                转入时：初始受让金额=转出时剩余还款，已还款=0，剩余还款=初始受让−已还款。
                转出时在上，转入时在下。
            </p>
            <div class="preview-legend">
                <span class="legend-out">■ 转出时</span>
                <span class="legend-in">■ 转入时</span>
            </div>`;
        groups.forEach((g) => {{
            const exitN = g.snaps.filter((s) => s.snapshot_role === 'exit').length;
            const entryN = g.snaps.filter((s) => s.snapshot_role === 'entry').length;
            html += `
                <div class="preview-section preview-product-block">
                    <h4 class="preview-product-title">${{escHtml(g.product_name)}}
                        <span class="chip">转出时 ${{exitN}}</span>
                        <span class="chip">转入时 ${{entryN}}</span>
                    </h4>
                    ${{renderMonitorRows(g.snaps)}}
                </div>`;
        }});
        return html;
    }}

    function syncPreviewMonitorScrolls(rootEl) {{
        const root = rootEl || document.getElementById('preview-result') || document;
        const scrolls = Array.from(root.querySelectorAll('.preview-monitor-scroll'));
        if (scrolls.length < 2) return;
        let locking = false;
        scrolls.forEach((el) => {{
            el.addEventListener('scroll', () => {{
                if (locking) return;
                locking = true;
                const left = el.scrollLeft;
                scrolls.forEach((other) => {{
                    if (other !== el && other.scrollLeft !== left) other.scrollLeft = left;
                }});
                locking = false;
            }}, {{ passive: true }});
        }});
    }}

    function renderPreviewResult(data) {{
        const el = document.getElementById('preview-result');
        el.innerHTML = `
            <div class="preview-summary">
                <span class="chip">转出合计 <strong>${{fmtNum(data.source_total_remaining)}}</strong></span>
                <span class="chip">转入合计 <strong>${{fmtNum(data.candidate_total_remaining)}}</strong></span>
                <span class="chip">盈余 <strong>${{fmtNum(data.surplus)}}</strong></span>
                <span class="chip">业务日 <strong>${{escHtml(data.swap_business_date)}}</strong></span>
                <span class="chip">方案 <strong>${{escHtml(schemeLabel(data.scheme_id))}}</strong></span>
            </div>
            ${{renderPreviewAssetTable('转出资产明细（美好生活 → 美润1号）', data.out_assets, 'row-swap-out')}}
            ${{renderPreviewAssetTable('转入资产明细（美润1号 → 美好生活）', data.in_assets, 'row-swap-in')}}
            ${{renderMonitorByProduct(data)}}
            <p class="preview-note muted">${{escHtml(data.note || '')}}</p>`;
        el.style.display = 'block';
        syncPreviewMonitorScrolls(el);
    }}

    function schemeLabel(id) {{
        return SCHEME_LABELS[id] || id || '—';
    }}

    function statusLabel(st) {{
        return STATUS_LABELS[st] || st || '—';
    }}

    function renderOrdersTable(orders) {{
        const wrap = document.getElementById('orders-table-wrap');
        const empty = document.getElementById('orders-empty');
        const loading = document.getElementById('orders-loading');
        loading.style.display = 'none';
        if (!orders || !orders.length) {{
            wrap.style.display = 'none';
            empty.style.display = 'block';
            return;
        }}
        empty.style.display = 'none';
        let rows = '';
        orders.forEach((o) => {{
            const products = escHtml(o.source_trust_product_name) + ' ↔ ' + escHtml(o.counterparty_trust_product_name);
            const counts = (o.source_asset_count ?? '—') + ' / ' + (o.candidate_asset_count ?? '—');
            const voidBtn = o.can_void
                ? `<button type="button" class="btn-danger btn-sm order-void-btn" data-order-id="${{o.id}}">失效</button>`
                : `<span class="void-blocked" title="${{escHtml(o.void_block_reason || '')}}">不可失效</span>`;
            rows += `<tr data-order-id="${{o.id}}">
                <td>${{o.id}}</td>
                <td>${{escHtml(o.swap_business_date)}}</td>
                <td class="col-products">${{products}}</td>
                <td>${{escHtml(schemeLabel(o.scheme_id))}}</td>
                <td><span class="status-badge status-${{escHtml(o.status)}}">${{escHtml(statusLabel(o.status))}}</span></td>
                <td>${{counts}}</td>
                <td>${{escHtml(o.executed_at || '—')}}</td>
                <td class="col-actions">
                    <button type="button" class="btn-ghost btn-sm order-view-btn" data-order-id="${{o.id}}">查看详情</button>
                    ${{voidBtn}}
                </td>
            </tr>`;
        }});
        wrap.innerHTML = `<table class="swap-table swap-table-orders"><thead><tr>
            <th>ID</th><th>业务日</th><th>产品</th><th>方案</th><th>状态</th><th>转出/转入户</th><th>执行时间</th><th>操作</th>
        </tr></thead><tbody>${{rows}}</tbody></table>`;
        wrap.style.display = 'block';
        wrap.querySelectorAll('.order-view-btn').forEach((btn) => {{
            btn.addEventListener('click', () => loadOrderDetail(btn.getAttribute('data-order-id')));
        }});
        wrap.querySelectorAll('.order-void-btn').forEach((btn) => {{
            btn.addEventListener('click', () => voidOrder(btn.getAttribute('data-order-id')));
        }});
    }}

    async function loadOrders() {{
        const loading = document.getElementById('orders-loading');
        loading.style.display = 'block';
        loading.textContent = '加载中…';
        document.getElementById('orders-table-wrap').style.display = 'none';
        document.getElementById('orders-empty').style.display = 'none';
        try {{
            const resp = await fetch('/asset-swap/orders', {{ credentials: 'same-origin' }});
            const data = await readJsonResponse(resp);
            renderOrdersTable(Array.isArray(data) ? data : (data.items || []));
        }} catch (err) {{
            loading.style.display = 'block';
            loading.textContent = '加载失败：' + (err.message || '未知错误');
        }}
    }}

    function renderOrderDetail(order) {{
        const body = document.getElementById('order-detail-body');
        const voidInfo = order.can_void
            ? ''
            : `<p class="void-block-reason">${{escHtml(order.void_block_reason || '不可失效')}}</p>`;
        const note = order.note ? `<p class="muted">备注：${{escHtml(order.note)}}</p>` : '';
        body.innerHTML = `
            <div class="stat-chips">
                <span class="chip">ID <strong>${{order.id}}</strong></span>
                <span class="chip">业务日 <strong>${{escHtml(order.swap_business_date)}}</strong></span>
                <span class="chip">方案 <strong>${{escHtml(schemeLabel(order.scheme_id))}}</strong></span>
                <span class="chip">状态 <strong>${{escHtml(statusLabel(order.status))}}</strong></span>
                <span class="chip">执行 <strong>${{escHtml(order.executed_at || '—')}}</strong></span>
            </div>
            <p class="muted">${{escHtml(order.source_trust_product_name)}} ↔ ${{escHtml(order.counterparty_trust_product_name)}} · 转出 ${{order.source_asset_count}} 户 / 转入 ${{order.candidate_asset_count}} 户 · 合计 ${{fmtNum(order.source_total_remaining)}} / ${{fmtNum(order.candidate_total_remaining)}}</p>
            ${{note}}
            ${{voidInfo}}
            ${{renderPreviewAssetTable('转出资产明细', order.out_assets, 'row-swap-out')}}
            ${{renderPreviewAssetTable('转入资产明细', order.in_assets, 'row-swap-in')}}
            ${{renderMonitorByProduct(order)}}
        `;
        document.getElementById('order-detail-title').textContent = '置换单 #' + order.id;
        document.getElementById('order-detail-panel').style.display = 'block';
        syncPreviewMonitorScrolls(body);
    }}

    async function loadOrderDetail(orderId) {{
        try {{
            const resp = await fetch('/asset-swap/orders/' + encodeURIComponent(orderId), {{ credentials: 'same-origin' }});
            const data = await readJsonResponse(resp);
            renderOrderDetail(data);
        }} catch (err) {{
            showExecuteStatus('加载详情失败：' + (err.message || '未知错误'), 'error');
        }}
    }}

    async function voidOrder(orderId) {{
        if (!window.confirm('确认将该置换单 #' + orderId + ' 标记为失效？')) return;
        try {{
            const resp = await fetch('/asset-swap/orders/' + encodeURIComponent(orderId) + '/void', {{
                method: 'POST',
                credentials: 'same-origin',
                headers: {{ 'Content-Type': 'application/json' }},
                body: '{{}}',
            }});
            await readJsonResponse(resp);
            showExecuteStatus('置换单 #' + orderId + ' 已失效', 'success');
            if (document.getElementById('order-detail-panel').style.display !== 'none') {{
                document.getElementById('order-detail-panel').style.display = 'none';
            }}
            await loadOrders();
        }} catch (err) {{
            showExecuteStatus('失效失败：' + (err.message || '未知错误'), 'error');
        }}
    }}

    document.querySelectorAll('.scheme-tab').forEach(btn => {{
        btn.addEventListener('click', () => {{
            document.querySelectorAll('.scheme-tab').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const scheme = btn.getAttribute('data-scheme');
            ['a','b','c'].forEach(id => {{
                document.getElementById('scheme-panel-' + id).style.display = id === scheme ? 'block' : 'none';
            }});
        }});
    }});

    document.getElementById('clear-exclude-storage').addEventListener('click', (e) => {{
        e.preventDefault();
        document.getElementById('exclude_asset_codes').value = '';
        saveExcludeStorage('');
    }});

    document.getElementById('order-detail-close').addEventListener('click', () => {{
        document.getElementById('order-detail-panel').style.display = 'none';
    }});

    document.getElementById('swap_business_date').value = todayIso();
    document.getElementById('swap_business_date').addEventListener('change', invalidatePreview);
    document.getElementById('swap_note').addEventListener('input', invalidatePreview);

    loadExcludeStorage();
    loadOrders();

    document.getElementById('preview-swap-btn').addEventListener('click', async () => {{
        const payload = buildSwapPayload();
        if (!payload) {{ showExecuteStatus('请先选用一个推荐方案', 'error'); return; }}
        if (!payload.swap_business_date) {{ showExecuteStatus('请填写置换业务日', 'error'); return; }}
        const btn = document.getElementById('preview-swap-btn');
        btn.disabled = true;
        btn.textContent = '预览中…';
        showExecuteStatus('', null);
        try {{
            const resp = await fetch('/asset-swap/preview', {{
                method: 'POST',
                credentials: 'same-origin',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(payload),
            }});
            const data = await readJsonResponse(resp);
            renderPreviewResult(data);
            previewValid = true;
            lastPreviewPayloadKey = payloadKey(payload);
            document.getElementById('confirm-swap-btn').disabled = false;
            showExecuteStatus('预览成功，可确认置换', 'success');
        }} catch (err) {{
            invalidatePreview();
            showExecuteStatus('预览失败：' + (err.message || '未知错误'), 'error');
        }} finally {{
            btn.disabled = !selectedScheme;
            btn.textContent = '预览置换';
        }}
    }});

    document.getElementById('confirm-swap-btn').addEventListener('click', async () => {{
        const payload = buildSwapPayload();
        if (!payload || !previewValid) {{
            showExecuteStatus('请先成功预览置换', 'error');
            return;
        }}
        if (payloadKey(payload) !== lastPreviewPayloadKey) {{
            showExecuteStatus('表单或方案已变更，请重新预览', 'error');
            invalidatePreview();
            return;
        }}
        const msg = '确认执行置换？\\n业务日：' + payload.swap_business_date
            + '\\n转出 ' + payload.source_asset_codes.length + ' 户 · 转入 ' + payload.candidate_asset_codes.length + ' 户';
        if (!window.confirm(msg)) return;
        const btn = document.getElementById('confirm-swap-btn');
        btn.disabled = true;
        btn.textContent = '执行中…';
        showExecuteStatus('', null);
        try {{
            const resp = await fetch('/asset-swap/execute', {{
                method: 'POST',
                credentials: 'same-origin',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify(payload),
            }});
            const data = await readJsonResponse(resp);
            invalidatePreview();
            updateExecuteButtons();
            await loadOrders();
            showExecuteStatus('置换成功，单号 #' + (data.order_id ?? '—'), 'success');
        }} catch (err) {{
            showExecuteStatus('置换失败：' + (err.message || '未知错误'), 'error');
            if (previewValid) document.getElementById('confirm-swap-btn').disabled = false;
        }} finally {{
            btn.textContent = '确认置换';
        }}
    }});

    document.getElementById('swap-form').addEventListener('submit', async (e) => {{
        e.preventDefault();
        showFormError('');
        const btn = document.getElementById('swap-submit-btn');
        const pid = document.getElementById('trust_product_id').value;
        const codes = document.getElementById('asset_codes').value.trim();
        const required = document.getElementById('required_asset_codes').value.trim();
        const exclude = document.getElementById('exclude_asset_codes').value.trim();
        if (!codes) {{ showFormError('请输入至少一个资产主编号'); return; }}
        const reqList = parseCodeList(required);
        const exList = parseCodeList(exclude);
        const overlap = reqList.filter(c => exList.includes(c));
        if (overlap.length) {{
            showFormError('以下编号不能同时指定与排除：' + overlap.join('、'));
            return;
        }}
        const params = new URLSearchParams();
        params.set('trust_product_id', pid);
        parseCodeList(codes).forEach(c => params.append('asset_codes', c));
        reqList.forEach(c => params.append('required_asset_codes', c));
        exList.forEach(c => params.append('exclude_asset_codes', c));
        btn.disabled = true;
        btn.textContent = '查询中…';
        try {{
            const resp = await fetch('/asset-swap/data?' + params.toString(), {{ credentials: 'same-origin' }});
            const data = await readJsonResponse(resp);
            saveExcludeStorage(exclude);
            renderAll(data);
        }} catch (err) {{
            showFormError(err.message || '查询失败');
        }} finally {{
            btn.disabled = false;
            btn.textContent = '查询推荐';
        }}
    }});

    document.getElementById('asset_codes').addEventListener('keydown', (e) => {{
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {{
            document.getElementById('swap-form').requestSubmit();
        }}
    }});
    </script>
    """
    return _page_shell("资产置换", body)


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
        p.muted {{ color: #94a3b8; margin-bottom: 1rem; font-size: 0.9rem; }}
        .card {{
            background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px; padding: 1.25rem; margin-bottom: 1rem;
        }}
        .swap-grid {{
            display: grid;
            grid-template-columns: minmax(300px, 0.92fr) minmax(340px, 1.08fr);
            gap: 1rem;
            align-items: start;
        }}
        @media (max-width: 960px) {{
            .swap-grid {{ grid-template-columns: 1fr; }}
            .swap-input-row {{ grid-template-columns: 1fr; }}
            .execute-fields {{ grid-template-columns: 1fr; }}
        }}
        .panel h2 {{ font-size: 1.1rem; color: #e2e8f0; margin: 0 0 1rem; }}
        .swap-field {{ margin-bottom: 0.85rem; }}
        .swap-field label {{ display: block; color: #cbd5e1; font-size: 0.9rem; margin-bottom: 0.15rem; }}
        .swap-field-hint {{
            margin: 0 0 0.35rem;
            font-size: 0.78rem;
            color: #64748b;
            line-height: 1.35;
        }}
        .swap-field-hint a {{ color: #64748b; text-decoration: underline; }}
        .swap-input-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.75rem;
            margin-bottom: 0.5rem;
        }}
        .swap-textarea {{
            width: 100%;
            box-sizing: border-box;
            padding: 0.55rem 0.65rem;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.14);
            background: rgba(15, 23, 42, 0.55);
            color: #e2e8f0;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.85rem;
            line-height: 1.45;
            resize: vertical;
            transition: border-color 0.15s, box-shadow 0.15s;
        }}
        .swap-textarea-compact {{ min-height: 2.5rem; }}
        .swap-textarea::placeholder {{ color: #64748b; }}
        .swap-textarea:focus {{
            outline: none;
            border-color: rgba(59, 130, 246, 0.55);
            box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
        }}
        .swap-date-input, .swap-note-input {{
            width: 100%;
            box-sizing: border-box;
            padding: 0.55rem 0.65rem;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.14);
            background: rgba(15, 23, 42, 0.55);
            color: #e2e8f0;
            font-size: 0.9rem;
        }}
        .swap-date-input:focus, .swap-note-input:focus {{
            outline: none;
            border-color: rgba(59, 130, 246, 0.55);
            box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15);
        }}
        .summary-block {{ margin-top: 1rem; font-size: 0.88rem; color: #cbd5e1; }}
        .stat-chips {{ display: flex; flex-wrap: wrap; gap: 0.4rem 0.65rem; margin-bottom: 0.35rem; }}
        .stat-chips-sub {{ margin-bottom: 0; }}
        .chip {{
            display: inline-flex; align-items: center; gap: 0.25rem;
            padding: 0.2rem 0.55rem; border-radius: 6px;
            background: rgba(255,255,255,0.05); font-size: 0.82rem; color: #94a3b8;
        }}
        .chip strong {{ color: #e2e8f0; font-variant-numeric: tabular-nums; }}
        .chip-good {{ background: rgba(34,197,94,0.12); color: #86efac; }}
        .chip-good strong {{ color: #bbf7d0; }}
        .combo-chips {{ margin-bottom: 0.65rem; }}
        .table-wrap {{ margin-top: 0.75rem; overflow-x: hidden; }}
        .table-wrap-source {{ overflow-x: hidden; }}
        .orders-table-wrap {{ overflow-x: auto; }}
        .swap-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.82rem;
        }}
        .swap-table th,
        .swap-table td {{
            padding: 0.4rem 0.35rem;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            vertical-align: middle;
        }}
        .swap-table th {{
            color: #94a3b8;
            font-weight: 600;
            text-align: left;
            white-space: nowrap;
            font-size: 0.76rem;
        }}
        .swap-table tbody tr:hover {{ background: rgba(255,255,255,0.03); }}
        .swap-table-source {{ table-layout: fixed; }}
        .swap-table-source .src-code {{
            width: 26%; text-align: left;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.76rem; word-break: break-all;
        }}
        .swap-table-source .src-city {{
            width: 12%; text-align: center; white-space: nowrap;
            overflow: hidden; text-overflow: ellipsis;
        }}
        .swap-table-source .src-date {{ width: 15%; text-align: center; white-space: nowrap; font-size: 0.76rem; }}
        .swap-table-source .src-num {{ width: 17%; text-align: right; font-variant-numeric: tabular-nums; }}
        .swap-table-source .src-rate {{ width: 10%; text-align: right; white-space: nowrap; }}
        .swap-table-candidate {{ table-layout: fixed; }}
        .swap-table-candidate .col-idx {{ width: 1.6rem; text-align: center; }}
        .swap-table-candidate .col-code {{
            width: 15%; text-align: left;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.74rem; word-break: break-all;
        }}
        .swap-table-candidate .col-city {{
            width: 8%; text-align: center; white-space: nowrap;
            overflow: hidden; text-overflow: ellipsis; font-size: 0.76rem;
        }}
        .swap-table-candidate .col-custody {{
            width: 14%; text-align: left;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.74rem; word-break: break-all;
        }}
        .swap-table-candidate .col-date {{ width: 12%; text-align: center; white-space: nowrap; font-size: 0.74rem; }}
        .swap-table-candidate .col-num {{ width: 12%; text-align: right; font-variant-numeric: tabular-nums; }}
        .swap-table-candidate .col-rate {{ width: 8%; text-align: right; white-space: nowrap; }}
        .swap-table-candidate .col-bucket {{ width: 5%; text-align: center; }}
        .swap-table-candidate .col-overdue {{ width: 7%; text-align: right; white-space: nowrap; }}
        .swap-table-orders .col-products {{ max-width: 12rem; }}
        .swap-table-orders .col-actions {{ white-space: nowrap; }}
        .swap-table-preview .col-num {{ text-align: right; font-variant-numeric: tabular-nums; }}
        .pin-badge {{
            display: inline-block; margin-left: 0.25rem;
            padding: 0.05rem 0.3rem; border-radius: 4px; font-size: 0.65rem;
            background: rgba(59,130,246,0.25); color: #93c5fd; vertical-align: middle;
        }}
        .row-pinned {{ background: rgba(59,130,246,0.06); }}
        .meta-bar {{
            font-size: 0.85rem; color: #94a3b8; margin-bottom: 0.75rem;
            padding: 0.45rem 0.65rem; border-radius: 8px;
            background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.06);
        }}
        .meta-bar strong {{ color: #cbd5e1; }}
        .required-warn {{
            color: #fbbf24; font-size: 0.85rem; margin-bottom: 0.75rem;
            padding: 0.5rem 0.65rem; border-radius: 8px;
            background: rgba(251,191,36,0.1); border: 1px solid rgba(251,191,36,0.3);
            white-space: pre-line; line-height: 1.45;
        }}
        .form-error {{
            color: #fca5a5; font-size: 0.85rem; margin-bottom: 0.75rem;
            padding: 0.5rem 0.65rem; border-radius: 8px;
            background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.25);
            white-space: pre-line; line-height: 1.45;
        }}
        .scheme-tabs {{ display: flex; gap: 0.5rem; margin: 0.75rem 0; flex-wrap: wrap; }}
        .scheme-tab {{
            padding: 0.4rem 0.85rem; border-radius: 8px; border: 1px solid rgba(255,255,255,0.15);
            background: transparent; color: #cbd5e1; cursor: pointer;
        }}
        .scheme-tab.active {{
            background: rgba(59,130,246,0.25); border-color: rgba(59,130,246,0.5); color: #e2e8f0;
        }}
        .scheme-desc {{ color: #94a3b8; font-size: 0.85rem; margin-bottom: 0.75rem; }}
        .combo-card {{
            margin-bottom: 1rem; padding: 0.75rem;
            border: 1px solid rgba(255,255,255,0.08); border-radius: 8px;
            overflow-x: hidden; cursor: pointer;
            transition: border-color 0.15s, box-shadow 0.15s;
        }}
        .combo-card:hover {{
            border-color: rgba(59,130,246,0.35);
        }}
        .combo-card-selected {{
            border-color: rgba(59,130,246,0.65);
            box-shadow: 0 0 0 1px rgba(59,130,246,0.35);
            background: rgba(59,130,246,0.06);
        }}
        .combo-select-row {{
            display: flex; align-items: center; gap: 0.45rem;
            margin-top: 0.65rem; font-size: 0.88rem; color: #cbd5e1;
            cursor: pointer; user-select: none;
        }}
        .combo-select-row input {{ cursor: pointer; }}
        .warn {{ color: #fbbf24; font-size: 0.85rem; }}
        .scheme-panel h3 {{ font-size: 0.9rem; color: #cbd5e1; margin: 1rem 0 0.5rem; }}
        .execute-form {{ display: flex; flex-wrap: wrap; gap: 1rem; align-items: flex-end; justify-content: space-between; }}
        .execute-fields {{
            display: grid; grid-template-columns: 10rem 1fr; gap: 0.75rem; flex: 1; min-width: 240px;
        }}
        .execute-actions {{ display: flex; gap: 0.5rem; flex-wrap: wrap; }}
        .preview-result {{
            margin-top: 1rem; padding-top: 1rem;
            border-top: 1px solid rgba(255,255,255,0.08);
        }}
        .preview-summary {{
            display: flex; flex-wrap: wrap; gap: 0.4rem 0.65rem; margin-bottom: 0.75rem;
        }}
        .preview-section {{ margin-bottom: 1rem; }}
        .preview-section h4 {{ font-size: 0.9rem; color: #cbd5e1; margin: 0.75rem 0 0.45rem; }}
        .preview-monitor-title {{
            font-size: 1rem; color: #e2e8f0; margin: 1.25rem 0 0.35rem;
            padding-top: 0.75rem; border-top: 1px dashed rgba(148,163,184,0.25);
        }}
        .preview-monitor-hint {{ margin-bottom: 0.5rem; font-size: 0.82rem; }}
        .preview-legend {{
            display: flex; gap: 1rem; margin: 0 0 0.75rem; font-size: 0.85rem;
        }}
        .legend-out {{ color: #fb923c; font-weight: 600; }}
        .legend-in {{ color: #60a5fa; font-weight: 600; }}
        .preview-product-block {{
            margin-bottom: 1.25rem;
            padding: 0.75rem 0.85rem;
            border: 1px solid rgba(148,163,184,0.18);
            border-radius: 10px;
            background: rgba(15,23,42,0.35);
        }}
        .preview-product-title {{
            display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem;
            font-size: 0.95rem; color: #e2e8f0; margin: 0 0 0.55rem;
        }}
        .swap-table-preview tbody tr.row-swap-out td {{
            color: #fb923c;
        }}
        .swap-table-preview tbody tr.row-swap-in td {{
            color: #60a5fa;
        }}
        .preview-table-scroll {{
            overflow-x: auto;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            background: rgba(0,0,0,0.15);
        }}
        .swap-table-preview {{
            table-layout: auto;
            width: max-content;
            min-width: 100%;
            font-size: 0.78rem;
        }}
        .swap-table-preview th,
        .swap-table-preview td {{
            padding: 0.4rem 0.55rem;
            white-space: nowrap;
            vertical-align: middle;
        }}
        .swap-table-preview th {{
            position: sticky; top: 0;
            background: #1e293b;
            z-index: 1;
            text-align: left;
        }}
        .swap-table-preview .col-num,
        .swap-table-preview td.col-num {{
            text-align: right;
            font-variant-numeric: tabular-nums;
        }}
        .swap-table-preview .col-rate {{ text-align: right; }}
        .swap-table-preview .col-code,
        .swap-table-preview .col-custody {{
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.74rem;
        }}
        .swap-table-preview .col-flow {{ min-width: 11rem; }}
        .swap-table-preview .col-city {{ text-align: center; }}
        .swap-table-preview .col-date {{ text-align: center; }}
        .preview-note {{ margin-top: 0.75rem; font-size: 0.82rem; }}
        .execute-status {{
            margin-top: 0.75rem; font-size: 0.85rem; padding: 0.5rem 0.65rem; border-radius: 8px;
            white-space: pre-line; line-height: 1.45;
        }}
        .execute-status-success {{
            color: #86efac; background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.25);
        }}
        .execute-status-error {{
            color: #fca5a5; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.25);
        }}
        .orders-loading {{ font-size: 0.88rem; }}
        .order-detail-panel {{
            margin-top: 1rem; padding-top: 1rem;
            border-top: 1px solid rgba(255,255,255,0.1);
        }}
        .order-detail-header {{
            display: flex; align-items: center; justify-content: space-between;
            margin-bottom: 0.75rem;
        }}
        .order-detail-header h3 {{ margin: 0; font-size: 1rem; color: #e2e8f0; }}
        .void-blocked {{ font-size: 0.78rem; color: #64748b; }}
        .void-block-reason {{ color: #fbbf24; font-size: 0.85rem; }}
        .status-badge {{
            display: inline-block; padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.78rem;
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
            padding: 0.35rem 0.75rem; border-radius: 8px; border: 1px solid rgba(239,68,68,0.45);
            background: rgba(239,68,68,0.15); color: #fca5a5; cursor: pointer;
        }}
        .btn-danger:hover {{ background: rgba(239,68,68,0.25); color: #fecaca; }}
        .btn-primary:disabled, .btn-secondary:disabled {{ opacity: 0.6; cursor: not-allowed; }}
    </style>
</head>
<body>
    {body}
</body>
</html>"""
