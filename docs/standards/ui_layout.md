# UI 页面布局规范

平台 HTML 页面（FastAPI `HTMLResponse` 内联页）的布局与 Chrome 约定。数据语义见 [`canonical/`](../canonical/README.md)；本文件只规定 **视觉骨架与组件模式**。

> **核心原则**：**Chrome 统一，内容区可按页面类型差异化。** 压缩单屏应动内容区，不动顶栏呼吸感。

---

## 1. 适用范围

| 适用 | 不适用 |
|------|--------|
| `backend/app/**/*.py` 内联 HTML | JSON API 响应 |
| `issuance_html.py` / `assetinfo_html.py` / `html/render.py` 等页面壳 | 前端框架（本项目暂无） |
| 登录页 `auth_html.py`（Chrome 子集） | 第三方静态资源 |

新增或修改任何业务 HTML 页面前，须对照本文与 [`.cursor/rules/ui_layout.mdc`](../../.cursor/rules/ui_layout.mdc)。

---

## 2. 页面模式：Standard / Dashboard

| 模式 | 路由示例 | Chrome | 内容区密度 |
|------|----------|--------|------------|
| **Standard** | `/issuance/*`、`/assetinfo/*`、`/overdue`、`/risk/*`、资产包详情、逾期/风险工作台 | **全站标准** | 正常，允许纵向滚动 |
| **Dashboard** | **`GET /` 首页仅此一个** | **与 Standard 相同** | KPI 以下可 **紧凑**，桌面目标尽量一屏 |

### 相同点（Chrome）

- `body` 顶边留白、`auth-topbar`、容器宽度、背景与语义色一致。
- 用户栏独立一行，不并入标题栏。

### 不同点（内容区）

| 项 | Standard | Dashboard |
|----|----------|-----------|
| 面包屑 | **必须有** | **无** |
| `h1` 字号 | 1.5–1.75rem | 1.25–1.35rem |
| 区块间距 | `1–1.25rem` | KPI 以下可用 `0.6–0.75rem` |
| KPI / 导航 | 按页而定 | 顶栏 KPI 条 + 双列 ops + 3 风险卡 |
| 空态 | 单行或简短说明 | **禁止** 大块空指标占位 |

**Dashboard 可以压缩 KPI 以下内容区，但不能压缩 Chrome。** 不允许为了单屏把桌面 `body` 顶边压到 **&lt; 1rem**。

---

## 3. 页面骨架（Chrome）

推荐 DOM 结构：

```text
<body>                          ← 外边距见 §4
  <div class="auth-topbar">     ← 登录后独立一行（§3.1）
  <div class="container">       ← max-width 1100–1200px
    <nav class="breadcrumb">    ← 子页必有；首页省略
    <header class="page-header">← 品牌或页标题
    <main>                        ← 卡片 / 表格 / 网格
    <footer>                      ← 可选
```

### 3.1 强制参数

| 元素 | 规范 | 说明 |
|------|------|------|
| `body` padding | **`2rem 1rem`**（默认） | 与发行、逾期等标准页一致 |
| `body` padding（工作台） | **`1.5rem 1rem`** | 如逾期跟进工作台、风险工作台 |
| 手机 `body` 顶边 | **`≥ 1rem`** | 允许纵向滚动，不强制单屏 |
| `.auth-topbar` | **`margin-bottom: 1rem`** | 见 `auth_html.USER_BAR_CSS` |
| 用户栏实现 | **`auth_html.inject_user_bar`** 或 `render_user_bar` + `USER_BAR_CSS` | **禁止** 把用户/退出塞进 `page-header` 右侧 |
| `.container` max-width | **1100px**（导入/发行）或 **1200px**（逾期/首页） | 新页默认 **1200px** |
| `.breadcrumb` | `font-size: 0.85–0.875rem`；**`margin-bottom: 1–1.5rem`** | 格式：`首页 / 模块 / 当前` |
| `header` / 页标题区 | **`margin-bottom: 1–2rem`**（Dashboard 品牌区 **1.25rem**） | |
| `h1` | Standard **1.5–1.75rem**；Dashboard **1.25–1.35rem** | 不得 **&lt; 1.25rem** |

### 3.2 用户栏位置（FAQ）

**用户栏必须独立一行**，位于 `<body>` 下、`.container` 前（`inject_user_bar` 注入位置），右对齐显示「当前用户」与「退出」。

---

## 4. 间距阶梯（Spacing Scale）

全站建议使用下列 rem 档，避免随意魔法数：

| Token | 值 | 典型用途 |
|-------|-----|----------|
| `space-xs` | 0.35rem | chip 内图标间距 |
| `space-sm` | 0.5rem | 表单项间隙、紧凑节距 |
| `space-md` | 0.75rem | 卡片内小节、Dashboard 节间距 |
| `space-lg` | 1rem | 标准卡片 padding、节间距 |
| `space-xl` | 1.25rem | Dashboard 标题下、header 下 |
| `space-2xl` | 1.5rem | 面包屑下、大区块 |
| `space-3xl` | 2rem | **body 顶边**（Chrome） |

Dashboard **仅**可在 KPI 条以下使用 `space-sm`–`space-md`；**不得**用 `space-xs` 级间距替代 Chrome 的 `space-3xl` 顶边。

---

## 5. 字号阶梯（Type Scale）

| 元素 | Standard | Dashboard |
|------|----------|-----------|
| `h1` | 1.5–1.75rem | 1.25–1.35rem |
| `h2` / 区块标题 | 0.95–1.05rem | 0.88rem 可接受 |
| 正文 / 表格 | 0.85–0.9rem | 同左 |
| KPI 数字 | 1.35–1.75rem | 顶栏 **1.25rem**；金额 **1.05rem**（8 列窄格 **0.95rem**）；风险卡 **1.35rem** |
| 标签 / 脚注 / muted | 0.75–0.8rem | 顶栏 / 风险卡标签 **0.75rem**；mini-kpi **0.8rem** |

---

## 6. 色板与语义色

首页与标准页应使用 **统一背景与语义色**（长期收敛目标）：

| 用途 | 推荐值 |
|------|--------|
| 页面背景 | `linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%)` |
| 标题文字 | `#f8fafc` |
| 正文 | `#e2e8f0` |
| 次要 / muted | `#94a3b8` |
| 弱化 | `#64748b` |
| 链接 / 强调 | `#38bdf8` |
| 成功 | `#34d399` |
| 警告 | `#fbbf24` / `#fb923c` |
| 危险 / 逾期 | `#f87171` |
| 卡片背景 | `rgba(255, 255, 255, 0.04–0.06)` |
| 卡片边框 | `1px solid rgba(255, 255, 255, 0.08–0.1)` |
| 圆角 | `10–12px` |
| 主按钮 | 背景 `#0ea5e9`，边框同色 |

---

## 7. 组件模式

### Card

- 用途：表单区、信息块、列表面板。
- Standard：`padding: 1–1.25rem`；`margin-bottom: 1rem`。

### KPI

- 用途：概览数字（逾期、风险、首页顶栏等）。
- 结构：label（小字）+ value（大字）。
- 无数据：**「—」**，不用大块空容器。

### Op-chip

- 用途：**Dashboard** 导航入口（发行导入、监控查看等）。
- 描边小按钮样式；**不**替代 Standard 页的主操作按钮。

### Button

- 主操作：`#0ea5e9` 实心（见 `issuance_html._page_shell`）。
- 次要：`secondary` 透明描边。
- 刷新/工具：小尺寸描边按钮，可放在 `page-header` 右侧。

### Table

- **表格页必须引用** [`backend/app/ui_css.py`](../../backend/app/ui_css.py) 中的 **`TABLE_SCROLL_CSS`**。
- 横向滚动、`white-space: nowrap`；数字列右对齐。

### Breadcrumb

- **子页必须有**；首页除外。
- 示例：`<nav class="breadcrumb"><a href="/">首页</a> / 逾期管理</nav>`

---

## 8. 响应式断点

| 断点 | 行为 |
|------|------|
| `≥ 1100px` | Dashboard：KPI 8 列横排；ops 双列 |
| `≤ 960px` | ops 双列 → 单列；KPI 2–4 列；风险卡 2 列 |
| `≤ 560px` | 风险卡单列；`body` 顶边 **≥ 1rem** |
| 全局 | **禁止** `body { overflow: hidden }`，避免小窗口裁切 |

---

## 9. 空态与数据展示

| 场景 | 规范 |
|------|------|
| 无数据 | 显示 **「—」** 或 **一行 muted 文案** |
| 禁止 | **`min-height: 180px`** 等等大块「暂无数据」占位（尤其 Dashboard） |
| 金额 | 使用 `fmt_money` |
| 计数 | 整数，可加「户 / 条」等单位 |
| KPI 口径 | 复用既有函数（如 `fetch_overdue_overview`），不在 UI 层另造语义 |

---

## 10. 禁止项（Anti-patterns）

1. **用户栏并入 `page-header`**（与品牌、刷新挤同一行）。
2. **桌面 `body` 顶边 &lt; 1rem** 换取单屏。
3. **大块空指标占位**（如 180px 空态框）。
4. **新页复制整套漂移 CSS** 而不对齐 Chrome 五参数（body padding、auth-topbar、container、h1、breadcrumb）。
5. **`body { overflow: hidden }`**。
6. **表格页不引用 `TABLE_SCROLL_CSS`**。
7. **子页省略 breadcrumb**（首页除外）。
8. **多个页面使用互不相关的背景 gradient** 且无文档说明。

---

## 11. 新页 / 改页检查清单

```
□ 已阅读本文与 ui_layout.mdc
□ body padding：2rem 1rem（工作台 1.5rem 1rem）；手机顶边 ≥ 1rem
□ auth-topbar 独立一行，margin-bottom 1rem
□ 子页含 breadcrumb（首页除外）
□ h1 在 Type Scale 内
□ container max-width 1100–1200px
□ 表格页已引用 TABLE_SCROLL_CSS
□ 空态为「—」或单行 muted，无大块占位
□ Dashboard 模式仅用于 GET /
□ 未使用 body overflow: hidden
□ KPI 口径与业务函数一致
```

---

## 12. 与现有代码的映射

| 文件 | 角色 | 模式 |
|------|------|------|
| [`auth_html.py`](../../backend/app/auth_html.py) | 用户栏、`USER_BAR_CSS` | Chrome 标准件 |
| [`ui_css.py`](../../backend/app/ui_css.py) | `TABLE_SCROLL_CSS` | 表格标准件 |
| [`issuance_html.py`](../../backend/app/issuance_html.py) | `_page_shell` | **Standard** 参考 |
| [`assetinfo_html.py`](../../backend/app/assetinfo_html.py) | `_page_shell` | **Standard** 参考 |
| [`main.py`](../../backend/app/main.py) | `/overdue`、`/risk`、资产包、`GET /` | Standard + **Dashboard** |
| [`html/render.py`](../../backend/app/html/render.py) | 逾期跟进工作台 | Standard（工作台顶边 1.5rem） |

---

## 13. 后续技术债

| 项 | 说明 | 优先级 |
|----|------|--------|
| `PAGE_CHROME_CSS` | 抽到 `ui_css.py`，单源维护 body/auth-topbar/container | P1 |
| `DASHBOARD_DENSITY_CSS` | Dashboard 内容区紧凑样式常量 | P1 |
| 统一背景 gradient | 首页与子页完全一致 | P2 |
| `_page_shell` 合并 | 发行/导入/主模块共用壳函数 | P2 |
| `docs/_templates/page_shell.md` | 新页脚手架模板 | P2 |

---

## 快速 FAQ

| 问题 | 答案 |
|------|------|
| 新建标准业务页 `body` padding？ | **`2rem 1rem`**（工作台 **`1.5rem 1rem`**） |
| 首页与子页哪里相同？ | **Chrome**：顶边、用户栏、背景、语义色 |
| 首页与子页哪里不同？ | 无 breadcrumb；h1 略小；**KPI 以下**可紧凑 |
| 用户栏放哪？ | **`<body>` 下独立一行**，`inject_user_bar` |
| 表格页必须引用什么？ | **`ui_css.TABLE_SCROLL_CSS`** |
| 禁止什么？ | 见 **§10** |

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | 初版：Standard / Dashboard、Chrome、组件与检查清单 |
