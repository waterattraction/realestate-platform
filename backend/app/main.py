import os
from html import escape
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)

app = FastAPI(title="Real Estate Securitization Platform")

STATUS_LABELS = {
    "pending": "待激活",
    "active": "生效中",
    "draft": "草稿",
    "in_progress": "进行中",
    "completed": "已完成",
    "raising": "募集中",
    "confirmed": "已确认",
}


def fmt_money(value: float) -> str:
    return f"¥{value:,.2f}"


def fmt_rate(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.2f}%"


def fmt_status(status: str) -> str:
    label = STATUS_LABELS.get(status, status)
    return f'<span class="badge">{escape(label)}</span>'


def fetch_asset_pool_overview(conn, asset_pool_id: int):
    pool_row = conn.execute(
        text("""
            SELECT
                id,
                code,
                name,
                status,
                appraised_value
            FROM asset_pools
            WHERE id = :asset_pool_id
        """),
        {"asset_pool_id": asset_pool_id},
    ).fetchone()

    if pool_row is None:
        return None

    project_rows = conn.execute(
        text("""
            SELECT
                p.id,
                p.code,
                p.name,
                p.city,
                p.status,
                p.total_budget,
                p.planned_start_date,
                p.planned_end_date
            FROM projects p
            INNER JOIN project_asset_pools pap ON pap.project_id = p.id
            WHERE pap.asset_pool_id = :asset_pool_id
            ORDER BY p.id
        """),
        {"asset_pool_id": asset_pool_id},
    )

    projects = []
    total_project_budget = 0.0
    for row in project_rows:
        budget = float(row.total_budget)
        total_project_budget += budget
        projects.append({
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "city": row.city,
            "status": row.status,
            "total_budget": budget,
            "planned_start_date": str(row.planned_start_date) if row.planned_start_date else None,
            "planned_end_date": str(row.planned_end_date) if row.planned_end_date else None,
        })

    trust_product_rows = conn.execute(
        text("""
            SELECT
                id,
                code,
                name,
                status,
                target_amount,
                raised_amount,
                expected_return_rate,
                open_date,
                close_date
            FROM trust_products
            WHERE asset_pool_id = :asset_pool_id
            ORDER BY id
        """),
        {"asset_pool_id": asset_pool_id},
    )

    trust_products = []
    trust_product_ids = []
    total_raised_amount = 0.0
    for row in trust_product_rows:
        raised = float(row.raised_amount)
        total_raised_amount += raised
        trust_product_ids.append(row.id)
        trust_products.append({
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "status": row.status,
            "target_amount": float(row.target_amount),
            "raised_amount": raised,
            "expected_return_rate": float(row.expected_return_rate) if row.expected_return_rate else None,
            "open_date": str(row.open_date) if row.open_date else None,
            "close_date": str(row.close_date) if row.close_date else None,
            "investments": [],
        })

    if trust_product_ids:
        investment_rows = conn.execute(
            text("""
                SELECT
                    i.id,
                    i.investor_id,
                    i.trust_product_id,
                    i.subscription_no,
                    i.amount,
                    i.status,
                    i.invested_at
                FROM investments i
                INNER JOIN trust_products tp ON tp.id = i.trust_product_id
                WHERE tp.asset_pool_id = :asset_pool_id
                ORDER BY i.trust_product_id, i.id
            """),
            {"asset_pool_id": asset_pool_id},
        )

        investments_by_product = {tp_id: [] for tp_id in trust_product_ids}
        for row in investment_rows:
            investments_by_product[row.trust_product_id].append({
                "id": row.id,
                "investor_id": row.investor_id,
                "trust_product_id": row.trust_product_id,
                "subscription_no": row.subscription_no,
                "amount": float(row.amount),
                "status": row.status,
                "invested_at": str(row.invested_at) if row.invested_at else None,
            })

        for tp in trust_products:
            tp["investments"] = investments_by_product[tp["id"]]

    return {
        "asset_pool": {
            "id": pool_row.id,
            "code": pool_row.code,
            "name": pool_row.name,
            "status": pool_row.status,
            "appraised_value": float(pool_row.appraised_value),
        },
        "projects": projects,
        "trust_products": trust_products,
        "total_raised_amount": total_raised_amount,
        "total_project_budget": total_project_budget,
    }


def fetch_investor_map(conn):
    result = conn.execute(text("SELECT id, code, name FROM investors ORDER BY id"))
    return {
        row.id: {"code": row.code, "name": row.name}
        for row in result
    }


def render_asset_pool_detail_html(data, investor_map):
    pool = data["asset_pool"]
    projects = data["projects"]
    trust_products = data["trust_products"]

    project_rows = ""
    if projects:
        for project in projects:
            project_rows += f"""
                <tr>
                    <td>{escape(project["code"])}</td>
                    <td>{escape(project["name"])}</td>
                    <td>{escape(project["city"] or "—")}</td>
                    <td>{fmt_status(project["status"])}</td>
                    <td class="num">{fmt_money(project["total_budget"])}</td>
                    <td>{escape(project["planned_start_date"] or "—")}</td>
                    <td>{escape(project["planned_end_date"] or "—")}</td>
                </tr>
            """
    else:
        project_rows = '<tr><td colspan="7" class="empty">暂无关联项目</td></tr>'

    trust_product_cards = ""
    if trust_products:
        for tp in trust_products:
            progress = min(tp["raised_amount"] / tp["target_amount"] * 100, 100) if tp["target_amount"] > 0 else 0
            trust_product_cards += f"""
                <div class="card sub-card">
                    <div class="sub-card-header">
                        <div>
                            <div class="sub-card-code">{escape(tp["code"])}</div>
                            <div class="sub-card-title">{escape(tp["name"])}</div>
                        </div>
                        {fmt_status(tp["status"])}
                    </div>
                    <div class="meta-grid">
                        <div><span class="meta-label">目标募集</span><span class="meta-value">{fmt_money(tp["target_amount"])}</span></div>
                        <div><span class="meta-label">已募集</span><span class="meta-value money">{fmt_money(tp["raised_amount"])}</span></div>
                        <div><span class="meta-label">预期收益率</span><span class="meta-value">{fmt_rate(tp["expected_return_rate"])}</span></div>
                        <div><span class="meta-label">开放日</span><span class="meta-value">{escape(tp["open_date"] or "—")}</span></div>
                        <div><span class="meta-label">关闭日</span><span class="meta-value">{escape(tp["close_date"] or "—")}</span></div>
                    </div>
                    <div class="progress-wrap">
                        <div class="progress-label">
                            <span>募集进度</span>
                            <span>{progress:.1f}%</span>
                        </div>
                        <div class="progress-bar"><div class="progress-fill" style="width: {progress:.1f}%"></div></div>
                    </div>
                </div>
            """
    else:
        trust_product_cards = '<div class="empty-block">尚未发行信托产品</div>'

    investment_rows = ""
    all_investments = []
    for tp in trust_products:
        for investment in tp["investments"]:
            all_investments.append((tp, investment))

    if all_investments:
        for tp, investment in all_investments:
            investor = investor_map.get(investment["investor_id"], {})
            investor_label = investor.get("name") or f'ID {investment["investor_id"]}'
            investor_code = investor.get("code", "—")
            investment_rows += f"""
                <tr>
                    <td>{escape(tp["code"])}</td>
                    <td>{escape(investment["subscription_no"])}</td>
                    <td>{escape(investor_label)}<span class="muted"> ({escape(investor_code)})</span></td>
                    <td class="num">{fmt_money(investment["amount"])}</td>
                    <td>{fmt_status(investment["status"])}</td>
                    <td>{escape(investment["invested_at"] or "—")}</td>
                </tr>
            """
    else:
        investment_rows = '<tr><td colspan="6" class="empty">暂无认购记录</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape(pool["name"])} · 资产包详情</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
            min-height: 100vh;
            color: #e2e8f0;
            padding: 2rem 1rem;
        }}
        a {{
            color: #38bdf8;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        .container {{
            max-width: 960px;
            margin: 0 auto;
        }}
        .breadcrumb {{
            font-size: 0.875rem;
            color: #94a3b8;
            margin-bottom: 1.5rem;
        }}
        header {{
            margin-bottom: 2rem;
        }}
        header h1 {{
            font-size: 1.75rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            color: #f8fafc;
            margin-top: 0.5rem;
        }}
        header p {{
            margin-top: 0.5rem;
            font-size: 0.95rem;
            color: #94a3b8;
        }}
        .hero {{
            display: flex;
            flex-wrap: wrap;
            gap: 1.5rem;
            align-items: flex-start;
            justify-content: space-between;
        }}
        .hero-main {{
            flex: 1;
            min-width: 220px;
        }}
        .hero-code {{
            font-size: 0.875rem;
            color: #94a3b8;
            margin-bottom: 0.5rem;
        }}
        .hero-value {{
            font-size: 2rem;
            font-weight: 700;
            color: #38bdf8;
            margin-top: 0.75rem;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.25rem;
        }}
        .card {{
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 1.5rem;
            backdrop-filter: blur(8px);
        }}
        .card-label {{
            font-size: 0.875rem;
            color: #94a3b8;
            margin-bottom: 0.75rem;
        }}
        .card-value {{
            font-size: 1.75rem;
            font-weight: 700;
            color: #f8fafc;
            line-height: 1.2;
        }}
        .card-value.money {{
            color: #38bdf8;
        }}
        .card-value.budget {{
            color: #34d399;
        }}
        .section {{
            margin-top: 2rem;
        }}
        .section-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: #f8fafc;
            margin-bottom: 1rem;
        }}
        .table-wrap {{
            overflow-x: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        th, td {{
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }}
        th {{
            color: #94a3b8;
            font-weight: 500;
            font-size: 0.8rem;
        }}
        td.num {{
            color: #38bdf8;
            font-weight: 600;
            white-space: nowrap;
        }}
        .badge {{
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 999px;
            font-size: 0.75rem;
            background: rgba(56, 189, 248, 0.15);
            color: #7dd3fc;
            border: 1px solid rgba(56, 189, 248, 0.25);
        }}
        .sub-card {{
            margin-bottom: 1rem;
        }}
        .sub-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            margin-bottom: 1rem;
        }}
        .sub-card-code {{
            font-size: 0.8rem;
            color: #94a3b8;
            margin-bottom: 0.25rem;
        }}
        .sub-card-title {{
            font-size: 1rem;
            font-weight: 600;
            color: #f8fafc;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 0.75rem;
            margin-bottom: 1rem;
        }}
        .meta-label {{
            display: block;
            font-size: 0.75rem;
            color: #94a3b8;
            margin-bottom: 0.25rem;
        }}
        .meta-value {{
            font-size: 0.95rem;
            color: #f8fafc;
        }}
        .meta-value.money {{
            color: #38bdf8;
        }}
        .progress-wrap {{
            margin-top: 0.5rem;
        }}
        .progress-label {{
            display: flex;
            justify-content: space-between;
            font-size: 0.8rem;
            color: #94a3b8;
            margin-bottom: 0.4rem;
        }}
        .progress-bar {{
            height: 8px;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 999px;
            overflow: hidden;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #38bdf8, #34d399);
            border-radius: 999px;
        }}
        .empty, .empty-block {{
            color: #64748b;
            text-align: center;
        }}
        .empty-block {{
            padding: 2rem 1rem;
            background: rgba(255, 255, 255, 0.04);
            border: 1px dashed rgba(255, 255, 255, 0.1);
            border-radius: 12px;
        }}
        .muted {{
            color: #64748b;
            font-size: 0.85rem;
        }}
        footer {{
            margin-top: 2.5rem;
            text-align: center;
            font-size: 0.8rem;
            color: #64748b;
        }}
    </style>
</head>
<body>
    <div class="container">
        <nav class="breadcrumb">
            <a href="/">首页</a> / 资产包 / {escape(pool["code"])}
        </nav>

        <header>
            <div class="card hero">
                <div class="hero-main">
                    <div class="hero-code">{escape(pool["code"])} · {fmt_status(pool["status"])}</div>
                    <h1>{escape(pool["name"])}</h1>
                    <p>资产包详情 · Real Estate Securitization Platform</p>
                    <div class="hero-value">{fmt_money(pool["appraised_value"])}</div>
                    <div class="card-label" style="margin-top: 0.5rem;">评估价值</div>
                </div>
            </div>
        </header>

        <div class="grid">
            <div class="card">
                <div class="card-label">关联项目数</div>
                <div class="card-value">{len(projects)}</div>
            </div>
            <div class="card">
                <div class="card-label">项目总预算</div>
                <div class="card-value money budget">{fmt_money(data["total_project_budget"])}</div>
            </div>
            <div class="card">
                <div class="card-label">信托产品数</div>
                <div class="card-value">{len(trust_products)}</div>
            </div>
            <div class="card">
                <div class="card-label">已募集总金额</div>
                <div class="card-value money">{fmt_money(data["total_raised_amount"])}</div>
            </div>
        </div>

        <section class="section">
            <h2 class="section-title">关联项目</h2>
            <div class="card table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>项目编号</th>
                            <th>项目名称</th>
                            <th>城市</th>
                            <th>状态</th>
                            <th>预算</th>
                            <th>计划开工</th>
                            <th>计划完工</th>
                        </tr>
                    </thead>
                    <tbody>{project_rows}</tbody>
                </table>
            </div>
        </section>

        <section class="section">
            <h2 class="section-title">信托产品</h2>
            {trust_product_cards}
        </section>

        <section class="section">
            <h2 class="section-title">投资明细</h2>
            <div class="card table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>信托产品</th>
                            <th>认购编号</th>
                            <th>投资人</th>
                            <th>认购金额</th>
                            <th>状态</th>
                            <th>认购时间</th>
                        </tr>
                    </thead>
                    <tbody>{investment_rows}</tbody>
                </table>
            </div>
        </section>

        <footer>Real Estate Securitization Platform</footer>
    </div>
</body>
</html>"""


def render_not_found_html():
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>资产包不存在</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
            min-height: 100vh;
            color: #e2e8f0;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 2rem;
        }
        .box {
            text-align: center;
            max-width: 420px;
        }
        h1 { font-size: 1.5rem; margin-bottom: 0.75rem; color: #f8fafc; }
        p { color: #94a3b8; margin-bottom: 1.5rem; }
        a { color: #38bdf8; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="box">
        <h1>资产包不存在</h1>
        <p>请检查 URL 中的资产包 ID 是否正确。</p>
        <a href="/">返回首页</a>
    </div>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
def dashboard():
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM projects) AS project_count,
                (SELECT COUNT(*) FROM asset_pools) AS asset_pool_count,
                (SELECT COUNT(*) FROM trust_products) AS trust_product_count,
                (SELECT COUNT(*) FROM investors) AS investor_count,
                (SELECT COALESCE(SUM(raised_amount), 0) FROM trust_products) AS total_raised_amount,
                (SELECT COALESCE(SUM(total_budget), 0) FROM projects) AS total_project_budget
        """)).fetchone()

    project_count = int(row.project_count)
    asset_pool_count = int(row.asset_pool_count)
    trust_product_count = int(row.trust_product_count)
    investor_count = int(row.investor_count)
    total_raised_amount = float(row.total_raised_amount)
    total_project_budget = float(row.total_project_budget)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>房地产资产证券化平台</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
            min-height: 100vh;
            color: #e2e8f0;
            padding: 2rem 1rem;
        }}
        .container {{
            max-width: 960px;
            margin: 0 auto;
        }}
        header {{
            margin-bottom: 2.5rem;
            text-align: center;
        }}
        header h1 {{
            font-size: 1.75rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            color: #f8fafc;
        }}
        header p {{
            margin-top: 0.5rem;
            font-size: 0.95rem;
            color: #94a3b8;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 1.25rem;
        }}
        .card {{
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 1.5rem;
            backdrop-filter: blur(8px);
            transition: transform 0.2s, border-color 0.2s;
        }}
        .card:hover {{
            transform: translateY(-2px);
            border-color: rgba(56, 189, 248, 0.4);
        }}
        .card-label {{
            font-size: 0.875rem;
            color: #94a3b8;
            margin-bottom: 0.75rem;
        }}
        .card-value {{
            font-size: 2rem;
            font-weight: 700;
            color: #f8fafc;
            line-height: 1.2;
        }}
        .card-value.money {{
            color: #38bdf8;
            font-size: 1.75rem;
        }}
        .card-value.budget {{
            color: #34d399;
        }}
        footer {{
            margin-top: 2.5rem;
            text-align: center;
            font-size: 0.8rem;
            color: #64748b;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>房地产资产证券化平台</h1>
            <p>数据概览 · Real Estate Securitization Platform</p>
        </header>
        <div class="grid">
            <div class="card">
                <div class="card-label">项目数量</div>
                <div class="card-value">{project_count}</div>
            </div>
            <div class="card">
                <div class="card-label">资产包数量</div>
                <div class="card-value">{asset_pool_count}</div>
            </div>
            <div class="card">
                <div class="card-label">信托产品数量</div>
                <div class="card-value">{trust_product_count}</div>
            </div>
            <div class="card">
                <div class="card-label">投资人数量</div>
                <div class="card-value">{investor_count}</div>
            </div>
            <div class="card">
                <div class="card-label">已募集总金额</div>
                <div class="card-value money">{fmt_money(total_raised_amount)}</div>
            </div>
            <div class="card">
                <div class="card-label">项目总预算</div>
                <div class="card-value money budget">{fmt_money(total_project_budget)}</div>
            </div>
        </div>
        <footer>Real Estate Securitization Platform</footer>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html)

@app.get("/projects")
def list_projects():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                id,
                code,
                name,
                city,
                status,
                total_budget,
                planned_start_date,
                planned_end_date
            FROM projects
            ORDER BY id
        """))

        projects = []
        for row in result:
            projects.append({
                "id": row.id,
                "code": row.code,
                "name": row.name,
                "city": row.city,
                "status": row.status,
                "total_budget": float(row.total_budget),
                "planned_start_date": str(row.planned_start_date) if row.planned_start_date else None,
                "planned_end_date": str(row.planned_end_date) if row.planned_end_date else None,
            })

        return projects

@app.get("/asset-pools")
def list_asset_pools():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                id,
                code,
                name,
                status,
                appraised_value
            FROM asset_pools
            ORDER BY id
        """))

        asset_pools = []
        for row in result:
            asset_pools.append({
                "id": row.id,
                "code": row.code,
                "name": row.name,
                "status": row.status,
                "appraised_value": float(row.appraised_value),
            })

        return asset_pools

@app.get("/asset-pools/{asset_pool_id}", response_class=HTMLResponse)
def asset_pool_detail(asset_pool_id: int):
    with engine.connect() as conn:
        data = fetch_asset_pool_overview(conn, asset_pool_id)
        if data is None:
            return HTMLResponse(content=render_not_found_html(), status_code=404)
        investor_map = fetch_investor_map(conn)
        html = render_asset_pool_detail_html(data, investor_map)

    return HTMLResponse(content=html)

@app.get("/asset-pools/{asset_pool_id}/overview")
def get_asset_pool_overview(asset_pool_id: int):
    with engine.connect() as conn:
        data = fetch_asset_pool_overview(conn, asset_pool_id)

    if data is None:
        raise HTTPException(status_code=404, detail="Asset pool not found")

    return data

@app.get("/trust-products")
def list_trust_products():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                id,
                asset_pool_id,
                code,
                name,
                status,
                target_amount,
                raised_amount,
                expected_return_rate,
                open_date,
                close_date
            FROM trust_products
            ORDER BY id
        """))

        trust_products = []
        for row in result:
            trust_products.append({
                "id": row.id,
                "asset_pool_id": row.asset_pool_id,
                "code": row.code,
                "name": row.name,
                "status": row.status,
                "target_amount": float(row.target_amount),
                "raised_amount": float(row.raised_amount),
                "expected_return_rate": float(row.expected_return_rate) if row.expected_return_rate else None,
                "open_date": str(row.open_date) if row.open_date else None,
                "close_date": str(row.close_date) if row.close_date else None,
            })

        return trust_products

@app.get("/investors")
def list_investors():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                id,
                code,
                name,
                investor_type,
                kyc_status,
                phone,
                email
            FROM investors
            ORDER BY id
        """))

        investors = []
        for row in result:
            investors.append({
                "id": row.id,
                "code": row.code,
                "name": row.name,
                "investor_type": row.investor_type,
                "kyc_status": row.kyc_status,
                "phone": row.phone,
                "email": row.email,
            })

        return investors

@app.get("/investments")
def list_investments():
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
                id,
                investor_id,
                trust_product_id,
                subscription_no,
                amount,
                status,
                invested_at
            FROM investments
            ORDER BY id
        """))

        investments = []
        for row in result:
            investments.append({
                "id": row.id,
                "investor_id": row.investor_id,
                "trust_product_id": row.trust_product_id,
                "subscription_no": row.subscription_no,
                "amount": float(row.amount),
                "status": row.status,
                "invested_at": str(row.invested_at) if row.invested_at else None,
            })

        return investments
