"""Excel 导入 V2 — HTML 页面."""

from __future__ import annotations

from datetime import date, datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

from app.ui_css import PAGE_CHROME_CSS, TABLE_SCROLL_CSS

DISPLAY_TZ = ZoneInfo("Asia/Shanghai")


def _page_shell(title: str, body: str, username: str | None = None) -> str:
    from app import auth_html

    user_bar = auth_html.user_bar_div(username) if username else ""
    user_css = auth_html.USER_BAR_CSS if username else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(title)}</title>
    <style>
        {user_css}
        {PAGE_CHROME_CSS}
        h1 {{ font-size: 1.5rem; color: #f8fafc; margin: 0 0 0.5rem; }}
        p.muted {{ color: #94a3b8; margin-bottom: 1rem; font-size: 0.9rem; }}
        .card {{
            background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px; padding: 1.25rem; margin-bottom: 1rem;
        }}
        label {{ display: block; font-size: 0.85rem; color: #94a3b8; margin: 0.75rem 0 0.25rem; }}
        input, select, button {{
            font: inherit; padding: 0.5rem 0.75rem; border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.15); background: rgba(15,23,42,0.8); color: #f8fafc;
        }}
        button {{ cursor: pointer; background: #0ea5e9; border-color: #0ea5e9; margin-top: 1rem; }}
        button.secondary {{ background: transparent; margin-left: 0.5rem; }}
        {TABLE_SCROLL_CSS}
        th, td {{ padding: 0.5rem 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.08); text-align: left; }}
        th {{ color: #94a3b8; }}
        .records-table {{ font-size: 0.85rem; }}
        .records-table th.col-num,
        .records-table td.col-num {{
            text-align: right;
        }}
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
        .sheet-toolbar button {{ margin-top: 0; font-size: 0.82rem; padding: 0.35rem 0.65rem; }}
        .sheet-cb {{ width: auto; margin-right: 0.35rem; }}
        .sheet-confirm-cb {{ width: auto; margin-left: 0.5rem; }}
        tr.row-reject {{ opacity: 0.55; }}
        tr.row-needs_confirm {{ background: rgba(251,191,36,0.06); }}
        .import-bar {{ margin-top: 1rem; padding-top: 0.75rem; border-top: 1px solid rgba(255,255,255,0.08); }}
        .filters {{ display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: flex-end; }}
        .filters > div {{ min-width: 140px; }}
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
<body>{user_bar}
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


def render_upload_page(trust_products: list[dict], username: str) -> str:
    options = "".join(
        f'<option value="{tp["id"]}">{escape(tp["name"])} (id={tp["id"]})</option>'
        for tp in trust_products
    )
    body = f"""
    <nav class="breadcrumb"><a href="/">首页</a> / 数据导入 V2</nav>
    <h1>Excel 批量导入 V2</h1>
    <p class="muted">先预检，再确认导入。字段映射：托管房源编码 → 托管房源号；资产编号(房源) → 资产分笔号。</p>
    <div class="card">
        <label>信托产品</label>
        <select id="trust_product_id" style="width:100%">{options}</select>
        <label>Excel 文件（可多选）</label>
        <input type="file" id="files" multiple accept=".xlsx,.xls" style="width:100%">
        <button type="button" onclick="runPreview()">预检</button>
    </div>
    <div class="card" id="result"><p class="muted">预检结果将显示在此处</p></div>
    <div class="card import-bar" id="importBar" style="display:none">
        <p class="muted">已选 <strong id="selCount">0</strong> 个 Sheet · 仅导入选中项</p>
        <button type="button" onclick="runImport()">确认导入选中 Sheet</button>
    </div>
    <script>
    let batchUuid = null;
    let previewData = null;
    let confirmedKeys = new Set();

    async function runPreview() {{
        const fd = new FormData();
        fd.append('trust_product_id', document.getElementById('trust_product_id').value);
        for (const f of document.getElementById('files').files) fd.append('files', f);
        const res = await fetch('/ingestion/preview', {{ method: 'POST', credentials: 'same-origin', body: fd }});
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
        const res = await fetch('/ingestion/import', {{
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
        let html = '<p class="' + (ok ? 'ok' : 'err') + '">file_id: ' + (data.file_id || data.batch_uuid || '') + '</p>';
        html += '<div class="sheet-toolbar">';
        html += '<button type="button" class="secondary" onclick="selectAllImport()">全选 import</button>';
        html += '<button type="button" class="secondary" onclick="selectExcludeNeedsConfirm()">仅 import（排除 needs_confirm）</button>';
        html += '</div>';
        html += '<div class="table-wrap"><table><tr><th>选</th><th>file</th><th>sheet</th><th>type</th><th>rows</th><th>amount</th><th>status</th><th>reason</th></tr>';
        sheets.forEach(s => {{
            const key = sheetKey(s);
            const st = s.status || s.action || '—';
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
                reasonCell = '名称识别：' + (s.name_type || '') + ' / 表头：' + (s.header_type || '');
            }}
            html += '<tr class="'+rowCls+'"><td>'+cb+'</td>';
            html += '<td>'+s.file_name+'</td><td>'+s.sheet_name+'</td><td>'+(s.type||s.sheet_type||'—')+'</td>';
            html += '<td>'+(s.rows ?? s.row_count ?? '—')+'</td><td>'+(s.amount ?? s.amount_sum ?? '—')+'</td>';
            html += '<td><span class="'+(st==='reject'?'err':(st==='needs_confirm'?'warn':'ok'))+'">'+st+'</span></td>';
            html += '<td>'+reasonCell+'</td></tr>';
        }});
        html += '</table></div>';
        document.getElementById('result').innerHTML = html;
        document.getElementById('importBar').style.display = sheets.length ? 'block' : 'none';
        updateSelCount();
    }}
    </script>
    """
    return _page_shell("数据导入 V2", body, username)


def _filter_query_string(filters: dict, page: int | None = None) -> str:
    parts = []
    for key, val in filters.items():
        if key == "include_history":
            if val:
                parts.append("include_history=1")
            continue
        if val is not None and val != "":
            parts.append(f"{key}={escape(str(val))}")
    if page is not None:
        parts.append(f"page={page}")
    return "&".join(parts)


RECORD_COLUMN_LABELS: dict[str, str] = {
    "custody_asset_code": "托管房源号",
    "source_asset_code": "资产分笔号",
    "asset_code": "资产主编号",
    "trust_product_name": "信托产品",
    "trust_product_id": "产品ID",
    "data_date": "数据日期",
    "repayment_date": "还款日期",
    "period_no": "期数",
    "actual_repayment_amount": "实际还款金额",
    "initial_transfer_amount": "初始受让金额",
    "repaid_amount": "已还款金额",
    "remaining_amount": "剩余还款金额",
    "overdue_days": "逾期天数",
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

REPAYMENT_COLUMN_ORDER: tuple[str, ...] = (
    "trust_product_name",
    "asset_code",
    "custody_asset_code",
    "source_asset_code",
    "data_date",
    "repayment_date",
    "period_no",
    "actual_repayment_amount",
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
    "source_asset_code",
    "data_date",
    "overdue_days",
    "initial_transfer_amount",
    "repaid_amount",
    "remaining_amount",
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
    "overdue_days",
    "risk_score",
})

RECORD_DATE_ONLY_COLUMNS: frozenset[str] = frozenset({
    "data_date",
    "repayment_date",
    "last_payment_date",
    "max_payment_date",
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


def _record_column_label(key: str) -> str:
    return RECORD_COLUMN_LABELS.get(key, key)


def _render_record_header(key: str) -> str:
    label = _record_column_label(key)
    cls = _record_col_class(key)
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
    username: str | None = None,
    record_type: str = "repayment",
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

    for key, label in [
        ("data_date", "数据日期"),
        ("asset_code", "资产主编号"),
        ("custody_asset_code", "托管房源号"),
        ("source_asset_code", "资产分笔号"),
        ("source_file_name", "文件名"),
        ("source_sheet_name", "Sheet名"),
    ]:
        val = escape(str(filters.get(key) or ""))
        filter_inputs += f"""
        <div><label>{label}</label>
        <input name="{key}" value="{val}" form="f"></div>"""

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

    rows = ""
    headers = ""
    if data.get("items"):
        keys = _ordered_record_keys(list(data["items"][0].keys()), record_type)
        headers = "".join(_render_record_header(k) for k in keys)
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
    body = f"""
    <nav class="breadcrumb"><a href="/">首页</a> / <a href="/ingestion/upload">导入</a> / {escape(title)}</nav>
    <h1>{escape(title)}</h1>
    <div class="card filters">
        <form id="f" method="get" class="filters" style="width:100%">
            {filter_inputs}
            <div><button type="submit">筛选</button></div>
        </form>
        {snapshot_banner}
    </div>
    {pager_block}
    <p class="muted"><a href="{escape(data_path)}?{json_qs}">JSON</a></p>
    <div class="card table-wrap">
        <table class="records-table"><thead><tr>{headers}</tr></thead><tbody>{rows or '<tr><td>无数据</td></tr>'}</tbody></table>
    </div>
    {pager_block}
    """
    return _page_shell(title, body, username)
