"""浏览器登录页与用户栏 HTML."""

from __future__ import annotations

from html import escape

USER_BAR_CSS = """
.auth-topbar {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 1rem;
    position: absolute;
    top: 0.4rem;
    right: 1rem;
    margin: 0;
    padding: 0;
    max-width: none;
    width: auto;
    z-index: 10;
    font-size: 0.9rem;
    color: #94a3b8;
}
.auth-topbar form { margin: 0; }
.auth-topbar button {
    cursor: pointer;
    font: inherit;
    margin: 0;
    padding: 0.35rem 0.75rem;
    border-radius: 8px;
    border: 1px solid rgba(255,255,255,0.15);
    background: rgba(15,23,42,0.8);
    color: #f8fafc;
}
.auth-topbar button:hover { border-color: #38bdf8; color: #38bdf8; }
"""


def user_bar_div(username: str) -> str:
    return f"""<div class="auth-topbar">
    <span>当前用户：{escape(username)}</span>
    <form method="post" action="/logout">
        <button type="submit">退出登录</button>
    </form>
</div>"""


def render_user_bar(username: str) -> str:
    return f"""
<style>{USER_BAR_CSS}</style>
{user_bar_div(username)}"""


def inject_user_bar(html: str, username: str) -> str:
    bar = render_user_bar(username)
    marker = "<body"
    idx = html.find(marker)
    if idx >= 0:
        end = html.find(">", idx)
        if end >= 0:
            return html[: end + 1] + "\n" + bar + html[end + 1 :]
    return bar + html


def render_login_page(error: str | None = None, next_url: str = "/") -> str:
    err = f'<p class="error">{escape(error)}</p>' if error else ""
    nxt = escape(next_url or "/")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>登录 — 房地产资产证券化平台</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
            min-height: 100vh; color: #e2e8f0;
            display: flex; align-items: center; justify-content: center; padding: 1rem;
        }}
        .card {{
            width: 100%; max-width: 400px;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px; padding: 2rem;
        }}
        h1 {{ font-size: 1.25rem; color: #f8fafc; margin-bottom: 0.5rem; }}
        p.muted {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 1.5rem; }}
        label {{ display: block; font-size: 0.85rem; color: #94a3b8; margin: 1rem 0 0.35rem; }}
        input {{
            width: 100%; font: inherit; padding: 0.6rem 0.75rem; border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.15);
            background: rgba(15,23,42,0.8); color: #f8fafc;
        }}
        button {{
            width: 100%; margin-top: 1.5rem; cursor: pointer; font: inherit;
            padding: 0.65rem; border-radius: 8px; border: none;
            background: #0ea5e9; color: #fff; font-weight: 600;
        }}
        button:hover {{ background: #0284c7; }}
        .error {{ color: #f87171; font-size: 0.9rem; margin-top: 1rem; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>登录</h1>
        <p class="muted">房地产资产证券化平台</p>
        <form method="post" action="/login">
            <input type="hidden" name="next" value="{nxt}">
            <label for="username">用户名</label>
            <input id="username" name="username" type="text" autocomplete="username" required>
            <label for="password">密码</label>
            <input id="password" name="password" type="password" autocomplete="current-password" required>
            <button type="submit">登录</button>
        </form>
        {err}
    </div>
</body>
</html>"""
