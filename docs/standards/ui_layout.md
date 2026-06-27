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
| **Dashboard** | **`GET /` 首页仅此一个** | **与 Standard 相同**（顶边略宽） | KPI 以下可 **紧凑**，桌面目标尽量一屏 |

### 相同点（Chrome）

- 背景 gradient、`.container` 宽度、`auth-topbar` 绝对定位（右上角）、语义色一致。
- 用户栏通过 `auth_html.inject_user_bar` 注入，样式见 `auth_html.USER_BAR_CSS`。

### 不同点（内容区）

| 项 | Standard | Dashboard |
|----|----------|-----------|
| 面包屑 | **必须有** | **无** |
| `body` 顶边 | **`0.4rem 1rem 2rem`**（`PAGE_CHROME_CSS`） | **`2rem 1rem 0.75rem`**（`DASHBOARD_BODY_CSS` 覆盖） |
| `h1` 字号 | **1.5rem**（`STANDARD_HEADER_CSS`） | 品牌区 **1.3rem** |
| 区块间距 | `1–1.25rem` | KPI 以下可用 `0.6–0.75rem` |
| KPI / 导航 | 按页而定 | 顶栏 KPI 条 + 双列 ops + 3 风险卡 |
| 空态 | 单行或简短说明 | **禁止** 大块空指标占位 |

**Dashboard 可以压缩 KPI 以下内容区，但不能压缩 Chrome 语义（容器宽度、用户栏位置）。**

---

## 3. 页面骨架（Chrome）

推荐 DOM 结构：

```text
<body class="…">                 ← 外边距见 §4；position: relative
  <div class="auth-topbar">      ← inject_user_bar；绝对定位右上角
  <div class="container">        ← max-width 1400px
    <nav class="breadcrumb">     ← 子页必有；首页省略
    <header class="page-header"> ← 品牌或页标题
    <main>                         ← 卡片 / 表格 / 网格
    <footer>                       ← 可选
```

### 3.1 强制参数

| 元素 | 规范 | 说明 |
|------|------|------|
| `body` padding（Standard） | **`0.4rem 1rem 2rem`** | `ui_css.PAGE_CHROME_CSS` |
| `body` padding（Dashboard） | **`2rem 1rem 0.75rem`** | `ui_css.DASHBOARD_BODY_CSS` |
| `body` padding（工作台） | **`0.4rem 1rem 0`** | `ui_css.WORKBENCH_BODY_CSS` |
| 手机 `body` 顶边 | **`≥ 1rem`** | Dashboard 响应式覆盖 |
| `.auth-topbar` | **绝对定位** `top: 0.4rem; right: 1rem` | `auth_html.USER_BAR_CSS` |
| 用户栏实现 | **`auth_html.inject_user_bar`** | **禁止** 把用户/退出塞进 `page-header` |
| `.container` max-width | **1400px** | `PAGE_CHROME_CSS` |
| `.breadcrumb` | **`0.875rem`**；**`margin-bottom: 1.5rem`**；**`line-height: 2rem`** | |
| `h1`（Standard） | **1.5rem** | `STANDARD_HEADER_CSS` |
| `h1`（Dashboard 品牌） | **1.3rem** | `STANDARD_HEADER_CSS` |

### 3.2 CSS 单源（`ui_css.py`）

| 常量 | 用途 |
|------|------|
| `PAGE_CHROME_CSS` | body / container / breadcrumb / 链接 |
| `DASHBOARD_BODY_CSS` | 首页 body 顶边覆盖 |
| `WORKBENCH_BODY_CSS` | 逾期跟进工作台底边 |
| `STANDARD_HEADER_CSS` | 标准 h1 |
| `BTN_CSS` | `.btn-primary` / `.btn-secondary` / `.tab-btn` / `.btn-recalc` |
| `FORM_FIELD_CSS` | 表单 input / select（不含 button） |
| `TABLE_SCROLL_CSS` | 表格横向滚动 |

新页 **必须引用** 上述常量，禁止复制漂移 Chrome。

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
| `space-3xl` | 2rem | **Dashboard body 顶边** |

Standard 子页顶边为 **0.4rem**（与用户栏同行视觉对齐），不是 2rem。

---

## 5. 字号阶梯（Type Scale）

| 元素 | Standard | Dashboard |
|------|----------|-----------|
| `h1` | **1.5rem** | **1.3rem**（品牌） |
| `h2` / 区块标题 | 0.95–1.05rem | 0.88rem 可接受 |
| 正文 / 表格 | 0.85–0.9rem | 同左 |
| KPI 数字 | 1.35–1.75rem | 顶栏 **1.25rem**；金额 **1.05rem** |
| 标签 / 脚注 / muted | 0.75–0.8rem | 顶栏 / 风险卡标签 **0.75rem** |

---

## 6. 色板与语义色

| 用途 | 推荐值 |
|------|--------|
| 页面背景 | `linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%)` |
| 标题文字 | `#f8fafc` |
| 正文 | `#e2e8f0` |
| 次要 / muted | `#94a3b8` |
| 链接 / 强调 | `#38bdf8` |
| 主按钮 | `.btn-primary` → `#0ea5e9` |

---

## 7. 组件模式

### Button

- 主操作：**`.btn-primary`**（`BTN_CSS`）
- 次要：**`.btn-secondary`**
- Tab / 胶囊：**`.tab-btn`**
- 工具：**`.btn-recalc`** / **`.btn-outline`**
- **禁止** `.container button { … }` 全局选择器（会污染 auth-topbar）

### Table

- **表格页必须引用** `TABLE_SCROLL_CSS`

### Breadcrumb

- **子页必须有**；首页除外
- 示例：`<nav class="breadcrumb"><a href="/">首页</a> / 逾期管理</nav>`

---

## 8. 禁止项（Anti-patterns）

1. **用户栏并入 `page-header`**
2. **新页复制整套漂移 CSS** 而不引用 `ui_css.py`
3. **`.container button` 全局样式**
4. **`body { overflow: hidden }`**
5. **表格页不引用 `TABLE_SCROLL_CSS`**
6. **子页省略 breadcrumb**（首页除外）

---

## 9. 新页 / 改页检查清单

```
□ 已阅读本文与 ui_layout.mdc
□ 已引用 PAGE_CHROME_CSS（+ Dashboard/Workbench 覆盖若适用）
□ auth-topbar 由 inject_user_bar 注入；USER_BAR_CSS 绝对定位
□ 子页含 breadcrumb（首页除外）
□ h1 使用 STANDARD_HEADER_CSS
□ container max-width 1400px
□ 按钮使用 btn-primary / btn-secondary 等语义类
□ 表格页已引用 TABLE_SCROLL_CSS
```

---

## 10. 与现有代码的映射

| 文件 | 角色 |
|------|------|
| [`ui_css.py`](../../backend/app/ui_css.py) | Chrome / 按钮 / 表格单源 |
| [`auth_html.py`](../../backend/app/auth_html.py) | 用户栏、`USER_BAR_CSS`、`inject_user_bar` |
| [`assetinfo_html.py`](../../backend/app/assetinfo_html.py) / [`issuance_html.py`](../../backend/app/issuance_html.py) | `_page_shell` → Standard |
| [`main.py`](../../backend/app/main.py) | Dashboard + overdue / risk / 资产包 |
| [`html/render.py`](../../backend/app/html/render.py) | 逾期跟进工作台 |

---

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06 | 初版：Standard / Dashboard、Chrome、组件与检查清单 |
| 2026-06-28 | 1400px 容器；子页顶边 0.4rem；auth-topbar 绝对定位；`PAGE_CHROME_CSS` / `BTN_CSS` 单源 |
