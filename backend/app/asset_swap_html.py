"""资产置换推荐页面."""

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
    <nav class="breadcrumb"><a href="/">首页</a> / 资产置换推荐</nav>
    <h1>资产置换推荐</h1>
    <p class="muted">只读推荐，不写入数据库。转出资产限美好生活系列产品；候选来自美润1号（M1 且未付天数 ≤ 25 天）。</p>

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
                    <p class="swap-field-hint">填写后必须进入推荐方案；未付超过 25 天仍可指定，查询结果会提示</p>
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
    </div>

    <script>
    const STORAGE_USER = '{storage_user}';
    const EXCLUDE_STORAGE_KEY = 'asset-swap:exclude:' + STORAGE_USER;
    const fmtNum = (v) => (v == null || v === '') ? '—' : Number(v).toLocaleString('zh-CN', {{minimumFractionDigits: 2, maximumFractionDigits: 2}});
    const parseCodeList = (text) => String(text || '')
        .split(/[\\r\\n,，;；\\s]+/)
        .map((s) => s.trim())
        .filter(Boolean);
    let lastData = null;

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
                <td class="src-code" title="${{a.asset_code}}">${{a.asset_code}}</td>
                <td class="src-city" title="${{city}}">${{city}}</td>
                <td class="src-date">${{a.issue_date}}</td>
                <td class="src-num">${{fmtNum(a.remaining_amount)}}</td>
                <td class="src-rate">${{a.asset_transfer_discount_rate_display}}</td>
                <td class="src-date">${{a.renovation_deadline}}</td>
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

    function renderCombo(combo, pinnedCodes) {{
        if (!combo) return '<p class="muted">无可行组合</p>';
        const pinned = pinnedCodes || new Set();
        let rows = '';
        (combo.assets || []).forEach((a, i) => {{
            const isPinned = a.pinned || pinned.has(a.asset_code);
            const city = a.city || '—';
            rows += `<tr class="${{isPinned ? 'row-pinned' : ''}}">
                <td class="col-idx">${{i + 1}}</td>
                <td class="col-code" title="${{a.asset_code}}">${{a.asset_code}}${{isPinned ? '<span class="pin-badge">指定</span>' : ''}}</td>
                <td class="col-city" title="${{city}}">${{city}}</td>
                <td class="col-custody" title="${{a.custody_asset_code || ''}}">${{a.custody_asset_code || '—'}}</td>
                <td class="col-num">${{fmtNum(a.remaining_amount)}}</td>
                <td class="col-rate">${{a.asset_transfer_discount_rate_display}}</td>
                <td class="col-date">${{a.last_renovation_payment_date}}</td>
                <td class="col-bucket">${{a.delinquency_bucket || '—'}}</td>
                <td class="col-overdue">${{a.overdue_days != null ? a.overdue_days + '天' : '—'}}</td>
            </tr>`;
        }});
        return `
            <div class="combo-card">
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
                    <th class="col-overdue">未付天数</th>
                </tr></thead><tbody>${{rows}}</tbody></table>
            </div>`;
    }}

    function pinnedSet(data) {{
        return new Set((data.required && data.required.asset_codes) || []);
    }}

    function renderSchemeA(data) {{
        const s = data.schemes.a;
        const ps = pinnedSet(data);
        let html = `<p class="scheme-desc">${{s.scheme_label}}${{s.min_asset_count ? ' · 最少 ' + s.min_asset_count + ' 户' : ''}}</p>`;
        if (!s.combinations || !s.combinations.length) {{
            html += '<p class="warn">未找到满足条件的组合</p>';
        }} else {{
            s.combinations.forEach(c => {{ html += renderCombo(c, ps); }});
        }}
        document.getElementById('scheme-panel-a').innerHTML = html;
    }}

    function renderSchemeB(data) {{
        const s = data.schemes.b;
        const ps = pinnedSet(data);
        let html = `<p class="scheme-desc">${{s.scheme_label}}（启发式）</p>`;
        if (!s.combinations || !s.combinations.length) {{
            html += '<p class="warn">未找到满足条件的组合</p>';
        }} else {{
            s.combinations.forEach(c => {{ html += renderCombo(c, ps); }});
        }}
        document.getElementById('scheme-panel-b').innerHTML = html;
    }}

    function renderSchemeC(data) {{
        const s = data.schemes.c;
        const ps = pinnedSet(data);
        let html = `<p class="scheme-desc">${{s.scheme_label}}</p>`;
        const blocks = [
            ['C1 · 最少户数', s.c1_min_count],
            ['C2 · 金额最贴近（≤3户）', s.c2_min_surplus],
            ['C3 · 加权成本最贴近', s.c3_best_cost_match],
        ];
        blocks.forEach(([title, combo]) => {{
            html += `<h3>${{title}}</h3>` + renderCombo(combo, ps);
        }});
        document.getElementById('scheme-panel-c').innerHTML = html;
    }}

    function renderAll(data) {{
        lastData = data;
        showFormError('');
        renderSource(data.source);
        const m = data.meta || {{}};
        const req = data.required || {{}};
        const maxOd = m.candidate_max_overdue_days ?? 25;
        let meta = `候选池 <strong>${{m.candidate_pool_size ?? 0}}</strong> 户 · 目标产品 <strong>${{m.target_product_name ?? ''}}</strong>`;
        meta += ` · 自动候选未付 ≤ <strong>${{maxOd}}</strong> 天`;
        if (req.asset_count) {{
            meta += ` · 指定 <strong>${{req.asset_count}}</strong> 户（${{fmtNum(req.total_remaining)}}）`;
        }}
        document.getElementById('meta-line').innerHTML = meta;
        const warnEl = document.getElementById('required-warn');
        const warns = req.overdue_warnings || [];
        if (warnEl) {{
            if (warns.length) {{
                warnEl.style.display = 'block';
                warnEl.textContent = '提示：必选房源未付天数超过 ' + maxOd + ' 天\\n' + warns.join('\\n');
            }} else {{
                warnEl.style.display = 'none';
                warnEl.textContent = '';
            }}
        }}
        renderSchemeA(data);
        renderSchemeB(data);
        renderSchemeC(data);
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

    loadExcludeStorage();

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
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || resp.statusText);
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
    return _page_shell("资产置换推荐", body)


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
            overflow-x: hidden;
        }}
        .warn {{ color: #fbbf24; font-size: 0.85rem; }}
        .scheme-panel h3 {{ font-size: 0.9rem; color: #cbd5e1; margin: 1rem 0 0.5rem; }}
        .btn-primary:disabled {{ opacity: 0.6; cursor: not-allowed; }}
    </style>
</head>
<body>
    {body}
</body>
</html>"""
