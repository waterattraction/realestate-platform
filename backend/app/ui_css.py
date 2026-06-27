"""Shared inline CSS snippets for HTML pages."""

# 标准业务页 Chrome：背景、容器、面包屑
PAGE_CHROME_CSS = """
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
            min-height: 100vh;
            color: #e2e8f0;
            padding: 0.4rem 1rem 2rem;
            position: relative;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        a {
            color: #38bdf8;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        .breadcrumb {
            font-size: 0.875rem;
            color: #94a3b8;
            margin-bottom: 1.5rem;
            line-height: 2rem;
        }
"""

# 首页 Dashboard：仅覆盖 body 顶边（Chrome 其余与标准页一致）
DASHBOARD_BODY_CSS = """
        body.dashboard-page {
            padding: 2rem 1rem 0.75rem;
        }
"""

# 工作台：底边更紧凑
WORKBENCH_BODY_CSS = """
        body.workbench-page {
            padding: 0.4rem 1rem 0;
        }
"""

# 表单控件（不含 button，避免污染 auth-topbar）
FORM_FIELD_CSS = """
        .container input, .container select,
        .filter-form select, .filter-form input[type="text"] {
            font: inherit;
            padding: 0.5rem 0.75rem;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.15);
            background: rgba(15,23,42,0.8);
            color: #f8fafc;
        }
        .filter-form select, .filter-form input[type="text"] {
            padding: 0.35rem 0.5rem;
            font-size: 0.82rem;
            background: rgba(0,0,0,0.2);
        }
        label { display: block; font-size: 0.85rem; color: #94a3b8; margin: 0.75rem 0 0.25rem; }
        .filters > div { min-width: 140px; }
        .snapshot-toggle input { width: auto; margin: 0; }
"""

# 全站按钮语义（禁止裸 button 选择器）
BTN_CSS = """
        .btn-primary {
            cursor: pointer;
            font: inherit;
            padding: 0.5rem 0.75rem;
            border-radius: 8px;
            border: 1px solid #0ea5e9;
            background: #0ea5e9;
            color: #f8fafc;
            margin-top: 1rem;
        }
        .btn-secondary {
            cursor: pointer;
            font: inherit;
            padding: 0.5rem 0.75rem;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.15);
            background: transparent;
            color: #f8fafc;
            margin-top: 1rem;
            margin-left: 0.5rem;
        }
        .filters .btn-primary, .sheet-toolbar .btn-secondary { margin-top: 0; }
        .tab-btn, .btn-pill {
            padding: 0.35rem 0.75rem;
            border-radius: 999px;
            border: 1px solid rgba(255,255,255,0.15);
            background: rgba(255,255,255,0.04);
            color: #94a3b8;
            cursor: pointer;
            font-size: 0.82rem;
            margin-top: 0;
        }
        .tab-btn.active, .btn-pill.active {
            background: rgba(56, 189, 248, 0.2);
            border-color: rgba(56, 189, 248, 0.45);
            color: #e2e8f0;
        }
        .btn-recalc, .btn-outline {
            padding: 0.45rem 0.9rem;
            border-radius: 8px;
            border: 1px solid rgba(56, 189, 248, 0.45);
            background: rgba(56, 189, 248, 0.15);
            color: #e2e8f0;
            cursor: pointer;
            font-size: 0.85rem;
            white-space: nowrap;
            margin-top: 0;
        }
        .btn-recalc:hover, .btn-outline:hover { background: rgba(56, 189, 248, 0.28); }
        .btn-recalc:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-compact {
            padding: 0.35rem 0.75rem;
            font-size: 0.8rem;
            height: 36px;
            box-sizing: border-box;
            cursor: pointer;
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.2);
            background: rgba(15,23,42,0.8);
            color: #f8fafc;
            margin-top: 0;
        }
"""

STANDARD_HEADER_CSS = """
        header h1, .page-header .brand h1 {
            font-size: 1.5rem;
            font-weight: 700;
            color: #f8fafc;
        }
        body.dashboard-page .brand h1 {
            font-size: 1.3rem;
            line-height: 1.25;
        }
"""

# 对账表格：单行完整展示，容器横向滚动，禁止截断/折行
TABLE_SCROLL_CSS = """
        .table-wrap {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            max-width: 100%;
        }
        table {
            width: max-content;
            min-width: 100%;
            border-collapse: collapse;
        }
        th, td {
            white-space: nowrap;
            overflow: visible;
            text-overflow: clip;
            word-break: keep-all;
            overflow-wrap: normal;
            vertical-align: middle;
        }
        td.mono, th.mono,
        .col-custody, .col-source-split, .col-asset-code, .col-source-sheet-name {
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.82rem;
        }
        .asset-id {
            white-space: nowrap;
        }
"""
