import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)

app = FastAPI(title="Real Estate Asset Management API")

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

    def fmt_money(value: float) -> str:
        return f"¥{value:,.2f}"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>房地产资产管理平台</title>
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
            <h1>房地产资产管理平台</h1>
            <p>数据概览 Dashboard</p>
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
        <footer>Real Estate Asset Management API</footer>
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

@app.get("/asset-pools/{asset_pool_id}/overview")
def get_asset_pool_overview(asset_pool_id: int):
    with engine.connect() as conn:
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
            raise HTTPException(status_code=404, detail="Asset pool not found")

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
