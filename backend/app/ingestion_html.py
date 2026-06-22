"""Excel 导入 V2 — HTML 页面."""

from __future__ import annotations

from datetime import date, datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

DISPLAY_TZ = ZoneInfo("Asia/Shanghai")


def _page_shell(title: str, body: str, username: str | None = None) -> str:
    from app import auth_html

    user_bar = auth_html.render_user_bar(username) if username else ""
    user_css = auth_html.USER_BAR_CSS if username else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(title)}</title>
    <style>
        {user_css}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
            min-height: 100vh; color: #e2e8f0; padding: 2rem 1rem;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        a {{ color: #38bdf8; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        h1 {{ font-size: 1.5rem; color: #f8fafc; margin: 1rem 0 0.5rem; }}
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
        table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
        th, td {{ padding: 0.5rem 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.08); text-align: left; }}
        th {{ color: #94a3b8; }}
        .records-table {{
            table-layout: fixed;
            width: max-content;
            min-width: 100%;
        }}
        .records-table th,
        .records-table td {{
            word-break: normal;
            overflow-wrap: normal;
            vertical-align: top;
            overflow: hidden;
        }}
        .records-table th.col-num,
        .records-table td.col-num {{
            text-align: right;
            white-space: nowrap;
        }}
        .records-table th.col-single-line,
        .records-table td.col-single-line {{
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .records-table th.col-trust-product,
        .records-table td.col-trust-product {{
            width: 220px;
            min-width: 220px;
            max-width: 220px;
        }}
        .records-table th.col-custody,
        .records-table td.col-custody {{
            width: 130px;
            min-width: 130px;
            max-width: 130px;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.82rem;
        }}
        .records-table th.col-source-split,
        .records-table td.col-source-split {{
            width: 150px;
            min-width: 150px;
            max-width: 150px;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.82rem;
        }}
        .records-table th.col-source-file-name,
        .records-table td.col-source-file-name {{
            width: 380px;
            min-width: 380px;
            max-width: 380px;
            overflow: hidden;
        }}
        .records-table th.col-source-sheet-name,
        .records-table td.col-source-sheet-name {{
            width: 180px;
            min-width: 180px;
            max-width: 180px;
            overflow: hidden;
        }}
        .records-table th.col-date,
        .records-table td.col-date {{
            width: 110px;
            min-width: 110px;
            max-width: 110px;
            white-space: nowrap;
        }}
        .records-table th.col-timestamp,
        .records-table td.col-timestamp {{
            width: 130px;
            min-width: 130px;
            max-width: 130px;
            white-space: nowrap;
        }}
        .records-table th.col-id,
        .records-table td.col-id {{
            width: 72px;
            min-width: 72px;
            max-width: 72px;
            white-space: nowrap;
        }}
        .records-table th.col-asset-code,
        .records-table td.col-asset-code {{
            width: 150px;
            min-width: 150px;
            max-width: 150px;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            font-size: 0.82rem;
        }}
        .records-table .source-file-name-text {{
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            word-break: break-word;
            line-height: 1.4;
            max-width: 100%;
        }}
        .records-table .sheet-name-text {{
            display: block;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 100%;
        }}
        .records-table .cell-ellipsis {{
            display: block;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 100%;
        }}
        details.compat-filters summary {{ cursor: pointer; color: #cbd5e1; }}
        .ok {{ color: #34d399; }} .warn {{ color: #fbbf24; }} .err {{ color: #f87171; }}
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
<body><div class="container">{user_bar}{body}</div></body></html>"""


def render_upload_page(trust_products: list[dict], username: str) -> str:
    options = "".join(
        f'<option value="{tp["id"]}">{escape(tp["name"])} (id={tp["id"]})</option>'
        for tp in trust_products
    )
    body = f"""
    <p class="muted"><a href="/">首页</a> / 数据导入 V2</p>
    <h1>Excel 批量导入 V2</h1>
    <p class="muted">先预检，再确认导入。字段映射：托管房源编码 → 托管房源号；资产编号(房源) → 资产分笔号。</p>
    <div class="card">
        <label>信托产品</label>
        <select id="trust_product_id" style="width:100%">{options}</select>
        <label>Excel 文件（可多选）</label>
        <input type="file" id="files" multiple accept=".xlsx,.xls" style="width:100%">
        <button type="button" onclick="runPreview()">预检</button>
        <button type="button" class="secondary" onclick="runImport()">确认导入</button>
    </div>
    <div class="card" id="result"><p class="muted">预检结果将显示在此处</p></div>
    <script>
    let batchUuid = null;
    let previewData = null;
    async function runPreview() {{
        const fd = new FormData();
        fd.append('trust_product_id', document.getElementById('trust_product_id').value);
        for (const f of document.getElementById('files').files) fd.append('files', f);
        const res = await fetch('/ingestion/preview', {{ method: 'POST', credentials: 'same-origin', body: fd }});
        const data = await res.json();
        batchUuid = data.batch_uuid;
        previewData = data;
        renderPreview(data, res.ok);
    }}
    async function runImport() {{
        if (!batchUuid) {{ alert('请先预检'); return; }}
        const confirmKeys = (previewData.sheets || [])
            .filter(s => s.action === 'needs_confirm')
            .map(s => s.file_name + '::' + s.sheet_name);
        const body = {{
            batch_uuid: batchUuid,
            trust_product_id: parseInt(document.getElementById('trust_product_id').value),
            confirm_sheet_keys: confirmKeys
        }};
        const res = await fetch('/ingestion/import', {{
            method: 'POST',
            credentials: 'same-origin',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(body)
        }});
        const data = await res.json();
        document.getElementById('result').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
    }}
    function renderPreview(data, ok) {{
        let html = '<p class="' + (ok ? 'ok' : 'err') + '">batch: ' + (data.batch_uuid||'') + '</p><table><tr>';
        ['file','sheet','type','parsed_date','rule','rows','amount','action','reason'].forEach(h => html += '<th>'+h+'</th>');
        html += '</tr>';
        (data.sheets||[]).forEach(s => {{
            let typeCell = s.sheet_type;
            let reasonCell = s.reason || '';
            if (s.sheet_type === 'ambiguous_sheet_type') {{
                typeCell = '<span class="err">❌ 类型冲突</span>';
                reasonCell = '名称识别：' + (s.name_type || '') + '<br>表头识别：' + (s.header_type || '') + '<br>请人工确认文件模板';
            }}
            html += '<tr><td>'+s.file_name+'</td><td>'+s.sheet_name+'</td><td>'+typeCell+'</td>';
            html += '<td>'+(s.parsed_date||'—')+'</td><td>'+(s.date_rule_label||'—')+'</td>';
            html += '<td>'+(s.row_count??'—')+'</td><td>'+(s.amount_sum??'—')+'</td>';
            html += '<td>'+s.action+'</td><td>'+reasonCell+'</td></tr>';
        }});
        html += '</table>';
        document.getElementById('result').innerHTML = html;
    }}
    </script>
    """
    return _page_shell("数据导入 V2", body, username)


def _filter_query_string(filters: dict, page: int | None = None) -> str:
    parts = []
    for key, val in filters.items():
        if val is not None and val != "":
            parts.append(f"{key}={escape(str(val))}")
    if page is not None:
        parts.append(f"page={page}")
    return "&".join(parts)


RECORD_COLUMN_LABELS: dict[str, str] = {
    "custody_asset_code": "托管房源号",
    "source_asset_code": "资产分笔号",
    "asset_code": "asset_code(兼容)",
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
    "custody_asset_code",
    "source_asset_code",
    "asset_code",
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
    "custody_asset_code",
    "source_asset_code",
    "asset_code",
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
    "period_no",
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
        classes.extend(["col-trust-product", "col-single-line"])
    elif key == "custody_asset_code":
        classes.extend(["col-custody", "col-single-line"])
    elif key == "source_asset_code":
        classes.extend(["col-source-split", "col-single-line"])
    elif key == "asset_code":
        classes.extend(["col-asset-code", "col-single-line"])
    elif key == "source_file_name":
        classes.append("col-source-file-name")
    elif key == "source_sheet_name":
        classes.extend(["col-source-sheet-name", "col-single-line"])
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
    title_attr = f' title="{escape(display)}"' if display != "—" else ""
    return (
        f'<td class="{cls}" data-col="source_file_name"{title_attr}>'
        f'<span class="source-file-name-text">{escape(display)}</span></td>'
    )


def _render_source_sheet_name_cell(value) -> str:
    display = _cell_display("source_sheet_name", value)
    cls = _record_col_class("source_sheet_name")
    title_attr = f' title="{escape(display)}"' if display != "—" else ""
    return (
        f'<td class="{cls}" data-col="source_sheet_name"{title_attr}>'
        f'<span class="sheet-name-text">{escape(display)}</span></td>'
    )


def _render_record_cell(key: str, value) -> str:
    if key == "source_file_name":
        return _render_source_file_name_cell(value)
    if key == "source_sheet_name":
        return _render_source_sheet_name_cell(value)

    display = _cell_display(key, value)
    cls = _record_col_class(key)
    class_attr = f' class="{cls}"' if cls else ""
    if key in ("trust_product_name", "custody_asset_code", "source_asset_code", "asset_code"):
        title_attr = f' title="{escape(display)}"' if display != "—" else ""
        return (
            f'<td{class_attr} data-col="{escape(key)}"{title_attr}>'
            f'<span class="cell-ellipsis">{escape(display)}</span></td>'
        )
    if key in RECORD_TIMESTAMP_COLUMNS:
        raw_title = str(value) if value is not None else ""
        title_attr = f' title="{escape(raw_title)}"' if raw_title else ""
        return f'<td{class_attr} data-col="{escape(key)}"{title_attr}>{escape(display)}</td>'
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
        ("custody_asset_code", "托管房源号"),
        ("source_asset_code", "资产分笔号"),
        ("source_file_name", "文件名"),
        ("source_sheet_name", "Sheet名"),
    ]:
        val = escape(str(filters.get(key) or ""))
        filter_inputs += f"""
        <div><label>{label}</label>
        <input name="{key}" value="{val}" form="f"></div>"""

    compat_asset = escape(str(filters.get("asset_code") or ""))
    filter_inputs += f"""
        <details class="compat-filters">
            <summary>高级筛选（兼容字段）</summary>
            <div style="margin-top:0.5rem">
                <label>asset_code（兼容，等同资产分笔号）</label>
                <input name="asset_code" value="{compat_asset}" form="f" style="width:100%">
            </div>
        </details>"""

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
    <p class="muted"><a href="/">首页</a> / <a href="/ingestion/upload">导入</a> / {escape(title)}</p>
    <h1>{escape(title)}</h1>
    <div class="card filters">
        <form id="f" method="get" class="filters" style="width:100%">
            {filter_inputs}
            <div><button type="submit">筛选</button></div>
        </form>
    </div>
    {pager_block}
    <p class="muted"><a href="{escape(data_path)}?{json_qs}">JSON</a></p>
    <div class="card" style="overflow-x:auto">
        <table class="records-table"><thead><tr>{headers}</tr></thead><tbody>{rows or '<tr><td>无数据</td></tr>'}</tbody></table>
    </div>
    {pager_block}
    """
    return _page_shell(title, body, username)
