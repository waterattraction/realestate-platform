"""Shared inline CSS snippets for HTML pages."""

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
