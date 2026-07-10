"""Spatial map HTML — city gate + monitor map (P0)."""

import json
from html import escape

from app.overdue.ui_constants import DELINQUENCY_BUCKET_COLORS, DELINQUENCY_BUCKET_LABELS
from app.ui_css import BTN_CSS, PAGE_CHROME_CSS, STANDARD_HEADER_CSS


def _bucket_legend() -> str:
    parts = []
    for code, label in DELINQUENCY_BUCKET_LABELS.items():
        color = DELINQUENCY_BUCKET_COLORS.get(code, "#94a3b8")
        parts.append(
            f'<span class="legend-item">'
            f'<i style="background:{color}"></i>{escape(label)}</span>'
        )
    return "".join(parts)


BUCKET_ORDER = ["ES", "M1", "M2", "M3", "M3_PLUS"]


def render_spatial_map_gate_html(
    cities: list[dict],
    *,
    latest_run: dict | None,
    is_admin: bool,
) -> str:
    city_options = ""
    for c in cities:
        city = escape(str(c.get("city") or ""))
        monitor = int(c.get("monitor_count") or 0)
        geocoded = int(c.get("geocoded_count") or 0)
        city_options += (
            f'<option value="{city}">{city} '
            f"(监控 {monitor} · 可上图 {geocoded})</option>"
        )

    run_html = '<p class="muted">尚未执行地理编码任务</p>'
    if latest_run:
        run_html = (
            f"<p>最近任务：{escape(str(latest_run.get('status') or ''))} · "
            f"成功 {int(latest_run.get('success_count') or 0)} · "
            f"失败 {int(latest_run.get('failed_count') or 0)} · "
            f"{escape(str(latest_run.get('started_at') or ''))}</p>"
        )

    admin_btn = ""
    if is_admin:
        admin_btn = (
            '<button type="button" class="btn primary" id="geocode-refresh">'
            "刷新地理编码（批量）</button>"
        )
    else:
        admin_btn = '<p class="muted tiny">地理编码刷新需管理员权限</p>'

    admin_flag = "true" if is_admin else "false"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>地图监控 · 城市选择 · 贝源RSP平台</title>
    <style>
        {PAGE_CHROME_CSS}
        {STANDARD_HEADER_CSS}
        {BTN_CSS}
        body {{ padding: 1rem; }}
        .gate-layout {{ max-width: 960px; margin: 0 auto; }}
        .gate-card {{
            padding: 1.25rem; margin-bottom: 1rem;
            border: 1px solid rgba(255,255,255,0.1); border-radius: 12px;
            background: rgba(15,23,42,0.85);
        }}
        .gate-card label {{ display: block; margin: 0.75rem 0 0.35rem; color: #94a3b8; }}
        .gate-card select, .filters select, .filters input {{
            padding: 0.45rem; border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.15); background: rgba(0,0,0,0.25);
            color: #e2e8f0;
        }}
        .gate-card select {{ width: 100%; max-width: 420px; }}
        .gate-actions {{ display: flex; gap: 0.65rem; margin-top: 1rem; flex-wrap: wrap; align-items: center; }}
        #geocode-status {{ margin-top: 0.75rem; font-size: 0.85rem; color: #94a3b8; }}
        .filters {{
            display: flex; flex-wrap: wrap; gap: 0.65rem 1rem; align-items: flex-end;
            margin-bottom: 0.75rem;
        }}
        .filters label {{ font-size: 0.8rem; color: #94a3b8; display: block; margin-bottom: 0.25rem; }}
        .list-panel {{ margin-top: 0.5rem; }}
        .list-panel h2 {{ margin: 0 0 0.75rem; font-size: 1rem; }}
        .loc-list {{ display: flex; flex-direction: column; gap: 0.55rem; }}
        .loc-card {{
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            background: rgba(0,0,0,0.18);
            overflow: hidden;
        }}
        .loc-card-head {{
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 0.5rem 1rem;
            padding: 0.65rem 0.85rem;
            align-items: start;
        }}
        .loc-card-title {{
            font-size: 0.88rem; color: #e2e8f0; line-height: 1.45;
        }}
        .loc-card-title .meta {{
            color: #94a3b8; font-size: 0.78rem; margin-top: 0.15rem;
        }}
        .loc-card-title .addr-preview {{
            color: #cbd5e1; font-size: 0.8rem; margin-top: 0.25rem;
            overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        }}
        .loc-card-status {{ flex-shrink: 0; padding-top: 0.1rem; }}
        .loc-card-actions {{
            display: flex; flex-wrap: wrap; gap: 0.4rem 0.65rem;
            padding: 0 0.85rem 0.65rem;
            align-items: center;
        }}
        .loc-card-actions .btn {{ font-size: 0.75rem; padding: 0.25rem 0.55rem; }}
        .loc-card-actions a {{ font-size: 0.78rem; color: #38bdf8; text-decoration: none; }}
        .loc-card-actions a:hover {{ text-decoration: underline; }}
        .toggle-detail {{
            background: none; border: none; color: #38bdf8; cursor: pointer;
            font-size: 0.78rem; padding: 0; display: inline-flex; align-items: center; gap: 0.25rem;
        }}
        .toggle-detail:hover {{ text-decoration: underline; }}
        .toggle-detail .chev {{
            display: inline-block; transition: transform 0.15s;
            font-size: 0.65rem;
        }}
        .loc-card.is-open .toggle-detail .chev {{ transform: rotate(90deg); }}
        .loc-detail {{
            display: none;
            padding: 0.65rem 0.85rem 0.85rem;
            border-top: 1px solid rgba(255,255,255,0.06);
            background: rgba(0,0,0,0.12);
        }}
        .loc-card.is-open .loc-detail {{ display: block; }}
        .detail-section {{ margin-bottom: 0.75rem; }}
        .detail-section:last-child {{ margin-bottom: 0; }}
        .detail-section h4 {{
            margin: 0 0 0.35rem; font-size: 0.72rem; color: #64748b;
            text-transform: uppercase; letter-spacing: 0.04em;
        }}
        .detail-kv {{
            display: grid; grid-template-columns: 88px 1fr;
            gap: 0.25rem 0.65rem; font-size: 0.78rem; line-height: 1.45;
        }}
        .detail-kv dt {{ color: #64748b; margin: 0; }}
        .detail-kv dd {{
            color: #e2e8f0; margin: 0; word-break: break-word;
        }}
        .detail-kv dd.err {{ color: #fca5a5; }}
        .detail-kv dd.mono {{ font-family: ui-monospace, monospace; font-size: 0.74rem; }}
        .geo-badge {{
            display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px;
            font-size: 0.72rem; text-transform: lowercase; white-space: nowrap;
        }}
        .geo-success {{ background: rgba(34,197,94,0.2); color: #86efac; }}
        .geo-failed {{ background: rgba(239,68,68,0.2); color: #fca5a5; }}
        .geo-pending {{ background: rgba(234,179,8,0.2); color: #fde047; }}
        .geo-skipped {{ background: rgba(148,163,184,0.2); color: #cbd5e1; }}
        .pager {{
            display: flex; gap: 0.75rem; align-items: center; margin-top: 0.75rem;
            font-size: 0.85rem; color: #94a3b8;
        }}
        .empty-list {{ padding: 1.5rem; text-align: center; color: #64748b; }}
    </style>
</head>
<body>
    <nav class="breadcrumb"><a href="/">首页</a> / 地图监控</nav>
    <div class="gate-layout">
        <div class="gate-card">
            <h1 style="margin:0 0 0.5rem;font-size:1.15rem;">地图监控 · 选择城市</h1>
            <p class="muted" style="margin:0;">城市来自发行数据；「未知」城市不提供地图入口。</p>
            <label for="city-select">城市</label>
            <select id="city-select">
                <option value="">请选择城市</option>
                {city_options}
            </select>
            <div class="gate-actions">
                <button type="button" class="btn primary" id="open-map" disabled>打开地图</button>
                {admin_btn}
            </div>
            <div id="geocode-status">{run_html}</div>
        </div>

        <div class="gate-card list-panel">
            <h2>地址与 Geocode 明细</h2>
            <div class="filters">
                <div>
                    <label for="filter-status">Geocode 状态</label>
                    <select id="filter-status" disabled>
                        <option value="">全部</option>
                        <option value="pending">pending</option>
                        <option value="success">success</option>
                        <option value="failed">failed</option>
                        <option value="skipped">skipped</option>
                    </select>
                </div>
                <div>
                    <label for="filter-q">搜索</label>
                    <input id="filter-q" type="search" placeholder="资产编号 / 地址 / 合同" disabled style="min-width:200px;">
                </div>
                <button type="button" class="btn" id="filter-apply" disabled>筛选</button>
            </div>
            <div id="list-placeholder" class="empty-list">请先选择城市</div>
            <div id="list-wrap" hidden>
                <div id="list-body" class="loc-list"></div>
                <div class="pager">
                    <button type="button" class="btn" id="page-prev" disabled>上一页</button>
                    <span id="page-info">—</span>
                    <button type="button" class="btn" id="page-next" disabled>下一页</button>
                </div>
            </div>
        </div>
    </div>
    <script>
    (function() {{
        var IS_ADMIN = {admin_flag};
        var sel = document.getElementById('city-select');
        var openBtn = document.getElementById('open-map');
        var filterStatus = document.getElementById('filter-status');
        var filterQ = document.getElementById('filter-q');
        var filterApply = document.getElementById('filter-apply');
        var listPlaceholder = document.getElementById('list-placeholder');
        var listWrap = document.getElementById('list-wrap');
        var listBody = document.getElementById('list-body');
        var pagePrev = document.getElementById('page-prev');
        var pageNext = document.getElementById('page-next');
        var pageInfo = document.getElementById('page-info');
        var state = {{ city: '', page: 1, pageSize: 50, total: 0 }};

        function esc(s) {{
            if (s == null || s === undefined) return '';
            return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
        }}

        function geoBadge(st) {{
            var cls = 'geo-pending';
            if (st === 'success') cls = 'geo-success';
            else if (st === 'failed') cls = 'geo-failed';
            else if (st === 'skipped') cls = 'geo-skipped';
            return '<span class="geo-badge ' + cls + '">' + esc(st || '—') + '</span>';
        }}

        function detailKv(label, val, cls) {{
            if (val == null || val === '') return '';
            var c = cls ? ' class="' + cls + '"' : '';
            return '<dt>' + esc(label) + '</dt><dd' + c + '>' + esc(val) + '</dd>';
        }}

        function renderRow(it) {{
            var addr = it.issuance_address || it.raw_address || '—';
            var refreshBtn = '';
            if (IS_ADMIN) {{
                refreshBtn = '<button type="button" class="btn row-refresh" data-id="' + it.location_id + '">刷新 Geocode</button>';
            }}
            var wb = it.workbench_url
                ? '<a href="' + esc(it.workbench_url) + '" target="_blank" rel="noopener">工作台</a>'
                : '';
            var listing = it.listing_label && it.listing_label !== '—'
                ? esc(it.listing_label) : '';
            var metaParts = [esc(it.trust_product_name), esc(it.asset_code)];
            if (listing) metaParts.push(listing);
            var meta = metaParts.join(' · ');
            var detail = ''
                + '<div class="detail-section"><h4>地址</h4><dl class="detail-kv">'
                + detailKv('发行地址', it.issuance_address || it.raw_address)
                + detailKv('回填地址', it.raw_address)
                + detailKv('格式化地址', it.formatted_address)
                + detailKv('城市', it.city)
                + detailKv('省/区', [it.province, it.district].filter(Boolean).join(' / ') || null)
                + '</dl></div>'
                + '<div class="detail-section"><h4>Geocode</h4><dl class="detail-kv">'
                + detailKv('状态', it.geocode_status)
                + detailKv('坐标', it.coordinates, 'mono')
                + detailKv('精度', it.geocode_level)
                + detailKv('提供商', it.geocode_provider)
                + detailKv('编码时间', it.geocoded_at)
                + detailKv('错误', it.geocode_error, 'err')
                + '</dl></div>'
                + '<div class="detail-section"><h4>溯源</h4><dl class="detail-kv">'
                + detailKv('托管编号', it.custody_asset_code, 'mono')
                + detailKv('合同', it.contract_name)
                + detailKv('债务人', it.debtor_name)
                + detailKv('发行城市', it.issuance_city)
                + detailKv('来源', it.location_source)
                + detailKv('发行记录 ID', it.source_issuance_id, 'mono')
                + detailKv('产品 ID', it.trust_product_id, 'mono')
                + detailKv('记录 ID', it.location_id, 'mono')
                + detailKv('地址哈希', it.address_hash, 'mono')
                + detailKv('创建', it.created_at)
                + detailKv('更新', it.updated_at)
                + '</dl></div>';
            return '<article class="loc-card" data-location-id="' + it.location_id + '">'
                + '<div class="loc-card-head">'
                + '<div class="loc-card-title">'
                + '<div>' + meta + '</div>'
                + '<div class="addr-preview" title="' + esc(addr) + '">' + esc(addr) + '</div>'
                + '</div>'
                + '<div class="loc-card-status">' + geoBadge(it.geocode_status) + '</div>'
                + '</div>'
                + '<div class="loc-card-actions">'
                + '<button type="button" class="toggle-detail" aria-expanded="false">'
                + '<span class="chev">▶</span> 详情</button>'
                + refreshBtn + wb
                + '</div>'
                + '<div class="loc-detail">' + detail + '</div>'
                + '</article>';
        }}

        function updatePager() {{
            var pages = Math.max(1, Math.ceil(state.total / state.pageSize));
            pageInfo.textContent = '第 ' + state.page + ' / ' + pages + ' 页 · 共 ' + state.total + ' 条';
            pagePrev.disabled = state.page <= 1;
            pageNext.disabled = state.page >= pages;
        }}

        function loadList() {{
            if (!state.city) {{
                listPlaceholder.hidden = false;
                listPlaceholder.textContent = '请先选择城市';
                listWrap.hidden = true;
                return;
            }}
            listPlaceholder.hidden = false;
            listPlaceholder.textContent = '加载中…';
            listWrap.hidden = true;
            var params = new URLSearchParams({{
                city: state.city,
                page: String(state.page),
                page_size: String(state.pageSize)
            }});
            if (filterStatus.value) params.set('geocode_status', filterStatus.value);
            if (filterQ.value.trim()) params.set('q', filterQ.value.trim());
            fetch('/spatial/locations/data?' + params.toString(), {{ credentials: 'same-origin' }})
                .then(function(r) {{ return r.json(); }})
                .then(function(data) {{
                    state.total = data.total || 0;
                    var items = data.items || [];
                    listBody.innerHTML = items.map(renderRow).join('') || '<div class="empty-list">无数据</div>';
                    listPlaceholder.hidden = true;
                    listWrap.hidden = false;
                    updatePager();
                }})
                .catch(function() {{
                    listPlaceholder.textContent = '加载失败';
                }});
        }}

        function setCityEnabled(on) {{
            openBtn.disabled = !on;
            filterStatus.disabled = !on;
            filterQ.disabled = !on;
            filterApply.disabled = !on;
        }}

        sel.addEventListener('change', function() {{
            state.city = sel.value;
            state.page = 1;
            setCityEnabled(!!state.city);
            loadList();
        }});

        filterApply.addEventListener('click', function() {{
            state.page = 1;
            loadList();
        }});
        filterQ.addEventListener('keydown', function(e) {{
            if (e.key === 'Enter') {{ state.page = 1; loadList(); }}
        }});

        pagePrev.addEventListener('click', function() {{
            if (state.page > 1) {{ state.page--; loadList(); }}
        }});
        pageNext.addEventListener('click', function() {{
            var pages = Math.ceil(state.total / state.pageSize);
            if (state.page < pages) {{ state.page++; loadList(); }}
        }});

        openBtn.addEventListener('click', function() {{
            if (!sel.value) return;
            window.location.href = '/spatial/map/view?city=' + encodeURIComponent(sel.value);
        }});

        listBody.addEventListener('click', function(e) {{
            var toggle = e.target.closest('.toggle-detail');
            if (toggle) {{
                var card = toggle.closest('.loc-card');
                if (!card) return;
                var open = card.classList.toggle('is-open');
                toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
                return;
            }}
            var btn = e.target.closest('.row-refresh');
            if (!btn) return;
            var id = btn.getAttribute('data-id');
            var card = listBody.querySelector('.loc-card[data-location-id="' + id + '"]');
            var wasOpen = card && card.classList.contains('is-open');
            btn.disabled = true;
            btn.textContent = '刷新中…';
            fetch('/spatial/geocode/refresh/' + id, {{ method: 'POST', credentials: 'same-origin' }})
                .then(function(r) {{
                    if (!r.ok) return r.json().then(function(j) {{ throw new Error(j.detail || r.status); }});
                    return r.json();
                }})
                .then(function(data) {{
                    if (card && data.item) {{
                        card.outerHTML = renderRow(data.item);
                        if (wasOpen) {{
                            var next = listBody.querySelector('.loc-card[data-location-id="' + id + '"]');
                            if (next) {{
                                next.classList.add('is-open');
                                var t = next.querySelector('.toggle-detail');
                                if (t) t.setAttribute('aria-expanded', 'true');
                            }}
                        }}
                    }} else {{
                        loadList();
                    }}
                }})
                .catch(function(err) {{
                    alert(err.message || '刷新失败');
                    btn.disabled = false;
                    btn.textContent = '刷新 Geocode';
                }});
        }});

        var refreshBtn = document.getElementById('geocode-refresh');
        if (refreshBtn) {{
            refreshBtn.addEventListener('click', function() {{
                refreshBtn.disabled = true;
                fetch('/spatial/geocode/refresh', {{ method: 'POST', credentials: 'same-origin' }})
                    .then(function(r) {{
                        if (!r.ok) return r.json().then(function(j) {{ throw new Error(j.detail || r.status); }});
                        return r.json();
                    }})
                    .then(function() {{
                        document.getElementById('geocode-status').textContent = '地理编码任务已启动，请稍后刷新页面查看状态';
                    }})
                    .catch(function(e) {{
                        alert(e.message || '启动失败');
                    }})
                    .finally(function() {{ refreshBtn.disabled = false; }});
            }});
        }}
    }})();
    </script>
</body>
</html>"""


def render_spatial_map_view_html(
    city: str,
    *,
    amap_key: str,
    map_data_url: str,
    city_center: list[float],
) -> str:
    city_esc = escape(city)
    center_json = json.dumps(city_center)
    bucket_colors_json = json.dumps(DELINQUENCY_BUCKET_COLORS)
    bucket_labels_json = json.dumps(DELINQUENCY_BUCKET_LABELS)
    bucket_order_json = json.dumps(BUCKET_ORDER)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{city_esc} · 地图监控 · 贝源RSP平台</title>
    <style>
        {PAGE_CHROME_CSS}
        {BTN_CSS}
        html, body {{ height: 100%; margin: 0; }}
        body {{ display: flex; flex-direction: column; background: #0f172a; }}
        .map-header {{
            border-bottom: 1px solid rgba(255,255,255,0.08);
            color: #e2e8f0; font-size: 0.85rem;
        }}
        .map-toolbar-row, .map-filter-row {{
            display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem 0.85rem;
            padding: 0.5rem 0.85rem;
        }}
        .map-filter-row {{
            border-top: 1px solid rgba(255,255,255,0.05);
            background: rgba(0,0,0,0.12);
        }}
        .map-toolbar-row a {{ color: #38bdf8; text-decoration: none; }}
        .map-toolbar-row a:hover {{ text-decoration: underline; }}
        #map-stats {{ color: #94a3b8; }}
        .filter-label {{ color: #64748b; font-size: 0.78rem; white-space: nowrap; }}
        .filter-chips {{ display: flex; flex-wrap: wrap; gap: 0.35rem; }}
        .bucket-chip {{
            display: inline-flex; align-items: center; gap: 0.35rem;
            padding: 0.2rem 0.55rem; border-radius: 999px; cursor: pointer;
            border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.04);
            color: #e2e8f0; font-size: 0.78rem; user-select: none;
        }}
        .bucket-chip.off {{
            opacity: 0.45; background: rgba(0,0,0,0.2);
            text-decoration: line-through;
        }}
        .bucket-chip i {{
            display: inline-block; border-radius: 50%; border: 1px solid rgba(255,255,255,0.35);
            flex-shrink: 0;
        }}
        .bucket-chip .cnt {{ color: #94a3b8; font-size: 0.72rem; }}
        .filter-presets {{ display: flex; gap: 0.35rem; }}
        .filter-presets .btn {{ font-size: 0.72rem; padding: 0.2rem 0.5rem; }}
        .product-filter {{ position: relative; }}
        .product-filter summary {{
            cursor: pointer; list-style: none; padding: 0.2rem 0.55rem;
            border-radius: 6px; border: 1px solid rgba(255,255,255,0.12);
            background: rgba(255,255,255,0.04); color: #e2e8f0; font-size: 0.78rem;
        }}
        .product-filter summary::-webkit-details-marker {{ display: none; }}
        .product-panel {{
            position: absolute; top: calc(100% + 4px); left: 0; z-index: 100;
            min-width: 220px; max-height: 240px; overflow: auto;
            padding: 0.5rem; border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.12); background: #1e293b;
            box-shadow: 0 8px 24px rgba(0,0,0,0.35);
        }}
        .product-panel label {{
            display: flex; align-items: center; gap: 0.45rem;
            padding: 0.25rem 0; font-size: 0.78rem; color: #e2e8f0; cursor: pointer;
        }}
        .product-panel .panel-actions {{
            display: flex; gap: 0.5rem; margin-bottom: 0.35rem;
            padding-bottom: 0.35rem; border-bottom: 1px solid rgba(255,255,255,0.08);
        }}
        .product-panel .panel-actions button {{
            background: none; border: none; color: #38bdf8; cursor: pointer;
            font-size: 0.72rem; padding: 0;
        }}
        #map-container {{ flex: 1; min-height: 400px; }}
        #filter-empty-hint {{
            display: none; padding: 0.35rem 0.85rem; font-size: 0.78rem;
            color: #fde047; background: rgba(234,179,8,0.08);
            border-bottom: 1px solid rgba(234,179,8,0.15);
        }}
    </style>
    <script src="https://webapi.amap.com/maps?v=2.0&key={escape(amap_key)}"></script>
</head>
<body>
    <div class="map-header">
        <div class="map-toolbar-row">
            <a href="/spatial/map">← 选择城市</a>
            <strong>{city_esc}</strong>
            <span id="map-stats">加载中…</span>
        </div>
        <div class="map-filter-row">
            <span class="filter-label">M级</span>
            <div id="bucket-filters" class="filter-chips"></div>
            <div class="filter-presets">
                <button type="button" class="btn" id="preset-m2plus">仅 M2+</button>
                <button type="button" class="btn" id="preset-all">全选</button>
            </div>
            <span class="filter-label">产品</span>
            <details class="product-filter" id="product-filter">
                <summary id="product-summary">全部产品</summary>
                <div class="product-panel">
                    <div class="panel-actions">
                        <button type="button" id="product-select-all">全选</button>
                        <button type="button" id="product-clear-all">清空</button>
                    </div>
                    <div id="product-checkboxes"></div>
                </div>
            </details>
        </div>
    </div>
    <div id="filter-empty-hint">当前筛选条件下无资产点</div>
    <div id="map-container"></div>
    <script>
    (function() {{
        var bucketColors = {bucket_colors_json};
        var bucketLabels = {bucket_labels_json};
        var bucketOrder = {bucket_order_json};
        var dataUrl = {json.dumps(map_data_url)};
        var cityCenter = {center_json};
        var cityZoom = 11;

        var markerStyles = {{
            ES: {{ radius: 5, strokeWeight: 1, zIndex: 10, halo: false, chipSize: 8 }},
            M1: {{ radius: 5, strokeWeight: 1, zIndex: 20, halo: false, chipSize: 8 }},
            M2: {{ radius: 8, strokeWeight: 2, zIndex: 30, halo: false, chipSize: 11 }},
            M3: {{ radius: 9, strokeWeight: 2, zIndex: 40, halo: false, chipSize: 12 }},
            M3_PLUS: {{ radius: 10, strokeWeight: 3, zIndex: 50, halo: true, chipSize: 13 }}
        }};

        var map = null;
        var allItems = [];
        var markerEntries = [];
        var activeBuckets = new Set(bucketOrder);
        var activeProducts = new Set();

        function updateStats(visibleCount) {{
            var total = allItems.length;
            var pc = activeProducts.size;
            document.getElementById('map-stats').textContent =
                '显示 ' + visibleCount + ' / ' + total + ' 点 · '
                + pc + ' / ' + (new Set(allItems.map(function(i) {{ return i.trust_product_id; }}))).size + ' 产品';
            document.getElementById('filter-empty-hint').style.display =
                visibleCount === 0 && total > 0 ? 'block' : 'none';
        }}

        function isVisible(it) {{
            return activeBuckets.has(it.delinquency_bucket)
                && activeProducts.has(it.trust_product_id);
        }}

        function applyFilters() {{
            markerEntries.forEach(function(entry) {{
                var show = isVisible(entry.item);
                entry.layers.forEach(function(layer) {{
                    if (show) layer.show();
                    else layer.hide();
                }});
            }});
            updateStats(allItems.filter(isVisible).length);
            bucketOrder.forEach(function(code) {{
                var chip = document.querySelector('.bucket-chip[data-bucket="' + code + '"]');
                if (chip) chip.classList.toggle('off', !activeBuckets.has(code));
            }});
            updateProductSummary();
        }}

        function updateProductSummary() {{
            var products = [];
            var seen = {{}};
            allItems.forEach(function(it) {{
                if (!seen[it.trust_product_id]) {{
                    seen[it.trust_product_id] = true;
                    products.push(it);
                }}
            }});
            var n = activeProducts.size;
            var el = document.getElementById('product-summary');
            if (n === 0) el.textContent = '未选产品';
            else if (n === products.length) el.textContent = '全部产品 (' + n + ')';
            else el.textContent = '已选 ' + n + ' 个产品';
        }}

        function buildBucketFilters(byBucket) {{
            var host = document.getElementById('bucket-filters');
            host.innerHTML = '';
            bucketOrder.forEach(function(code) {{
                var color = bucketColors[code] || '#94a3b8';
                var label = bucketLabels[code] || code;
                var st = markerStyles[code] || markerStyles.M1;
                var cnt = (byBucket && byBucket[code]) || 0;
                var chip = document.createElement('button');
                chip.type = 'button';
                chip.className = 'bucket-chip';
                chip.setAttribute('data-bucket', code);
                chip.innerHTML = '<i style="width:' + st.chipSize + 'px;height:' + st.chipSize
                    + 'px;background:' + color + '"></i>'
                    + label + ' <span class="cnt">' + cnt + '</span>';
                chip.addEventListener('click', function() {{
                    if (activeBuckets.has(code)) activeBuckets.delete(code);
                    else activeBuckets.add(code);
                    applyFilters();
                }});
                host.appendChild(chip);
            }});
        }}

        function buildProductFilters(products) {{
            var host = document.getElementById('product-checkboxes');
            host.innerHTML = '';
            activeProducts = new Set();
            (products || []).forEach(function(p) {{
                activeProducts.add(p.trust_product_id);
                var id = 'prod-' + p.trust_product_id;
                var label = document.createElement('label');
                label.innerHTML = '<input type="checkbox" checked data-pid="' + p.trust_product_id
                    + '"> ' + (p.trust_product_name || ('产品 ' + p.trust_product_id))
                    + ' <span class="cnt">(' + p.count + ')</span>';
                host.appendChild(label);
            }});
            host.querySelectorAll('input[type=checkbox]').forEach(function(cb) {{
                cb.addEventListener('change', function() {{
                    var pid = parseInt(cb.getAttribute('data-pid'), 10);
                    if (cb.checked) activeProducts.add(pid);
                    else activeProducts.delete(pid);
                    applyFilters();
                }});
            }});
            document.getElementById('product-select-all').onclick = function() {{
                host.querySelectorAll('input[type=checkbox]').forEach(function(cb) {{
                    cb.checked = true;
                    activeProducts.add(parseInt(cb.getAttribute('data-pid'), 10));
                }});
                applyFilters();
            }};
            document.getElementById('product-clear-all').onclick = function() {{
                host.querySelectorAll('input[type=checkbox]').forEach(function(cb) {{
                    cb.checked = false;
                }});
                activeProducts.clear();
                applyFilters();
            }};
            updateProductSummary();
        }}

        function createMarkers(items) {{
            markerEntries = [];
            var sorted = items.slice().sort(function(a, b) {{
                var za = (markerStyles[a.delinquency_bucket] || markerStyles.M1).zIndex;
                var zb = (markerStyles[b.delinquency_bucket] || markerStyles.M1).zIndex;
                return za - zb;
            }});
            sorted.forEach(function(it) {{
                var pos = [it.longitude, it.latitude];
                var bucket = it.delinquency_bucket || 'M1';
                var color = bucketColors[bucket] || '#94a3b8';
                var st = markerStyles[bucket] || markerStyles.M1;
                var layers = [];
                if (st.halo) {{
                    var halo = new AMap.CircleMarker({{
                        center: pos,
                        radius: st.radius + 6,
                        strokeWeight: 0,
                        fillColor: color,
                        fillOpacity: 0.18,
                        zIndex: st.zIndex - 1
                    }});
                    halo.setMap(map);
                    layers.push(halo);
                }}
                var marker = new AMap.CircleMarker({{
                    center: pos,
                    radius: st.radius,
                    strokeColor: '#ffffff',
                    strokeWeight: st.strokeWeight,
                    strokeOpacity: 0.95,
                    fillColor: color,
                    fillOpacity: 0.88,
                    zIndex: st.zIndex
                }});
                marker.setMap(map);
                marker.on('click', function() {{
                    if (it.workbench_url) window.open(it.workbench_url, '_blank');
                }});
                layers.push(marker);
                markerEntries.push({{ item: it, layers: layers }});
            }});
        }}

        document.getElementById('preset-m2plus').addEventListener('click', function() {{
            activeBuckets = new Set(['M2', 'M3', 'M3_PLUS']);
            applyFilters();
        }});
        document.getElementById('preset-all').addEventListener('click', function() {{
            activeBuckets = new Set(bucketOrder);
            applyFilters();
        }});

        fetch(dataUrl, {{ credentials: 'same-origin' }})
            .then(function(r) {{ return r.json(); }})
            .then(function(data) {{
                allItems = data.items || [];
                var stats = data.stats || {{}};
                map = new AMap.Map('map-container', {{
                    center: cityCenter,
                    zoom: cityZoom,
                    viewMode: '2D'
                }});
                buildBucketFilters(stats.by_bucket || {{}});
                buildProductFilters(stats.products || []);
                if (!allItems.length) {{
                    map.setCenter(cityCenter);
                    map.setZoom(cityZoom);
                    updateStats(0);
                    return;
                }}
                createMarkers(allItems);
                applyFilters();
                var fitTargets = [];
                markerEntries.forEach(function(e) {{ fitTargets.push.apply(fitTargets, e.layers); }});
                if (fitTargets.length) map.setFitView(fitTargets, false, [40, 40, 40, 40]);
            }})
            .catch(function() {{
                document.getElementById('map-stats').textContent = '加载失败';
            }});
    }})();
    </script>
</body>
</html>"""
