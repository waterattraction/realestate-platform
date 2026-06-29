"""信托产品发行资产明细 — HTML 页面."""

from __future__ import annotations

from datetime import date
from html import escape

from app.ui_css import BTN_CSS, FORM_FIELD_CSS, PAGE_CHROME_CSS, STANDARD_HEADER_CSS, TABLE_SCROLL_CSS
from app import issuance_cleanse as ic
from app import issuance_labels as il
from app.import_ui_labels import (
    PREVIEW_BTN_EXCLUDE_CONFIRM,
    PREVIEW_BTN_SELECT_IMPORT,
    preview_script_helpers,
)


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
        h1 {{ font-size: 1.5rem; color: #f8fafc; margin: 0 0 0.5rem; }}
        p.muted {{ color: #94a3b8; margin-bottom: 1rem; font-size: 0.9rem; }}
        .card {{
            background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px; padding: 1.25rem; margin-bottom: 1rem;
        }}
        {TABLE_SCROLL_CSS}
        th, td {{ padding: 0.5rem 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.08); text-align: left; }}
        th {{ color: #94a3b8; }}
        .records-table {{ font-size: 0.85rem; }}
        .records-table th.col-num,
        .records-table td.col-num {{ text-align: right; }}
        .ok {{ color: #34d399; }} .warn {{ color: #fbbf24; }} .err {{ color: #f87171; }}
        .sheet-toolbar {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.75rem 0; }}
        .sheet-cb {{ width: auto; margin-right: 0.35rem; }}
        .sheet-confirm-cb {{ width: auto; margin-left: 0.5rem; }}
        tr.row-reject {{ opacity: 0.55; }}
        tr.row-needs_confirm {{ background: rgba(251,191,36,0.06); }}
        .import-bar {{ margin-top: 1rem; padding-top: 0.75rem; border-top: 1px solid rgba(255,255,255,0.08); }}
        .filters {{ display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: flex-end; }}
        .pager {{
            display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center;
            margin: 1rem 0; color: #94a3b8; font-size: 0.9rem;
        }}
        .pager-btn {{
            display: inline-block; padding: 0.4rem 1rem; border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.15); background: rgba(15,23,42,0.8);
            color: #f8fafc; text-decoration: none;
        }}
        a.pager-btn:hover {{ border-color: #38bdf8; color: #38bdf8; text-decoration: none; }}
        .pager-btn.disabled {{ opacity: 0.4; cursor: not-allowed; pointer-events: none; }}
        pre {{ white-space: pre-wrap; font-size: 0.8rem; color: #cbd5e1; }}
    </style>
</head>
<body>
<div class="container">{body}</div>
<script>
(function() {{
    var filterForm = document.getElementById('f');
    if (!filterForm || filterForm.method.toLowerCase() !== 'get') return;
    filterForm.addEventListener('submit', function(ev) {{
        ev.preventDefault();
        var params = new URLSearchParams();
        filterForm.querySelectorAll('input, select, textarea').forEach(function(el) {{
            if (!el.name || el.disabled) return;
            if (el.type === 'checkbox' && !el.checked) return;
            var val = (el.value || '').trim();
            if (val) params.set(el.name, val);
        }});
        var qs = params.toString();
        var action = filterForm.getAttribute('action') || window.location.pathname;
        window.location = action + (qs ? '?' + qs : '');
    }});
}})();
</script>
</body></html>"""


def render_upload_page(trust_products: list[dict]) -> str:
    options = "".join(
        f'<option value="{tp["id"]}">{escape(tp["name"])} (id={tp["id"]})</option>'
        for tp in trust_products
    )
    today = date.today().isoformat()
    body = f"""
    <nav class="breadcrumb"><a href="/">首页</a> / 发行资产明细导入</nav>
    <h1>信托产品发行资产明细导入</h1>
    <p class="muted">选择信托产品与发行日期，上传 Excel 后预检再导入。业务时间维度仅为发行日期。</p>
    <div class="card">
        <label>信托产品</label>
        <select id="trust_product_id" style="width:100%">{options}</select>
        <label>发行日期</label>
        <input type="date" id="issue_date" value="{today}" style="width:100%">
        <label>Excel 文件（可多选）</label>
        <input type="file" id="files" multiple accept=".xlsx,.xls" style="width:100%">
        <button type="button" class="btn-primary" onclick="runPreview()">预检</button>
    </div>
    <div class="card" id="result"><p class="muted">预检结果将显示在此处</p></div>
    <div class="card import-bar" id="importBar" style="display:none">
        <p class="muted">已选 <strong id="selCount">0</strong> 个 Sheet · 仅导入选中项</p>
        <button type="button" class="btn-primary" onclick="runImport()">确认导入选中 Sheet</button>
    </div>
    <script>
    {preview_script_helpers()}
    let batchUuid = null;
    let previewData = null;
    let confirmedKeys = new Set();

    async function runPreview() {{
        const fd = new FormData();
        fd.append('trust_product_id', document.getElementById('trust_product_id').value);
        fd.append('issue_date', document.getElementById('issue_date').value);
        for (const f of document.getElementById('files').files) fd.append('files', f);
        const res = await fetch('/issuance/preview', {{ method: 'POST', credentials: 'same-origin', body: fd }});
        const data = await res.json();
        batchUuid = data.batch_uuid || data.file_id;
        previewData = data;
        confirmedKeys = new Set();
        renderPreview(data, res.ok);
    }}

    function sheetKey(s) {{ return s.sheet_key || (s.file_name + '::' + s.sheet_name); }}

    function isSelectable(s) {{
        const st = s.status || s.action;
        return st === 'import' || st === 'needs_confirm' || s.action === 'overwrite';
    }}

    function isReject(s) {{
        const st = s.status || s.action;
        return st === 'reject' || s.action === 'failed' || st === 'skip';
    }}

    function canCheckSheet(s) {{
        if (isReject(s)) return false;
        if ((s.status || s.action) === 'needs_confirm' || s.action === 'needs_confirm') {{
            return confirmedKeys.has(sheetKey(s));
        }}
        return isSelectable(s);
    }}

    function toggleConfirm(key, checked) {{
        if (checked) confirmedKeys.add(key); else confirmedKeys.delete(key);
        const s = previewData.sheets.find(x => sheetKey(x) === key);
        const cb = document.querySelector('input.sheet-select[data-sheet-key="'+key+'"]');
        if (cb && s) {{
            cb.disabled = !canCheckSheet(s);
            if (!canCheckSheet(s)) cb.checked = false;
        }}
        updateSelCount();
    }}

    function toggleSheet(key, checked) {{ updateSelCount(); }}

    function selectedKeys() {{
        const keys = [];
        document.querySelectorAll('input.sheet-select:checked').forEach(el => keys.push(el.dataset.sheetKey));
        return keys;
    }}

    function updateSelCount() {{
        const el = document.getElementById('selCount');
        if (el) el.textContent = selectedKeys().length;
    }}

    function selectAllImport() {{
        document.querySelectorAll('input.sheet-select').forEach(el => {{
            const s = previewData.sheets.find(x => sheetKey(x) === el.dataset.sheetKey);
            if (!s) return;
            const st = s.status || s.action;
            if (st === 'import' || s.action === 'overwrite') {{
                el.checked = true;
                el.disabled = false;
            }}
        }});
        updateSelCount();
    }}

    function selectExcludeNeedsConfirm() {{
        document.querySelectorAll('input.sheet-select').forEach(el => {{
            const s = previewData.sheets.find(x => sheetKey(x) === el.dataset.sheetKey);
            if (!s) return;
            const st = s.status || s.action;
            if (st === 'import' || s.action === 'overwrite') {{
                el.checked = true;
                el.disabled = false;
            }} else {{
                el.checked = false;
            }}
        }});
        updateSelCount();
    }}

    async function runImport() {{
        if (!batchUuid) {{ alert('请先预检'); return; }}
        const keys = selectedKeys();
        if (!keys.length) {{ alert('必须选择至少一个 Sheet'); return; }}
        const body = {{
            file_id: batchUuid,
            batch_uuid: batchUuid,
            trust_product_id: parseInt(document.getElementById('trust_product_id').value),
            issue_date: document.getElementById('issue_date').value,
            selected_sheet_keys: keys,
            confirm_sheet_keys: [...confirmedKeys],
            confirm: true
        }};
        const res = await fetch('/issuance/import', {{
            method: 'POST',
            credentials: 'same-origin',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(body)
        }});
        const data = await res.json();
        const pre = document.createElement('pre');
        pre.textContent = JSON.stringify(data, null, 2);
        document.getElementById('result').after(pre);
        if (!res.ok) alert(data.detail || '导入失败');
    }}

    function renderPreview(data, ok) {{
        const sheets = data.sheets || [];
        const batchId = data.batch_uuid || data.file_id || '';
        let html = '<p class="' + (ok ? 'ok' : 'err') + '">发行日: ' + (data.issue_date || '') + ' · 批次 ID: ' + batchId + '</p>';
        html += '<div class="sheet-toolbar">';
        html += '<button type="button" class="btn-secondary" onclick="selectAllImport()">{PREVIEW_BTN_SELECT_IMPORT}</button>';
        html += '<button type="button" class="btn-secondary" onclick="selectExcludeNeedsConfirm()">{PREVIEW_BTN_EXCLUDE_CONFIRM}</button>';
        html += '</div>';
        html += '<div class="table-wrap"><table><tr><th>选</th><th>文件名</th><th>工作表</th><th>行数</th><th>金额合计</th><th>预检状态</th><th>说明</th></tr>';
        sheets.forEach(s => {{
            const key = sheetKey(s);
            const st = s.status || s.action || '—';
            const stLabel = importActionLabel(st);
            const rowCls = s.action === 'failed' ? 'row-reject' : (st === 'needs_confirm' ? 'row-needs_confirm' : '');
            const reject = isReject(s);
            const needsConfirm = st === 'needs_confirm' || s.action === 'needs_confirm';
            let cb = '';
            if (!reject) {{
                const disabled = needsConfirm && !confirmedKeys.has(key);
                cb = '<input type="checkbox" class="sheet-select sheet-cb" data-sheet-key="'+key+'"';
                cb += (disabled ? ' disabled' : '') + ' onchange="toggleSheet(\\''+key+'\\', this.checked)">';
                if (needsConfirm) {{
                    cb += '<br><label class="muted" style="font-size:0.75rem"><input type="checkbox" class="sheet-confirm-cb" onchange="toggleConfirm(\\''+key+'\\', this.checked)">二次确认</label>';
                }}
            }} else {{
                cb = '<span class="err">禁选</span>';
            }}
            html += '<tr class="'+rowCls+'"><td>'+cb+'</td>';
            html += '<td>'+s.file_name+'</td><td>'+s.sheet_name+'</td>';
            html += '<td>'+(s.rows ?? s.row_count ?? '—')+'</td><td>'+(s.amount ?? s.amount_sum ?? '—')+'</td>';
            html += '<td><span class="'+previewStatusClass(st)+'">'+stLabel+'</span></td>';
            html += '<td>'+(s.reason || '')+'</td></tr>';
        }});
        html += '</table></div>';
        document.getElementById('result').innerHTML = html;
        document.getElementById('importBar').style.display = sheets.length ? 'block' : 'none';
        updateSelCount();
    }}
    </script>
    """
    return _page_shell("发行资产明细导入", body)


def _filter_query_string(filters: dict, page: int | None = None) -> str:
    parts = []
    for key, val in filters.items():
        if val is not None and val != "":
            parts.append(f"{key}={escape(str(val))}")
    if page is not None:
        parts.append(f"page={page}")
    return "&".join(parts)


def render_records_page(
    filters: dict,
    data: dict,
    trust_products: list[dict] | None = None,
) -> str:
    selected_product_id = str(filters.get("trust_product_id") or "")
    product_options = '<option value="">全部</option>'
    for tp in trust_products or []:
        tid = str(tp["id"])
        sel = " selected" if tid == selected_product_id else ""
        product_options += (
            f'<option value="{escape(tid)}"{sel}>{escape(tp["name"])} (id={escape(tid)})</option>'
        )

    filter_fields = [
        ("trust_product_id", None),
        ("issue_date", "发行日期"),
        ("custody_asset_code", "托管房源号"),
        ("business_asset_key", "发行资产标识"),
        ("city", "城市"),
        ("source_file_name", "文件名"),
        ("source_sheet_name", "工作表名"),
        ("from_trust_product_name", "转出信托产品"),
    ]
    filter_inputs = f"""
        <div><label>信托产品</label>
        <select name="trust_product_id" form="f" style="width:100%">{product_options}</select></div>"""
    selected_migration = str(filters.get("migration_type") or "")
    migration_options = '<option value="">全部</option>'
    for val, label in ic.MIGRATION_TYPE_LABELS.items():
        sel = " selected" if val == selected_migration else ""
        migration_options += f'<option value="{escape(val)}"{sel}>{escape(label)}</option>'
    filter_inputs += f"""
        <div><label>迁移类型</label>
        <select name="migration_type" form="f" style="width:100%">{migration_options}</select></div>"""
    for key, label in filter_fields[1:]:
        val = escape(str(filters.get(key) or ""))
        filter_inputs += f"""
        <div><label>{label}</label>
        <input name="{key}" value="{val}" form="f"></div>"""

    rows = ""
    headers = ""
    if data.get("items"):
        sample = data["items"][0]
        keys = [k for k in il.COLUMN_ORDER if k in sample]
        extra = sorted(k for k in sample if k not in keys)
        keys = keys + extra
        headers = "".join(
            f'<th data-col="{escape(k)}">{escape(il.field_label(k))}</th>'
            for k in keys
        )
        for item in data["items"]:
            cells = ""
            for k in keys:
                display = il.format_cell(k, item.get(k))
                cls = "col-num" if k in il.NUMERIC_COLUMNS else ""
                class_attr = f' class="{cls}"' if cls else ""
                cells += f"<td{class_attr}>{escape(display)}</td>"
            rows += f"<tr>{cells}</tr>"

    page = int(data.get("page", 1) or 1)
    page_size = int(data.get("page_size", 50) or 50)
    total = int(data.get("total", 0) or 0)
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    if page > total_pages:
        page = total_pages

    list_path = "/issuance/records"
    data_path = "/issuance/records/data"
    filter_qs = _filter_query_string(filters)

    prev_btn = (
        f'<a class="pager-btn" href="{escape(list_path)}?{_filter_query_string(filters, page - 1)}">上一页</a>'
        if page > 1 else '<span class="pager-btn disabled">上一页</span>'
    )
    next_btn = (
        f'<a class="pager-btn" href="{escape(list_path)}?{_filter_query_string(filters, page + 1)}">下一页</a>'
        if page < total_pages else '<span class="pager-btn disabled">下一页</span>'
    )
    pager = f"""
    <div class="pager">
        <span>共 {total} 条</span>
        {prev_btn}
        <span>第 {page} / {total_pages} 页</span>
        {next_btn}
    </div>"""

    json_qs = f"{filter_qs}&page={page}" if filter_qs else f"page={page}"
    body = f"""
    <nav class="breadcrumb"><a href="/">首页</a> / <a href="/issuance/upload">发行导入</a> / 发行资产明细</nav>
    <h1>发行资产明细</h1>
    <div class="card filters">
        <form id="f" method="get" class="filters" style="width:100%">
            {filter_inputs}
            <div><button type="submit" class="btn-primary">筛选</button></div>
        </form>
    </div>
    {pager}
    <p class="muted"><a href="{escape(data_path)}?{json_qs}">JSON</a></p>
    <div class="card table-wrap">
        <table class="records-table"><thead><tr>{headers}</tr></thead>
        <tbody>{rows or f'<tr><td colspan="{len(il.COLUMN_ORDER)}">无数据</td></tr>'}</tbody></table>
    </div>
    {pager}
    """
    return _page_shell("发行资产明细", body)
