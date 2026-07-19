"""数据披露页面 HTML（还款明细 / 资产监控）。"""
from __future__ import annotations

import json
from html import escape

from app.ui_css import BTN_CSS, FORM_FIELD_CSS, PAGE_CHROME_CSS, STANDARD_HEADER_CSS, TABLE_SCROLL_CSS


def _product_checkboxes(products: list[dict], selected_ids: list[int] | None) -> str:
    selected = set(selected_ids or [])
    parts = []
    for p in products:
        pid = int(p["id"])
        checked = " checked" if pid in selected else ""
        parts.append(
            f'<label class="tp-opt">'
            f'<input type="checkbox" name="trust_product_ids" value="{pid}"{checked}> '
            f'{escape(str(p["name"]))}</label>'
        )
    return "\n".join(parts)


def _snapshots_json(snapshots: list[dict]) -> str:
    # 放入 <script>：不做 HTML escape（会破坏 JSON），仅规避 </script>
    return json.dumps(snapshots, ensure_ascii=False, default=str).replace("<", "\\u003c")


def render_repayment_disclosure_page(
    products: list[dict],
    snapshots: list[dict],
    *,
    selected_ids: list[int] | None = None,
    as_of: str = "",
    username: str = "",
) -> str:
    return _render_page(
        kind="repayment",
        title="还款明细披露",
        date_label="披露截止日",
        date_hint="明细按还款日期 ≤ 截止日；回款计划取各产品统计日 ≤ 截止日的最新批次；逾期天数取监控统计日 ≤ 截止日的最新值。",
        products=products,
        snapshots=snapshots,
        selected_ids=selected_ids,
        as_of=as_of,
        username=username,
        has_tabs=True,
    )


def render_monitor_disclosure_page(
    products: list[dict],
    snapshots: list[dict],
    *,
    selected_ids: list[int] | None = None,
    as_of: str = "",
    username: str = "",
) -> str:
    return _render_page(
        kind="monitor",
        title="资产监控披露",
        date_label="统计日期",
        date_hint="仅展示所选信托产品在该统计日期（data_date）的监控导入数据。",
        products=products,
        snapshots=snapshots,
        selected_ids=selected_ids,
        as_of=as_of,
        username=username,
        has_tabs=False,
    )


def _render_page(
    *,
    kind: str,
    title: str,
    date_label: str,
    date_hint: str,
    products: list[dict],
    snapshots: list[dict],
    selected_ids: list[int] | None,
    as_of: str,
    username: str,
    has_tabs: bool,
) -> str:
    product_html = _product_checkboxes(products, selected_ids)
    snaps_json = _snapshots_json(snapshots)
    tabs_html = ""
    if has_tabs:
        tabs_html = """
        <div class="tabs" id="view-tabs">
            <button type="button" class="tab active" data-tab="detail">还款明细</button>
            <button type="button" class="tab" data-tab="plan">回款计划</button>
        </div>
        """
    panels_html = (
        """
        <div id="panel-detail" class="table-panel"></div>
        <div id="panel-plan" class="table-panel" style="display:none"></div>
        """
        if has_tabs
        else '<div id="panel-monitor" class="table-panel"></div>'
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{escape(title)} · 贝源RSP平台</title>
<style>
{PAGE_CHROME_CSS}
{STANDARD_HEADER_CSS}
{FORM_FIELD_CSS}
{BTN_CSS}
{TABLE_SCROLL_CSS}
.card {{
    background: rgba(30,41,59,0.85);
    border: 1px solid rgba(148,163,184,0.2);
    border-radius: 12px;
    padding: 1rem 1.25rem;
    margin-bottom: 1rem;
}}
.muted {{ color: #94a3b8; font-size: 0.88rem; margin: 0.35rem 0 0.75rem; }}
.filters {{ display: flex; flex-wrap: wrap; gap: 0.75rem 1rem; align-items: flex-end; }}
.filters .tp-box {{
    min-width: 220px; max-width: 360px; max-height: 140px; overflow: auto;
    border: 1px solid rgba(255,255,255,0.12); border-radius: 8px;
    padding: 0.4rem 0.55rem; background: rgba(0,0,0,0.2);
}}
.tp-opt {{ display: block; font-size: 0.82rem; color: #e2e8f0; margin: 0.2rem 0; }}
.tp-opt input {{ width: auto; margin-right: 0.35rem; }}
.actions {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.75rem; }}
.btn-danger {{
    cursor: pointer; font: inherit; padding: 0.5rem 0.75rem; border-radius: 8px;
    border: 1px solid #ef4444; background: transparent; color: #fca5a5; margin-top: 0;
}}
.btn-ghost {{
    cursor: pointer; font: inherit; padding: 0.5rem 0.75rem; border-radius: 8px;
    border: 1px solid rgba(148,163,184,0.35); background: transparent; color: #e2e8f0; margin-top: 0;
}}
.btn-primary, .btn-secondary {{ margin-top: 0; }}
.meta {{ font-size: 0.85rem; color: #cbd5e1; margin: 0.5rem 0; }}
.err {{ color: #fca5a5; font-size: 0.9rem; margin: 0.5rem 0; }}
.ok {{ color: #86efac; font-size: 0.9rem; margin: 0.5rem 0; }}
.tabs {{ display: flex; gap: 0.35rem; margin: 0.75rem 0 0.5rem; }}
.tab {{
    cursor: pointer; font: inherit; padding: 0.4rem 0.85rem; border-radius: 8px;
    border: 1px solid rgba(148,163,184,0.3); background: transparent; color: #cbd5e1;
}}
.tab.active {{ background: #0ea5e9; border-color: #0ea5e9; color: #fff; }}
.table-scroll {{ overflow-x: auto; max-height: 62vh; overflow-y: auto; }}
table.data {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; }}
table.data th, table.data td {{
    border-bottom: 1px solid rgba(148,163,184,0.15);
    padding: 0.4rem 0.55rem; text-align: left; white-space: nowrap;
}}
table.data th {{
    position: sticky; top: 0; background: #1e293b; color: #94a3b8; font-weight: 600; z-index: 1;
}}
.snap-row {{ display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: flex-end; }}
.snap-row select {{ min-width: 280px; }}
h1 {{ font-size: 1.45rem; margin-bottom: 0.25rem; }}
</style>
</head>
<body>
<div class="container">
<nav class="breadcrumb"><a href="/">首页</a> / 数据披露 / {escape(title)}</nav>
<h1>{escape(title)}</h1>
<p class="muted">{escape(date_hint)}</p>

<div class="card">
  <div class="filters">
    <div>
      <label>信托产品（可多选）</label>
      <div class="tp-box" id="tp-box">{product_html}</div>
    </div>
    <div>
      <label for="as_of">{escape(date_label)}</label>
      <input type="date" id="as_of" name="as_of" value="{escape(as_of or '')}" required/>
    </div>
    <div>
      <label for="note">备注（冻结时可选）</label>
      <input type="text" id="note" name="note" placeholder="如：二季度披露" style="min-width:180px"/>
    </div>
  </div>
  <div class="actions">
    <button type="button" class="btn-primary" id="btn-preview">查看活数据</button>
    <button type="button" class="btn-secondary" id="btn-freeze">冻结当前时点</button>
    <button type="button" class="btn-ghost" id="btn-export-live">导出活数据</button>
  </div>
</div>

<div class="card">
  <h2 style="font-size:1rem;margin-bottom:0.5rem">已冻结快照</h2>
  <div class="snap-row">
    <div>
      <label for="snapshot_id">选择快照</label>
      <select id="snapshot_id"><option value="">— 请选择 —</option></select>
    </div>
    <div class="actions" style="margin-top:0">
      <button type="button" class="btn-ghost" id="btn-view-snap">查看快照</button>
      <button type="button" class="btn-ghost" id="btn-export-snap">导出快照</button>
      <button type="button" class="btn-danger" id="btn-delete-snap">删除快照</button>
    </div>
  </div>
  <p class="muted">同一产品与时点可多次冻结；冻结满 1 个月的快照不可删除。</p>
</div>

<div class="card">
  <div id="status" class="meta"></div>
  <div id="msg"></div>
  {tabs_html}
  {panels_html}
</div>
</div>

<script>
const KIND = {json.dumps(kind)};
const INITIAL_SNAPS = {snaps_json};
const HAS_TABS = {json.dumps(has_tabs)};

function selectedProductIds() {{
  return Array.from(document.querySelectorAll('input[name="trust_product_ids"]:checked'))
    .map((el) => el.value);
}}

function qs(params) {{
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {{
    if (v == null || v === '') return;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, x));
    else sp.set(k, v);
  }});
  return sp.toString();
}}

function setMsg(text, ok) {{
  const el = document.getElementById('msg');
  el.className = ok ? 'ok' : 'err';
  el.textContent = text || '';
}}

function fmtCell(v) {{
  if (v == null || v === '') return '—';
  return String(v);
}}

function renderTable(headers, keys, rows) {{
  if (!rows || !rows.length) {{
    return '<p class="muted">暂无数据</p>';
  }}
  let html = '<div class="table-scroll"><table class="data"><thead><tr>';
  headers.forEach((h) => {{ html += `<th>${{h}}</th>`; }});
  html += '</tr></thead><tbody>';
  rows.forEach((row) => {{
    html += '<tr>';
    keys.forEach((k) => {{ html += `<td>${{fmtCell(row[k])}}</td>`; }});
    html += '</tr>';
  }});
  html += '</tbody></table></div>';
  return html;
}}

function fillSnapshotSelect(snaps) {{
  const sel = document.getElementById('snapshot_id');
  const cur = sel.value;
  sel.innerHTML = '<option value="">— 请选择 —</option>';
  (snaps || []).forEach((s) => {{
    const label = `${{s.as_of_date}} · 冻结 ${{String(s.frozen_at || '').replace('T', ' ').slice(0, 19)}} · ${{s.product_names || ''}}`
      + (KIND === 'repayment'
        ? `（明细 ${{s.detail_row_count || 0}} / 计划 ${{s.plan_row_count || 0}}）`
        : `（监控 ${{s.monitor_row_count || 0}}）`);
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = label;
    sel.appendChild(opt);
  }});
  if (cur) sel.value = cur;
}}

function showPreview(data) {{
  const status = document.getElementById('status');
  if (data.mode === 'snapshot') {{
    const s = data.snapshot || {{}};
    status.textContent = `快照 #${{s.id}} · 时点 ${{s.as_of_date}} · 冻结于 ${{s.frozen_at || ''}} · ${{s.product_names || ''}}`;
  }} else {{
    status.textContent = `活数据 · ${{data.as_of_date || ''}} · 预览最多 200 行`;
  }}
  if (KIND === 'repayment') {{
    status.textContent += ` · 明细 ${{data.detail_total}} 行 / 计划 ${{data.plan_total}} 行`;
    document.getElementById('panel-detail').innerHTML =
      renderTable(data.detail_headers, data.detail_keys, data.details);
    document.getElementById('panel-plan').innerHTML =
      renderTable(data.plan_headers, data.plan_keys, data.plans);
  }} else {{
    status.textContent += ` · 监控 ${{data.monitor_total}} 行`;
    document.getElementById('panel-monitor').innerHTML =
      renderTable(data.headers, data.keys, data.rows);
  }}
}}

function detailText(body) {{
  const d = body && body.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join('; ');
  return (body && body.message) || '';
}}

async function apiGet(path, params) {{
  const url = path + (params ? ('?' + qs(params)) : '');
  const res = await fetch(url, {{ credentials: 'same-origin' }});
  const body = await res.json().catch(() => ({{}}));
  if (!res.ok) throw new Error(detailText(body) || ('请求失败 ' + res.status));
  return body;
}}

async function apiPost(path, params) {{
  const res = await fetch(path + '?' + qs(params), {{
    method: 'POST',
    credentials: 'same-origin',
  }});
  const body = await res.json().catch(() => ({{}}));
  if (!res.ok) throw new Error(detailText(body) || ('请求失败 ' + res.status));
  return body;
}}

async function apiDelete(path) {{
  const res = await fetch(path, {{ method: 'DELETE', credentials: 'same-origin' }});
  const body = await res.json().catch(() => ({{}}));
  if (!res.ok) throw new Error(detailText(body) || ('请求失败 ' + res.status));
  return body;
}}

function baseParams() {{
  const pids = selectedProductIds();
  const asOf = document.getElementById('as_of').value;
  if (!pids.length) throw new Error('请至少选择一个信托产品');
  if (!asOf) throw new Error('请选择' + {json.dumps(date_label)});
  return {{ trust_product_ids: pids, as_of: asOf }};
}}

document.getElementById('btn-preview').addEventListener('click', async () => {{
  try {{
    setMsg('');
    const data = await apiGet(`/disclosure/${{KIND}}/preview`, baseParams());
    showPreview(data);
  }} catch (e) {{ setMsg(e.message, false); }}
}});

document.getElementById('btn-freeze').addEventListener('click', async () => {{
  try {{
    setMsg('');
    const params = baseParams();
    const note = document.getElementById('note').value.trim();
    if (note) params.note = note;
    if (!confirm('确认按当前产品与时点冻结快照？')) return;
    const result = await apiPost(`/disclosure/${{KIND}}/freeze`, params);
    setMsg(`已冻结快照 #${{result.snapshot_id}}`, true);
    const snaps = await apiGet(`/disclosure/${{KIND}}/snapshots`);
    fillSnapshotSelect(snaps.items || []);
    document.getElementById('snapshot_id').value = String(result.snapshot_id);
    const data = await apiGet(`/disclosure/${{KIND}}/preview`, {{ snapshot_id: result.snapshot_id }});
    showPreview(data);
  }} catch (e) {{ setMsg(e.message, false); }}
}});

document.getElementById('btn-export-live').addEventListener('click', () => {{
  try {{
    setMsg('');
    const params = baseParams();
    window.location.href = `/disclosure/${{KIND}}/export?` + qs(params);
  }} catch (e) {{ setMsg(e.message, false); }}
}});

document.getElementById('btn-view-snap').addEventListener('click', async () => {{
  try {{
    setMsg('');
    const sid = document.getElementById('snapshot_id').value;
    if (!sid) throw new Error('请先选择快照');
    const data = await apiGet(`/disclosure/${{KIND}}/preview`, {{ snapshot_id: sid }});
    showPreview(data);
  }} catch (e) {{ setMsg(e.message, false); }}
}});

document.getElementById('btn-export-snap').addEventListener('click', () => {{
  try {{
    setMsg('');
    const sid = document.getElementById('snapshot_id').value;
    if (!sid) throw new Error('请先选择快照');
    window.location.href = `/disclosure/${{KIND}}/export?` + qs({{ snapshot_id: sid }});
  }} catch (e) {{ setMsg(e.message, false); }}
}});

document.getElementById('btn-delete-snap').addEventListener('click', async () => {{
  try {{
    setMsg('');
    const sid = document.getElementById('snapshot_id').value;
    if (!sid) throw new Error('请先选择快照');
    if (!confirm('确认物理删除该快照？此操作不可恢复。')) return;
    await apiDelete(`/disclosure/snapshots/${{sid}}`);
    setMsg(`已删除快照 #${{sid}}`, true);
    const snaps = await apiGet(`/disclosure/${{KIND}}/snapshots`);
    fillSnapshotSelect(snaps.items || []);
    document.getElementById('status').textContent = '';
    if (HAS_TABS) {{
      document.getElementById('panel-detail').innerHTML = '';
      document.getElementById('panel-plan').innerHTML = '';
    }} else {{
      document.getElementById('panel-monitor').innerHTML = '';
    }}
  }} catch (e) {{ setMsg(e.message, false); }}
}});

if (HAS_TABS) {{
  document.getElementById('view-tabs').addEventListener('click', (ev) => {{
    const btn = ev.target.closest('.tab');
    if (!btn) return;
    document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
    btn.classList.add('active');
    const tab = btn.dataset.tab;
    document.getElementById('panel-detail').style.display = tab === 'detail' ? '' : 'none';
    document.getElementById('panel-plan').style.display = tab === 'plan' ? '' : 'none';
  }});
}}

fillSnapshotSelect(INITIAL_SNAPS);
</script>
</body>
</html>"""
