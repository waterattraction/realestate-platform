"""Shared inline CSS snippets for HTML pages."""

# 标准业务页 Chrome：背景、容器、面包屑（Dashboard 首页仅复用背景时可内联同色值）
PAGE_CHROME_CSS = """
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
            min-height: 100vh;
            color: #e2e8f0;
            padding: 2rem 1rem;
        }
        .container {
            max-width: 1200px;
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
