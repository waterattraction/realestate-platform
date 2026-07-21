"""Excel 导入 V2 — HTML 页面."""

from __future__ import annotations

from datetime import date, datetime, timezone
from html import escape
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from app.ui_css import BTN_CSS, FORM_FIELD_CSS, PAGE_CHROME_CSS, STANDARD_HEADER_CSS, TABLE_SCROLL_CSS
from app.import_ui_labels import (
    PREVIEW_BTN_EXCLUDE_CONFIRM,
    PREVIEW_BTN_SELECT_IMPORT,
    preview_script_helpers,
)
from app.issuance_labels import format_rate
from app.issuance_upload import ISSUANCE_CITY_UNKNOWN
from app.assetinfo_upload import MONITOR_DISCOUNT_RATE_NONE, MONITOR_SORT_COLUMNS

DISPLAY_TZ = ZoneInfo("Asia/Shanghai")


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
        .records-table td.col-num {{
            text-align: right;
        }}
        .records-table th.sortable {{
            cursor: pointer;
            user-select: none;
        }}
        .records-table th.sortable:hover {{ color: #e2e8f0; }}
        .records-table th.sortable.sort-asc::after {{ content: ' ▲'; font-size: 0.65rem; }}
        .records-table th.sortable.sort-desc::after {{ content: ' ▼'; font-size: 0.65rem; }}
        details.compat-filters summary {{ cursor: pointer; color: #cbd5e1; }}
        .ok {{ color: #34d399; }} .warn {{ color: #fbbf24; }} .err {{ color: #f87171; }}
        .snapshot-hint {{
            margin: 0.75rem 0 0;
            padding: 0.55rem 0.75rem;
            border-radius: 8px;
            font-size: 0.85rem;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .snapshot-hint.ok {{
            border-color: rgba(52,211,153,0.35);
            color: #a7f3d0;
        }}
        .snapshot-hint.warn {{
            border-color: rgba(251,191,36,0.35);
            color: #fde68a;
        }}
        .snapshot-toggle label {{
            display: flex;
            align-items: center;
            gap: 0.45rem;
            font-size: 0.9rem;
            color: #e2e8f0;
            cursor: pointer;
        }}
        .snapshot-toggle input {{
            width: auto;
            margin: 0;
        }}
        .sheet-toolbar {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.75rem 0; }}
        .sheet-cb {{ width: auto; margin-right: 0.35rem; }}
        .sheet-confirm-cb {{ width: auto; margin-left: 0.5rem; }}
        tr.row-reject {{ opacity: 0.55; }}
        tr.row-needs_confirm {{ background: rgba(251,191,36,0.06); }}
        .import-bar {{ margin-top: 1rem; padding-top: 0.75rem; border-top: 1px solid rgba(255,255,255,0.08); }}
        .upload-field-product {{ max-width: 22rem; }}
        .file-list {{
            margin: 0.5rem 0 0.75rem;
            padding: 0.55rem 0.75rem;
            border-radius: 8px;
            background: rgba(15,23,42,0.45);
            border: 1px solid rgba(255,255,255,0.1);
            font-size: 0.85rem;
            color: #cbd5e1;
        }}
        .file-list ul {{ margin: 0.35rem 0 0; padding-left: 1.1rem; }}
        .file-list li {{ margin: 0.15rem 0; word-break: break-all; }}
        .import-summary {{ font-size: 0.9rem; color: #e2e8f0; }}
        .import-summary h3 {{ margin: 0 0 0.5rem; font-size: 1rem; color: #f8fafc; }}
        .import-summary ul {{ margin: 0.35rem 0 0.75rem; padding-left: 1.2rem; }}
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
        .pager-btn.disabled {{
            opacity: 0.4; cursor: not-allowed; pointer-events: none;
        }}
        details.compat-filters {{
            margin-top: 0.75rem;
            font-size: 0.85rem;
            color: #94a3b8;
        }}
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
    body = f"""
    <nav class="breadcrumb"><a href="/">首页</a> / 资产情况 / 资产数据导入</nav>
    <h1>资产数据导入</h1>
    <p class="muted">先预检，再确认导入。仅导入勾选的 Sheet；映射规则以预检类型为准。</p>
    <div class="card">
        <label>信托产品</label>
        <select id="trust_product_id" class="upload-field-product">{options}</select>
        <label>Excel 文件（可多选）</label>
        <input type="file" id="files" multiple accept=".xlsx,.xls">
        <div class="file-list" id="fileList"><span class="muted">未选择任何文件</span></div>
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

    function updateFileList() {{
        const input = document.getElementById('files');
        const box = document.getElementById('fileList');
        if (!input || !box) return;
        const files = Array.from(input.files || []);
        if (!files.length) {{
            box.innerHTML = '<span class="muted">未选择任何文件</span>';
            return;
        }}
        let html = '<strong>已选 ' + files.length + ' 个文件</strong><ul>';
        files.forEach(f => {{
            html += '<li>' + escapeHtml(f.name) + ' <span class="muted">(' + formatFileSize(f.size) + ')</span></li>';
        }});
        html += '</ul>';
        box.innerHTML = html;
    }}

    function escapeHtml(s) {{
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }}

    function formatFileSize(n) {{
        if (n < 1024) return n + ' B';
        if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
        return (n / (1024 * 1024)).toFixed(1) + ' MB';
    }}

    document.getElementById('files').addEventListener('change', updateFileList);

    async function runPreview() {{
        const fd = new FormData();
        fd.append('trust_product_id', document.getElementById('trust_product_id').value);
        for (const f of document.getElementById('files').files) fd.append('files', f);
        const res = await fetch('/assetinfo/preview', {{ method: 'POST', credentials: 'same-origin', body: fd }});
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
        return st === 'reject' || s.action === 'failed' || st === 'skip' || s.action === 'skip';
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

    function toggleSheet(key, checked) {{
        updateSelCount();
    }}

    function selectedKeys() {{
        const keys = [];
        document.querySelectorAll('input.sheet-select:checked').forEach(el => keys.push(el.dataset.sheetKey));
        return keys;
    }}

    function updateSelCount() {{
        const n = selectedKeys().length;
        const el = document.getElementById('selCount');
        if (el) el.textContent = n;
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

    function renderImportResult(data, ok, selectedKeysList) {{
        const selectedSet = new Set(selectedKeysList || []);
        const allResults = data.sheet_results || [];
        const scoped = allResults.filter(s => selectedSet.has(sheetKey(s)));
        const types = new Set(scoped.map(s => s.sheet_type || s.type).filter(Boolean));

        let html = '<div class="import-summary">';
        html += '<h3 class="' + (ok ? 'ok' : 'err') + '">' + (ok ? '导入完成' : '导入失败') + '</h3>';
        html += '<p class="muted">批次 ' + escapeHtml(String(data.batch_uuid || data.file_id || '—'));
        html += ' · 产品 ' + escapeHtml(String(data.trust_product_name || data.trust_product_id || '—'));
        html += ' · 本次选中 ' + scoped.length + ' 个 Sheet</p>';

        html += '<ul>';
        if (types.has('repayment_detail')) {{
            html += '<li>还款明细写入 <strong>' + (data.inserted_repayment_count ?? 0) + '</strong> 行</li>';
        }}
        if (types.has('repayment_plan')) {{
            html += '<li>回款计划写入 <strong>' + (data.inserted_repayment_plan_count ?? 0) + '</strong> 行</li>';
        }}
        if (types.has('asset_monitor')) {{
            html += '<li>监控快照写入 <strong>' + (data.inserted_monitor_count ?? 0) + '</strong> 行</li>';
        }}
        if (scoped.length) {{
            html += '<li>资产 upsert <strong>' + (data.upsert_asset_count ?? 0) + '</strong></li>';
        }}
        const scopedFailed = scoped.filter(s => (s.final_action || '') === 'failed').length;
        const scopedSkipped = scoped.filter(s => (s.final_action || '') === 'skipped' || (s.final_action || '') === 'skip').length;
        if (scopedFailed) html += '<li class="err">失败 Sheet <strong>' + scopedFailed + '</strong></li>';
        if (scopedSkipped) html += '<li class="warn">跳过 Sheet <strong>' + scopedSkipped + '</strong></li>';
        html += '</ul>';

        if (types.has('asset_monitor') && data.risk_recalc_hint) {{
            html += '<p class="snapshot-hint warn">' + escapeHtml(data.risk_recalc_hint) + '</p>';
        }}

        const scopedWarns = [];
        scoped.forEach(s => {{
            (s.quality_warnings || []).forEach(w => scopedWarns.push(w));
        }});
        if (types.has('asset_monitor') && (data.quality_warnings || []).length && !scopedWarns.length) {{
            (data.quality_warnings || []).forEach(w => scopedWarns.push(w));
        }}
        if (scopedWarns.length) {{
            html += '<p class="warn">质量提示</p><ul>';
            scopedWarns.slice(0, 30).forEach(w => {{ html += '<li>' + escapeHtml(w) + '</li>'; }});
            if (scopedWarns.length > 30) html += '<li class="muted">…另有 ' + (scopedWarns.length - 30) + ' 条</li>';
            html += '</ul>';
        }}

        html += '<div class="table-wrap"><table><tr><th>文件名</th><th>工作表</th><th>类型</th><th>结果</th><th>写入行数</th><th>说明</th></tr>';
        scoped.forEach(s => {{
            const st = s.final_action || s.action || '—';
            const typeLabel = sheetTypeLabel(s.type || s.sheet_type || '—');
            html += '<tr>';
            html += '<td>' + escapeHtml(s.file_name || '') + '</td>';
            html += '<td>' + escapeHtml(s.sheet_name || '') + '</td>';
            html += '<td>' + typeLabel + '</td>';
            html += '<td><span class="' + previewStatusClass(st) + '">' + importActionLabel(st) + '</span></td>';
            html += '<td>' + (s.inserted != null ? s.inserted : '—') + '</td>';
            html += '<td>' + escapeHtml(s.reason || '') + '</td>';
            html += '</tr>';
        }});
        html += '</table></div></div>';

        const box = document.getElementById('result');
        box.innerHTML = html;
        document.getElementById('importBar').style.display = 'none';
    }}

    async function runImport() {{
        if (!batchUuid) {{ alert('请先预检'); return; }}
        const keys = selectedKeys();
        if (!keys.length) {{ alert('必须选择至少一个 Sheet'); return; }}
        const confirmKeys = [...confirmedKeys];
        const body = {{
            file_id: batchUuid,
            batch_uuid: batchUuid,
            trust_product_id: parseInt(document.getElementById('trust_product_id').value),
            selected_sheet_keys: keys,
            confirm_sheet_keys: confirmKeys,
            confirm: true
        }};
        const res = await fetch('/assetinfo/import', {{
            method: 'POST',
            credentials: 'same-origin',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(body)
        }});
        const data = await res.json();
        if (!res.ok) {{
            alert(data.detail || '导入失败');
            renderImportResult(data, false, keys);
            return;
        }}
        renderImportResult(data, true, keys);
    }}

    function renderPreview(data, ok) {{
        const sheets = data.sheets || [];
        const batchId = data.batch_uuid || data.file_id || '';
        let html = '<p class="' + (ok ? 'ok' : 'err') + '">批次 ID: ' + batchId + '</p>';
        html += '<div class="sheet-toolbar">';
        html += '<button type="button" class="btn-secondary" onclick="selectAllImport()">{PREVIEW_BTN_SELECT_IMPORT}</button>';
        html += '<button type="button" class="btn-secondary" onclick="selectExcludeNeedsConfirm()">{PREVIEW_BTN_EXCLUDE_CONFIRM}</button>';
        html += '</div>';
        html += '<div class="table-wrap"><table><tr><th>选</th><th>文件名</th><th>工作表</th><th>类型</th><th>行数</th><th>金额合计</th><th>预检状态</th><th>说明</th></tr>';
        sheets.forEach(s => {{
            const key = sheetKey(s);
            const st = s.status || s.action || '—';
            const stLabel = importActionLabel(st);
            const rowCls = st === 'reject' || s.action === 'failed' ? 'row-reject' : (st === 'needs_confirm' ? 'row-needs_confirm' : '');
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
            let reasonCell = s.reason || '';
            if (s.sheet_type === 'ambiguous_sheet_type') {{
                reasonCell = '名称识别：' + sheetTypeLabel(s.name_type || '') + ' / 表头：' + sheetTypeLabel(s.header_type || '');
            }}
            const typeRaw = s.type || s.sheet_type || '—';
            const typeLabel = sheetTypeLabel(typeRaw);
            html += '<tr class="'+rowCls+'"><td>'+cb+'</td>';
            html += '<td>'+s.file_name+'</td><td>'+s.sheet_name+'</td><td>'+typeLabel+'</td>';
            html += '<td>'+(s.rows ?? s.row_count ?? '—')+'</td><td>'+(s.amount ?? s.amount_sum ?? '—')+'</td>';
            html += '<td><span class="'+previewStatusClass(st)+'">'+stLabel+'</span></td>';
            html += '<td>'+reasonCell+'</td></tr>';
        }});
        html += '</table></div>';
        document.getElementById('result').innerHTML = html;
        document.getElementById('importBar').style.display = sheets.length ? 'block' : 'none';
        updateSelCount();
    }}
    </script>
    """
    return _page_shell("数据导入 V2", body)


def _filter_query_string(filters: dict, page: int | None = None) -> str:
    params: dict[str, str] = {}
    for key, val in filters.items():
        if key == "include_history":
            if val:
                params["include_history"] = "1"
            continue
        if key in ("sort_by", "sort_dir") and val:
            params[key] = str(val)
            continue
        if key == "asset_transfer_discount_rate" and val is not None and val != "":
            params[key] = str(val)
            continue
        if val is not None and val != "":
            params[key] = str(val)
    if page is not None:
        params["page"] = str(page)
    return urlencode(params)


MONITOR_SORTABLE_COLUMNS = frozenset(MONITOR_SORT_COLUMNS.keys())

RECORD_COLUMN_LABELS: dict[str, str] = {
    "custody_asset_code": "托管房源号",
    "source_asset_code": "资产分笔号",
    "asset_code": "资产主编号",
    "trust_product_name": "信托产品",
    "trust_product_id": "产品ID",
    "data_date": "数据日期",
    "repayment_date": "还款日期",
    "period_no": "期数",
    "actual_repayment_amount": "当期实际还款金额",
    "asset_pool_code": "资产包编号",
    "current_payer": "当前还款方",
    "planned_repayment_amount": "当期计划还款金额",
    "initial_renovation_amount": "初始受让装修金额",
    "cumulative_repaid_amount": "累计已还款金额",
    "remaining_balance": "剩余应还款余额",
    "initial_transfer_amount": "初始受让金额",
    "repaid_amount": "已还款金额",
    "remaining_amount": "剩余还款金额",
    "overdue_days": "逾期天数",
    "asset_transfer_discount_rate": "资产转让折扣率(%)",
    "last_renovation_payment_date": "最后一期装修款付款时间",
    "renovation_vendor": "装修服务商",
    "asset_status": "资产状态",
    "community_name": "小区名称",
    "city": "城市",
    "collection_contract_code": "收房合同编码",
    "custody_agreement_sign_date": "托管协议签署日期",
    "collection_contract_years": "收房合同签约年数",
    "owner_code": "业主代码",
    "withholding_ratio": "代扣比例",
    "actual_monthly_rent": "实际出房月租金",
    "current_bill_date": "当期账单日",
    "repayment_amount_detail": "回款金额明细",
    "planned_monthly_repayment_amount": "后续计划每月回款金额",
    "final_planned_repayment_amount": "最后一期计划回款金额",
    "source_file_name": "文件名",
    "source_sheet_name": "Sheet名",
    "synced_at": "同步时间",
    "created_at": "创建时间",
    "id": "ID",
    "trust_asset_id": "资产ID",
    "risk_score": "风险评分",
    "risk_level": "风险等级",
    "last_payment_date": "最后回款日",
    "max_payment_date": "最大回款日",
}

MONITOR_COLUMN_LABELS: dict[str, str] = {
    **RECORD_COLUMN_LABELS,
    "source_asset_code": "资产编号(房源)",
}

REPAYMENT_PLAN_COLUMN_LABELS: dict[str, str] = {
    **RECORD_COLUMN_LABELS,
    "source_asset_code": "资产编号(房源)",
    "data_date": "统计日期",
}

REPAYMENT_COLUMN_ORDER: tuple[str, ...] = (
    "trust_product_name",
    "current_payer",
    "custody_asset_code",
    "asset_code",
    "planned_repayment_amount",
    "initial_renovation_amount",
    "cumulative_repaid_amount",
    "remaining_balance",
    "actual_repayment_amount",
    "repayment_date",
    "period_no",
    "data_date",
    "source_file_name",
    "source_sheet_name",
    "synced_at",
    "created_at",
    "id",
    "trust_product_id",
    "trust_asset_id",
)

REPAYMENT_PLAN_COLUMN_ORDER: tuple[str, ...] = (
    "trust_product_name",
    "asset_code",
    "custody_asset_code",
    "renovation_vendor",
    "data_date",
    "initial_transfer_amount",
    "repaid_amount",
    "remaining_amount",
    "community_name",
    "city",
    "current_bill_date",
    "repayment_amount_detail",
    "planned_monthly_repayment_amount",
    "final_planned_repayment_amount",
    "source_file_name",
    "source_sheet_name",
    "synced_at",
    "created_at",
    "id",
    "trust_product_id",
    "trust_asset_id",
)

MONITOR_COLUMN_ORDER: tuple[str, ...] = (
    "trust_product_name",
    "asset_code",
    "custody_asset_code",
    "renovation_vendor",
    "data_date",
    "initial_transfer_amount",
    "repaid_amount",
    "remaining_amount",
    "asset_status",
    "last_renovation_payment_date",
    "community_name",
    "city",
    "collection_contract_code",
    "custody_agreement_sign_date",
    "collection_contract_years",
    "owner_code",
    "withholding_ratio",
    "actual_monthly_rent",
    "overdue_days",
    "asset_transfer_discount_rate",
    "source_file_name",
    "source_sheet_name",
    "synced_at",
    "created_at",
    "last_payment_date",
    "max_payment_date",
    "risk_score",
    "risk_level",
    "id",
    "trust_product_id",
    "trust_asset_id",
)

RECORD_COLUMN_ORDERS: dict[str, tuple[str, ...]] = {
    "repayment": REPAYMENT_COLUMN_ORDER,
    "repayment_plan": REPAYMENT_PLAN_COLUMN_ORDER,
    "monitor": MONITOR_COLUMN_ORDER,
}

RECORD_NUMERIC_COLUMNS: frozenset[str] = frozenset({
    "trust_product_id",
    "id",
    "trust_asset_id",
    "actual_repayment_amount",
    "initial_transfer_amount",
    "repaid_amount",
    "remaining_amount",
    "planned_repayment_amount",
    "initial_renovation_amount",
    "cumulative_repaid_amount",
    "remaining_balance",
    "planned_monthly_repayment_amount",
    "final_planned_repayment_amount",
    "overdue_days",
    "risk_score",
    "asset_transfer_discount_rate",
    "withholding_ratio",
    "actual_monthly_rent",
    "collection_contract_years",
})

RECORD_DATE_ONLY_COLUMNS: frozenset[str] = frozenset({
    "data_date",
    "repayment_date",
    "last_payment_date",
    "max_payment_date",
    "last_renovation_payment_date",
    "custody_agreement_sign_date",
    "current_bill_date",
})

RECORD_TIMESTAMP_COLUMNS: frozenset[str] = frozenset({
    "synced_at",
    "created_at",
})


def _parse_datetime_value(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    text = str(value).strip()
    if not text or text == "—":
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_timestamptz_for_display(value) -> str:
    dt = _parse_datetime_value(value)
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(DISPLAY_TZ).strftime("%Y-%m-%d %H:%M")


def _format_date_for_display(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    if not text or text == "—":
        return "—"
    return text[:10]


def _format_cell_display(key: str, value) -> str:
    if value is None:
        return "—"
    if key == "asset_transfer_discount_rate":
        return format_rate(value)
    if key == "city":
        text = str(value).strip() if value is not None else ""
        return text if text else "—"
    if key in RECORD_TIMESTAMP_COLUMNS:
        return _format_timestamptz_for_display(value)
    if key in RECORD_DATE_ONLY_COLUMNS:
        return _format_date_for_display(value)
    return str(value)


def _record_col_class(key: str) -> str:
    classes: list[str] = []
    if key == "trust_product_name":
        classes.append("col-trust-product")
    elif key == "custody_asset_code":
        classes.append("col-custody")
    elif key == "source_asset_code":
        classes.append("col-source-split")
    elif key == "asset_code":
        classes.append("col-asset-code")
    elif key == "source_file_name":
        classes.append("col-source-file-name")
    elif key == "source_sheet_name":
        classes.append("col-source-sheet-name")
    elif key in RECORD_TIMESTAMP_COLUMNS:
        classes.append("col-timestamp")
    elif key in RECORD_DATE_ONLY_COLUMNS:
        classes.append("col-date")
    elif key in ("id", "trust_product_id", "trust_asset_id"):
        classes.append("col-id")
    if key in RECORD_NUMERIC_COLUMNS:
        classes.append("col-num")
    return " ".join(classes)


def _ordered_record_keys(keys: list[str], record_type: str) -> list[str]:
    order = RECORD_COLUMN_ORDERS.get(record_type, ())
    preferred = [k for k in order if k in keys]
    rest = sorted(k for k in keys if k not in preferred)
    return preferred + rest


def _record_column_label(key: str, record_type: str = "repayment") -> str:
    if record_type == "monitor":
        return MONITOR_COLUMN_LABELS.get(key, RECORD_COLUMN_LABELS.get(key, key))
    if record_type == "repayment_plan":
        return REPAYMENT_PLAN_COLUMN_LABELS.get(key, RECORD_COLUMN_LABELS.get(key, key))
    return RECORD_COLUMN_LABELS.get(key, key)


def _render_record_header(
    key: str,
    record_type: str = "repayment",
    *,
    sort_by: str | None = None,
    sort_dir: str | None = None,
) -> str:
    label = _record_column_label(key, record_type)
    cls = _record_col_class(key)
    if record_type == "monitor" and key in MONITOR_SORTABLE_COLUMNS:
        sort_cls = "sortable"
        if sort_by == key and sort_dir in ("asc", "desc"):
            sort_cls += f" sort-{sort_dir}"
        parts = [sort_cls]
        if cls:
            parts.append(cls)
        class_attr = f' class="{" ".join(parts)}"'
        return (
            f'<th{class_attr} data-col="{escape(key)}" data-sort-key="{escape(key)}" '
            f'title="点击排序">{escape(label)}</th>'
        )
    class_attr = f' class="{cls}"' if cls else ""
    return f'<th{class_attr} data-col="{escape(key)}">{escape(label)}</th>'


def _cell_display(key: str, value) -> str:
    return _format_cell_display(key, value)


def _render_source_file_name_cell(value) -> str:
    display = _cell_display("source_file_name", value)
    cls = _record_col_class("source_file_name")
    return f'<td class="{cls}" data-col="source_file_name">{escape(display)}</td>'


def _render_source_sheet_name_cell(value) -> str:
    display = _cell_display("source_sheet_name", value)
    cls = _record_col_class("source_sheet_name")
    return f'<td class="{cls}" data-col="source_sheet_name">{escape(display)}</td>'


def _render_record_cell(key: str, value) -> str:
    if key == "source_file_name":
        return _render_source_file_name_cell(value)
    if key == "source_sheet_name":
        return _render_source_sheet_name_cell(value)

    display = _cell_display(key, value)
    cls = _record_col_class(key)
    class_attr = f' class="{cls}"' if cls else ""
    return f'<td{class_attr} data-col="{escape(key)}">{escape(display)}</td>'


def render_records_page(
    title: str,
    data_path: str,
    filters: dict,
    data: dict,
    trust_products: list[dict] | None = None,
    record_type: str = "repayment",
    discount_rate_options: list[dict[str, str]] | None = None,
    city_options: list[str] | None = None,
) -> str:
    selected_product_id = str(filters.get("trust_product_id") or "")
    product_options = '<option value="">全部</option>'
    for tp in trust_products or []:
        tid = str(tp["id"])
        sel = ' selected' if tid == selected_product_id else ''
        product_options += (
            f'<option value="{escape(tid)}"{sel}>{escape(tp["name"])} (id={escape(tid)})</option>'
        )

    filter_inputs = f"""
        <div><label>信托产品</label>
        <select name="trust_product_id" form="f" style="width:100%">{product_options}</select></div>"""

    data_date_label = "统计日期" if record_type == "repayment_plan" else "数据日期"
    field_specs = [
        ("data_date", data_date_label, "date", False),
        ("asset_code", "资产主编号", "text", True),
        ("custody_asset_code", "托管房源号", "text", True),
        ("source_file_name", "文件名", "text", True),
        ("source_sheet_name", "Sheet名", "text", True),
    ]
    for key, label, input_type, fuzzy in field_specs:
        val = escape(str(filters.get(key) or ""))
        placeholder = ' placeholder="模糊匹配"' if fuzzy else ""
        filter_inputs += f"""
        <div><label>{label}</label>
        <input type="{input_type}" name="{key}" value="{val}" form="f"{placeholder}></div>"""

    snapshot_banner = ""
    if record_type == "monitor":
        include_history = bool(filters.get("include_history"))
        history_checked = " checked" if include_history else ""
        view_mode = data.get("view_mode") or (
            "history" if include_history else ("fixed_date" if filters.get("data_date") else "latest_effective")
        )
        if view_mode == "latest_effective":
            snapshot_banner = (
                '<p class="snapshot-hint ok">当前有效快照层：每个资产仅展示最新 data_date 记录</p>'
            )
        elif view_mode == "fixed_date":
            snapshot_banner = (
                f'<p class="snapshot-hint">已按指定数据日期筛选：{escape(str(filters.get("data_date")))}</p>'
            )
        else:
            snapshot_banner = (
                '<p class="snapshot-hint warn">历史快照模式：同一资产可能出现在多个 data_date 下</p>'
            )
        filter_inputs += f"""
        <div class="snapshot-toggle">
            <label>
                <input type="checkbox" name="include_history" value="1" form="f"{history_checked}>
                查看历史快照
            </label>
        </div>"""
        transferred_val = str(filters.get("transferred") or "")
        transferred_disabled = "" if selected_product_id else " disabled"
        transferred_hint = (
            '<span class="muted" style="font-size:12px">须先选择信托产品</span>'
            if not selected_product_id
            else ""
        )
        filter_inputs += f"""
        <div><label>已转让</label>
        <select name="transferred" id="transferred-filter" form="f" style="width:100%"{transferred_disabled}>
            <option value="">全部</option>
            <option value="yes"{" selected" if transferred_val == "yes" else ""}>是</option>
            <option value="no"{" selected" if transferred_val == "no" else ""}>否</option>
        </select>
        {transferred_hint}
        </div>
        <script>
        (function() {{
            var productSelect = document.querySelector('select[name="trust_product_id"]');
            var transferredSelect = document.getElementById('transferred-filter');
            if (!productSelect || !transferredSelect) return;
            function syncTransferredFilter() {{
                var hasProduct = !!productSelect.value;
                transferredSelect.disabled = !hasProduct;
                if (!hasProduct) transferredSelect.value = '';
            }}
            productSelect.addEventListener('change', syncTransferredFilter);
            syncTransferredFilter();
        }})();
        </script>"""
        discount_val = str(filters.get("asset_transfer_discount_rate") or "")
        discount_options = '<option value="">全部</option>'
        none_sel = " selected" if discount_val == MONITOR_DISCOUNT_RATE_NONE else ""
        discount_options += f'<option value="{MONITOR_DISCOUNT_RATE_NONE}"{none_sel}>未录入</option>'
        for opt in discount_rate_options or []:
            val = escape(opt["value"])
            sel = " selected" if discount_val == opt["value"] else ""
            discount_options += f'<option value="{val}"{sel}>{escape(opt["label"])}</option>'
        filter_inputs += f"""
        <div><label>资产转让折扣率(%)</label>
        <select name="asset_transfer_discount_rate" form="f" style="width:100%">{discount_options}</select></div>"""
        selected_city = str(filters.get("city") or "")
        city_select = '<option value="">全部</option>'
        for city_name in city_options or [ISSUANCE_CITY_UNKNOWN]:
            sel = " selected" if city_name == selected_city else ""
            city_select += f'<option value="{escape(city_name)}"{sel}>{escape(city_name)}</option>'
        filter_inputs += f"""
        <div><label>城市</label>
        <select name="city" form="f" style="width:100%">{city_select}</select></div>"""

    sort_by = filters.get("sort_by")
    sort_dir = filters.get("sort_dir")
    rows = ""
    headers = ""
    if data.get("items"):
        keys = _ordered_record_keys(list(data["items"][0].keys()), record_type)
        headers = "".join(
            _render_record_header(
                k,
                record_type,
                sort_by=sort_by if record_type == "monitor" else None,
                sort_dir=sort_dir if record_type == "monitor" else None,
            )
            for k in keys
        )
        for item in data.get("items", []):
            cells = "".join(_render_record_cell(k, item.get(k)) for k in keys)
            rows += f"<tr>{cells}</tr>"
    else:
        rows = ""

    page = int(data.get("page", 1) or 1)
    page_size = int(data.get("page_size", 50) or 50)
    total = int(data.get("total", 0) or 0)
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    if page > total_pages:
        page = total_pages

    list_path = data_path.removesuffix("/data") if data_path.endswith("/data") else data_path
    filter_qs = _filter_query_string(filters)

    if page > 1:
        prev_href = f"{escape(list_path)}?{_filter_query_string(filters, page - 1)}"
        prev_btn = f'<a class="pager-btn" href="{prev_href}">上一页</a>'
    else:
        prev_btn = '<span class="pager-btn disabled">上一页</span>'

    if page < total_pages:
        next_href = f"{escape(list_path)}?{_filter_query_string(filters, page + 1)}"
        next_btn = f'<a class="pager-btn" href="{next_href}">下一页</a>'
    else:
        next_btn = '<span class="pager-btn disabled">下一页</span>'

    pager_block = f"""
    <div class="pager">
        <span>共 {total} 条</span>
        {prev_btn}
        <span>第 {page} / {total_pages} 页</span>
        {next_btn}
    </div>"""

    json_qs = f"{filter_qs}&page={page}" if filter_qs else f"page={page}"
    export_link = ""
    if record_type == "monitor":
        export_href = f"/assetinfo/monitor-records/export?{filter_qs}" if filter_qs else "/assetinfo/monitor-records/export"
        export_link = f' · <a href="{escape(export_href)}">导出 Excel（监控模版）</a>'
    elif record_type in ("repayment", "repayment_plan"):
        export_href = f"/assetinfo/repayment-records/export?{filter_qs}" if filter_qs else "/assetinfo/repayment-records/export"
        export_link = f' · <a href="{escape(export_href)}">导出 Excel（披露模版）</a>'

    empty_hint = ""
    if record_type == "repayment_plan" and total == 0:
        empty_hint = (
            '<p class="snapshot-hint warn">暂无回款计划数据。请在 '
            '<a href="/assetinfo/upload">资产数据导入</a> 中勾选还款披露 Excel 的「回款计划」Sheet 导入。</p>'
        )

    sort_script = ""
    if record_type == "monitor":
        sort_script = f"""
    <script>
    (function() {{
        var listPath = {list_path!r};
        var table = document.querySelector('.records-table');
        if (!table) return;
        table.querySelectorAll('th.sortable').forEach(function(th) {{
            th.addEventListener('click', function() {{
                var key = th.getAttribute('data-sort-key');
                var params = new URLSearchParams(window.location.search);
                var currentSort = params.get('sort_by');
                var currentDir = params.get('sort_dir') || 'desc';
                if (currentSort === key) {{
                    params.set('sort_dir', currentDir === 'asc' ? 'desc' : 'asc');
                }} else {{
                    params.set('sort_by', key);
                    params.set('sort_dir', 'asc');
                }}
                params.set('page', '1');
                window.location.href = listPath + '?' + params.toString();
            }});
        }});
    }})();
    </script>"""

    hscroll_script = """
    <script>
    (function() {
        var wrap = document.getElementById('records-hscroll');
        if (!wrap) return;
        var key = 'recordsHScroll:' + window.location.pathname;
        var colKey = key + ':col';

        function anchorCol() {
            var ths = wrap.querySelectorAll('thead th[data-col]');
            var left = wrap.scrollLeft;
            for (var i = 0; i < ths.length; i++) {
                var th = ths[i];
                if (th.offsetLeft + th.offsetWidth > left + 1) {
                    return th.getAttribute('data-col');
                }
            }
            return ths.length ? ths[ths.length - 1].getAttribute('data-col') : null;
        }

        function savePos() {
            sessionStorage.setItem(key, String(wrap.scrollLeft));
            var col = anchorCol();
            if (col) sessionStorage.setItem(colKey, col);
        }

        function restorePos() {
            var col = sessionStorage.getItem(colKey);
            if (col) {
                var th = wrap.querySelector('thead th[data-col="' + col + '"]');
                if (th) {
                    wrap.scrollLeft = th.offsetLeft;
                    return;
                }
            }
            var saved = sessionStorage.getItem(key);
            if (saved !== null) {
                var left = parseInt(saved, 10);
                if (!isNaN(left)) wrap.scrollLeft = left;
            }
        }

        requestAnimationFrame(function() {
            requestAnimationFrame(restorePos);
        });
        window.addEventListener('load', restorePos);

        wrap.addEventListener('scroll', savePos, { passive: true });
        document.querySelectorAll('a.pager-btn').forEach(function(a) {
            a.addEventListener('click', savePos);
        });
        var filterForm = document.getElementById('f');
        if (filterForm) {
            filterForm.addEventListener('submit', function() {
                sessionStorage.removeItem(key);
                sessionStorage.removeItem(colKey);
            });
        }
    })();
    </script>"""
    empty_table = (
        '<tr><td colspan="8">暂无数据</td></tr>'
        if record_type == "repayment_plan"
        else '<tr><td>无数据</td></tr>'
    )
    body = f"""
    <nav class="breadcrumb"><a href="/">首页</a> / <a href="/assetinfo/upload">资产情况</a> / {escape(title)}</nav>
    <h1>{escape(title)}</h1>
    <div class="card filters">
        <form id="f" method="get" class="filters" style="width:100%">
            {filter_inputs}
            <div><button type="submit" class="btn-primary">筛选</button></div>
        </form>
        {snapshot_banner}
        {empty_hint}
    </div>
    {pager_block}
    <p class="muted"><a href="{escape(data_path)}?{json_qs}">JSON</a>{export_link}</p>
    <div class="card table-wrap" id="records-hscroll">
        <table class="records-table"><thead><tr>{headers}</tr></thead><tbody>{rows or empty_table}</tbody></table>
    </div>
    {pager_block}
    {sort_script}
    {hscroll_script}
    """
    return _page_shell(title, body)
