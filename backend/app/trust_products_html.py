"""信托产品主数据 V1 Lite — HTML 页面."""

from __future__ import annotations

import json
from html import escape

from app.ui_css import BTN_CSS, FORM_FIELD_CSS, PAGE_CHROME_CSS, STANDARD_HEADER_CSS, TABLE_SCROLL_CSS


def _page_shell(title: str, body: str, *, extra_script: str = "") -> str:
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
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 1.25rem;
            margin-bottom: 1rem;
        }}
        .table-card {{ overflow-x: auto; }}
        th, td {{
            padding: 0.5rem 0.75rem;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            text-align: left;
            white-space: nowrap;
        }}
        th {{ color: #94a3b8; font-weight: 500; }}
        .toolbar {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            align-items: center;
            margin-bottom: 1rem;
        }}
        .form-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 1rem 1.25rem;
        }}
        .form-grid label {{ display: block; }}
        .readonly-value {{
            padding: 0.55rem 0.75rem;
            border-radius: 8px;
            background: rgba(15,23,42,0.55);
            border: 1px solid rgba(255,255,255,0.08);
            color: #cbd5e1;
        }}
        .form-actions {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin-top: 1.25rem;
            padding-top: 1rem;
            border-top: 1px solid rgba(255,255,255,0.08);
        }}
        .msg {{ margin-top: 0.75rem; font-size: 0.9rem; }}
        .msg.err {{ color: #f87171; }}
        .msg.ok {{ color: #34d399; }}
        .badge {{
            display: inline-block;
            padding: 0.15rem 0.55rem;
            border-radius: 999px;
            font-size: 0.8rem;
            background: rgba(56,189,248,0.15);
            color: #7dd3fc;
        }}
    </style>
</head>
<body>
<div class="container">{body}</div>
{extra_script}
</body></html>"""


def render_trust_products_manage_page(items: list[dict]) -> str:
    rows = ""
    if not items:
        rows = '<tr><td colspan="9" class="muted">暂无信托产品</td></tr>'
    else:
        for item in items:
            end_date = escape(item.get("trust_end_date") or "—")
            rows += f"""
            <tr>
                <td>{item["id"]}</td>
                <td>{escape(item["code"])}</td>
                <td>{escape(item["name"])}</td>
                <td><span class="badge">{escape(item["status_label"])}</span></td>
                <td>{escape(item.get("asset_pool_name") or "—")}</td>
                <td>{end_date}</td>
                <td>{escape(item.get("created_at") or "—")}</td>
                <td>{escape(item.get("updated_at") or "—")}</td>
                <td><a href="/trust-products/{item["id"]}/edit">编辑</a></td>
            </tr>
            """

    body = f"""
    <div class="breadcrumb"><a href="/">首页</a> / 信托产品管理</div>
    <header class="page-header">
        <h1>信托产品管理</h1>
        <p class="muted">主数据维护：编码与资产包创建后不可修改；状态仅「已发行 / 结束」。</p>
    </header>
    <div class="toolbar">
        <a class="btn btn-primary" href="/trust-products/new">新增信托产品</a>
        <a class="api-link" href="/trust-products">JSON 列表</a>
    </div>
    <div class="card table-card">
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>产品编码</th>
                    <th>产品名称</th>
                    <th>状态</th>
                    <th>资产包</th>
                    <th>信托结束日期</th>
                    <th>创建时间</th>
                    <th>更新时间</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """
    return _page_shell("信托产品管理", body)


def render_trust_product_form_page(
    *,
    mode: str,
    asset_pools: list[dict] | None = None,
    product: dict | None = None,
) -> str:
    is_edit = mode == "edit"
    title = "编辑信托产品" if is_edit else "新增信托产品"
    breadcrumb_tail = title
    product_id = int(product["id"]) if product else 0

    status_issued_sel = ""
    status_ended_sel = ""
    default_status = (product or {}).get("status") or "issued"
    if default_status == "ended":
        status_ended_sel = " selected"
    else:
        status_issued_sel = " selected"

    trust_end_date_val = escape((product or {}).get("trust_end_date") or "")
    name_val = escape((product or {}).get("name") or "")

    if is_edit:
        asset_pool_field = f"""
            <label>资产包
                <div class="readonly-value">{escape(product.get("asset_pool_name") or "—")}</div>
            </label>
            <label>产品编码
                <div class="readonly-value">{escape(product.get("code") or "—")}</div>
            </label>
        """
        submit_url = f"/trust-products/{product_id}"
        submit_method = "PATCH"
    else:
        pool_options = '<option value="">请选择资产包</option>'
        for pool in asset_pools or []:
            pool_options += (
                f'<option value="{pool["id"]}">'
                f'{escape(pool["name"])} ({escape(pool["code"])})'
                f"</option>"
            )
        asset_pool_field = f"""
            <label>资产包 <span class="muted">*</span>
                <select name="asset_pool_id" required>{pool_options}</select>
            </label>
            <label>产品编码 <span class="muted">*</span>
                <input type="text" name="code" maxlength="32" required placeholder="如 TRU-2026-00005">
            </label>
        """
        submit_url = "/trust-products"
        submit_method = "POST"

    body = f"""
    <div class="breadcrumb">
        <a href="/">首页</a> / <a href="/trust-products/manage">信托产品管理</a> / {escape(breadcrumb_tail)}
    </div>
    <header class="page-header">
        <h1>{escape(title)}</h1>
        <p class="muted">{"仅可修改名称、状态与信托结束日期。" if is_edit else "创建后编码与资产包不可修改。"}</p>
    </header>
    <div class="card">
        <form id="tp-form" class="form-grid" onsubmit="return false;">
            {asset_pool_field}
            <label>产品名称 <span class="muted">*</span>
                <input type="text" name="name" maxlength="200" required value="{name_val}">
            </label>
            <label>状态 <span class="muted">*</span>
                <select name="status" required>
                    <option value="issued"{status_issued_sel}>已发行</option>
                    <option value="ended"{status_ended_sel}>结束</option>
                </select>
            </label>
            <label>信托结束日期
                <input type="date" name="trust_end_date" value="{trust_end_date_val}">
            </label>
        </form>
        <div class="form-actions">
            <button type="button" class="btn btn-primary" id="tp-submit">保存</button>
            <a class="btn btn-secondary" href="/trust-products/manage">取消</a>
        </div>
        <div id="tp-msg" class="msg" aria-live="polite"></div>
    </div>
    """

    script = f"""
<script>
(function() {{
    var form = document.getElementById('tp-form');
    var msg = document.getElementById('tp-msg');
    var submitBtn = document.getElementById('tp-submit');
    var url = {json.dumps(submit_url)};
    var method = {json.dumps(submit_method)};

    function showMsg(text, ok) {{
        msg.textContent = text;
        msg.className = 'msg ' + (ok ? 'ok' : 'err');
    }}

    submitBtn.addEventListener('click', function() {{
        msg.textContent = '';
        msg.className = 'msg';
        var payload = {{}};
        if (method === 'POST') {{
            var poolEl = form.querySelector('[name="asset_pool_id"]');
            var codeEl = form.querySelector('[name="code"]');
            if (!poolEl || !poolEl.value) {{
                showMsg('请选择资产包', false);
                return;
            }}
            if (!codeEl || !(codeEl.value || '').trim()) {{
                showMsg('请填写产品编码', false);
                return;
            }}
            payload.asset_pool_id = parseInt(poolEl.value, 10);
            payload.code = codeEl.value.trim();
        }}
        var nameEl = form.querySelector('[name="name"]');
        var statusEl = form.querySelector('[name="status"]');
        var endEl = form.querySelector('[name="trust_end_date"]');
        if (!nameEl || !(nameEl.value || '').trim()) {{
            showMsg('请填写产品名称', false);
            return;
        }}
        payload.name = nameEl.value.trim();
        payload.status = statusEl ? statusEl.value : 'issued';
        var endVal = endEl ? (endEl.value || '').trim() : '';
        payload.trust_end_date = endVal || null;

        submitBtn.disabled = true;
        fetch(url, {{
            method: method,
            headers: {{ 'Content-Type': 'application/json' }},
            credentials: 'same-origin',
            body: JSON.stringify(payload)
        }}).then(function(resp) {{
            return resp.json().then(function(data) {{
                return {{ ok: resp.ok, status: resp.status, data: data }};
            }}).catch(function() {{
                return {{ ok: resp.ok, status: resp.status, data: {{ detail: resp.statusText }} }};
            }});
        }}).then(function(result) {{
            submitBtn.disabled = false;
            if (result.ok) {{
                window.location.href = '/trust-products/manage';
                return;
            }}
            var detail = result.data && result.data.detail;
            if (Array.isArray(detail)) {{
                detail = detail.map(function(d) {{ return d.msg || JSON.stringify(d); }}).join('; ');
            }}
            showMsg(detail || ('保存失败 (' + result.status + ')'), false);
        }}).catch(function(err) {{
            submitBtn.disabled = false;
            showMsg(err.message || '网络错误', false);
        }});
    }});
}})();
</script>
"""
    return _page_shell(title, body, extra_script=script)
