import os
import uuid
from html import escape
from typing import Annotated
from urllib.parse import quote

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import create_engine, text

from app import auth
from app import auth_html
from app import ingestion_html
from app import ingestion_pipeline
from app import ingestion_upload
from app import risk_hub

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)

app = FastAPI(title="Real Estate Securitization Platform")

get_current_user = auth.make_current_user_dependency(engine)
get_page_user = auth.make_page_user_dependency(engine)


def _safe_next_path(next_url: str) -> str:
    if not next_url or not next_url.startswith("/") or next_url.startswith("//"):
        return "/"
    return next_url


@app.exception_handler(auth.LoginRedirect)
async def handle_login_redirect(_request: Request, exc: auth.LoginRedirect):
    return RedirectResponse(url=f"/login?next={quote(exc.next_path)}", status_code=302)


@app.on_event("startup")
def on_startup():
    auth.init_auth(engine)

STATUS_LABELS = {
    "pending": "待激活",
    "active": "生效中",
    "draft": "草稿",
    "in_progress": "进行中",
    "completed": "已完成",
    "raising": "募集中",
    "confirmed": "已确认",
}

FOLLOWUP_STATUS_LABELS = {
    "open": "待处理",
    "in_progress": "跟进中",
    "resolved": "已解决",
    "closed": "已关闭",
}

TRIGGER_SOURCE_LABELS = {
    "system": "系统自检",
    "trust": "信托要求",
}

DELINQUENCY_BUCKET_LABELS = {
    "M1": "M1 (1-30天)",
    "M2": "M2 (31-60天)",
    "M3": "M3 (61-90天)",
    "M3_PLUS": "M3+ (90天以上)",
}

DELINQUENCY_BUCKET_COLORS = {
    "M1": "#34d399",
    "M2": "#fbbf24",
    "M3": "#fbbf24",
    "M3_PLUS": "#f87171",
}

RECONCILIATION_TOLERANCE = 0.01


def fmt_money(value: float) -> str:
    return f"¥{value:,.2f}"


def fmt_rate(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.2f}%"


def fmt_status(status: str) -> str:
    label = STATUS_LABELS.get(status, status)
    return f'<span class="badge">{escape(label)}</span>'


def delinquency_bucket(overdue_days: int) -> str | None:
    if overdue_days <= 0:
        return None
    if overdue_days <= 30:
        return "M1"
    if overdue_days <= 60:
        return "M2"
    if overdue_days <= 90:
        return "M3"
    return "M3_PLUS"


def fmt_delinquency_badge(bucket: str | None) -> str:
    if bucket is None:
        return '<span class="badge">正常</span>'
    label = DELINQUENCY_BUCKET_LABELS.get(bucket, bucket)
    color = DELINQUENCY_BUCKET_COLORS.get(bucket, "#94a3b8")
    return (
        f'<span class="badge" style="background: {color}22; color: {color}; '
        f'border-color: {color}55;">{escape(label)}</span>'
    )


def _latest_monitor_filter(trust_product_id: int | None, data_date: str | None) -> tuple[str, dict]:
    params: dict = {}
    if data_date:
        if trust_product_id is not None:
            return (
                "m.trust_product_id = :trust_product_id AND m.data_date = :data_date",
                {"trust_product_id": trust_product_id, "data_date": data_date},
            )
        return ("m.data_date = :data_date", {"data_date": data_date})

    if trust_product_id is not None:
        return (
            """
            m.trust_product_id = :trust_product_id
            AND m.data_date = (
                SELECT MAX(data_date)
                FROM trust_asset_monitor_records
                WHERE trust_product_id = :trust_product_id
            )
            """,
            {"trust_product_id": trust_product_id},
        )

    return (
        """
        m.data_date = (
            SELECT MAX(data_date) FROM trust_asset_monitor_records
        )
        """,
        {},
    )


def fetch_overdue_overview(conn, trust_product_id: int | None = None, data_date: str | None = None):
    monitor_filter, params = _latest_monitor_filter(trust_product_id, data_date)

    row = conn.execute(
        text(f"""
            SELECT
                m.data_date,
                COUNT(*) FILTER (WHERE m.overdue_days > 0) AS overdue_count,
                COUNT(*) FILTER (WHERE m.overdue_days BETWEEN 1 AND 30) AS m1_count,
                COUNT(*) FILTER (WHERE m.overdue_days BETWEEN 31 AND 60) AS m2_count,
                COUNT(*) FILTER (WHERE m.overdue_days BETWEEN 61 AND 90) AS m3_count,
                COUNT(*) FILTER (WHERE m.overdue_days > 90) AS m3_plus_count,
                COUNT(*) AS total_asset_count
            FROM trust_asset_monitor_records m
            WHERE {monitor_filter}
            GROUP BY m.data_date
        """),
        params,
    ).fetchone()

    if row is None:
        return {
            "data_date": data_date,
            "trust_product_id": trust_product_id,
            "overdue_count": 0,
            "m1_count": 0,
            "m2_count": 0,
            "m3_count": 0,
            "m3_plus_count": 0,
            "total_asset_count": 0,
            "reconciliation_failed_count": 0,
            "active_followup_count": 0,
            "top_overdue": [],
        }

    resolved_data_date = str(row.data_date)
    recon_params = dict(params)
    if "data_date" not in recon_params:
        recon_params["data_date"] = resolved_data_date

    recon_filter = monitor_filter
    if trust_product_id is not None and "data_date" not in params:
        recon_filter = "m.trust_product_id = :trust_product_id AND m.data_date = :data_date"
    elif trust_product_id is None and "data_date" not in params:
        recon_filter = "m.data_date = :data_date"

    recon_row = conn.execute(
        text(f"""
            WITH monitor AS (
                SELECT m.*
                FROM trust_asset_monitor_records m
                WHERE {recon_filter}
            ),
            repayment_sum AS (
                SELECT
                    r.trust_asset_id,
                    COALESCE(SUM(r.actual_repayment_amount), 0) AS total_repaid
                FROM trust_repayment_detail_records r
                WHERE r.data_date = :data_date
                  {"AND r.trust_product_id = :trust_product_id" if trust_product_id is not None else ""}
                GROUP BY r.trust_asset_id
            ),
            balance_fail AS (
                SELECT m.trust_asset_id
                FROM monitor m
                WHERE ABS((m.initial_transfer_amount - m.repaid_amount) - m.remaining_amount)
                      > :tolerance
            ),
            cross_fail AS (
                SELECT m.trust_asset_id
                FROM monitor m
                LEFT JOIN repayment_sum rs ON rs.trust_asset_id = m.trust_asset_id
                WHERE ABS(m.repaid_amount - COALESCE(rs.total_repaid, 0)) > :tolerance
            )
            SELECT COUNT(DISTINCT trust_asset_id) AS failed_count
            FROM (
                SELECT trust_asset_id FROM balance_fail
                UNION
                SELECT trust_asset_id FROM cross_fail
            ) failed
        """),
        {**recon_params, "tolerance": RECONCILIATION_TOLERANCE},
    ).fetchone()

    followup_sql = """
        SELECT COUNT(*) AS cnt
        FROM trust_overdue_followups
        WHERE status IN ('open', 'in_progress')
    """
    followup_params: dict = {}
    if trust_product_id is not None:
        followup_sql += " AND trust_product_id = :trust_product_id"
        followup_params["trust_product_id"] = trust_product_id

    followup_row = conn.execute(text(followup_sql), followup_params).fetchone()

    top_rows = conn.execute(
        text(f"""
            SELECT
                m.trust_asset_id,
                ta.asset_code,
                ta.asset_name,
                m.trust_product_id,
                tp.name AS trust_product_name,
                m.overdue_days,
                EXISTS (
                    SELECT 1 FROM trust_overdue_followups f
                    WHERE f.trust_asset_id = m.trust_asset_id
                      AND f.status IN ('open', 'in_progress')
                ) AS has_follow_up
            FROM trust_asset_monitor_records m
            INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
            INNER JOIN trust_products tp ON tp.id = m.trust_product_id
            WHERE {monitor_filter}
              AND m.overdue_days > 0
            ORDER BY m.overdue_days DESC
            LIMIT 5
        """),
        params,
    )

    top_overdue = []
    for r in top_rows:
        bucket = delinquency_bucket(int(r.overdue_days))
        top_overdue.append({
            "trust_asset_id": r.trust_asset_id,
            "asset_code": r.asset_code,
            "asset_name": r.asset_name,
            "trust_product_id": r.trust_product_id,
            "trust_product_name": r.trust_product_name,
            "overdue_days": int(r.overdue_days),
            "delinquency_bucket": bucket,
            "has_follow_up": bool(r.has_follow_up),
        })

    return {
        "data_date": resolved_data_date,
        "trust_product_id": trust_product_id,
        "overdue_count": int(row.overdue_count),
        "m1_count": int(row.m1_count),
        "m2_count": int(row.m2_count),
        "m3_count": int(row.m3_count),
        "m3_plus_count": int(row.m3_plus_count),
        "total_asset_count": int(row.total_asset_count),
        "reconciliation_failed_count": int(recon_row.failed_count) if recon_row else 0,
        "active_followup_count": int(followup_row.cnt) if followup_row else 0,
        "top_overdue": top_overdue,
    }


def fetch_overdue_checks(conn, trust_product_id: int | None = None, data_date: str | None = None):
    monitor_filter, params = _latest_monitor_filter(trust_product_id, data_date)

    rows = conn.execute(
        text(f"""
            SELECT
                m.trust_asset_id,
                ta.asset_code,
                ta.asset_name,
                m.trust_product_id,
                tp.name AS trust_product_name,
                m.data_date,
                m.overdue_days,
                m.last_payment_date,
                m.max_payment_date,
                m.repaid_amount,
                m.remaining_amount,
                EXISTS (
                    SELECT 1 FROM trust_overdue_followups f
                    WHERE f.trust_asset_id = m.trust_asset_id
                      AND f.status IN ('open', 'in_progress')
                ) AS has_follow_up
            FROM trust_asset_monitor_records m
            INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
            INNER JOIN trust_products tp ON tp.id = m.trust_product_id
            WHERE {monitor_filter}
              AND m.overdue_days > 0
            ORDER BY m.overdue_days DESC, ta.asset_code
        """),
        params,
    )

    items = []
    resolved_date = data_date
    for row in rows:
        if resolved_date is None:
            resolved_date = str(row.data_date)
        items.append({
            "trust_asset_id": row.trust_asset_id,
            "asset_code": row.asset_code,
            "asset_name": row.asset_name,
            "trust_product_id": row.trust_product_id,
            "trust_product_name": row.trust_product_name,
            "data_date": str(row.data_date),
            "overdue_days": int(row.overdue_days),
            "delinquency_bucket": delinquency_bucket(int(row.overdue_days)),
            "last_payment_date": str(row.last_payment_date) if row.last_payment_date else None,
            "max_payment_date": str(row.max_payment_date) if row.max_payment_date else None,
            "repaid_amount": float(row.repaid_amount),
            "remaining_amount": float(row.remaining_amount),
            "has_follow_up": bool(row.has_follow_up),
        })

    return {"data_date": resolved_date, "items": items}


def fetch_reconciliation(conn, trust_product_id: int | None = None, data_date: str | None = None):
    monitor_filter, params = _latest_monitor_filter(trust_product_id, data_date)

    row = conn.execute(
        text(f"""
            SELECT m.data_date
            FROM trust_asset_monitor_records m
            WHERE {monitor_filter}
            LIMIT 1
        """),
        params,
    ).fetchone()

    if row is None:
        return {"data_date": data_date, "items": []}

    resolved_data_date = str(row.data_date)
    query_params = dict(params)
    if "data_date" not in query_params:
        query_params["data_date"] = resolved_data_date
    query_params["tolerance"] = RECONCILIATION_TOLERANCE

    recon_filter = monitor_filter
    if "data_date" not in params:
        if trust_product_id is not None:
            recon_filter = "m.trust_product_id = :trust_product_id AND m.data_date = :data_date"
        else:
            recon_filter = "m.data_date = :data_date"

    rows = conn.execute(
        text(f"""
            WITH monitor AS (
                SELECT m.*
                FROM trust_asset_monitor_records m
                WHERE {recon_filter}
            ),
            repayment_sum AS (
                SELECT
                    r.trust_asset_id,
                    COALESCE(SUM(r.actual_repayment_amount), 0) AS total_repaid
                FROM trust_repayment_detail_records r
                WHERE r.data_date = :data_date
                  {"AND r.trust_product_id = :trust_product_id" if trust_product_id is not None else ""}
                GROUP BY r.trust_asset_id
            ),
            balance_check AS (
                SELECT
                    m.trust_asset_id,
                    m.asset_code,
                    m.trust_product_id,
                    m.data_date,
                    'balance_equation' AS check_type,
                    (m.initial_transfer_amount - m.repaid_amount) AS left_amount,
                    m.remaining_amount AS right_amount,
                    ((m.initial_transfer_amount - m.repaid_amount) - m.remaining_amount) AS diff_amount
                FROM monitor m
            ),
            cross_check AS (
                SELECT
                    m.trust_asset_id,
                    m.asset_code,
                    m.trust_product_id,
                    m.data_date,
                    'cross_sheet_repayment' AS check_type,
                    m.repaid_amount AS left_amount,
                    COALESCE(rs.total_repaid, 0) AS right_amount,
                    (m.repaid_amount - COALESCE(rs.total_repaid, 0)) AS diff_amount
                FROM monitor m
                LEFT JOIN repayment_sum rs ON rs.trust_asset_id = m.trust_asset_id
            ),
            all_checks AS (
                SELECT * FROM balance_check
                UNION ALL
                SELECT * FROM cross_check
            )
            SELECT
                ac.trust_asset_id,
                ac.asset_code,
                ta.asset_name,
                ac.trust_product_id,
                tp.name AS trust_product_name,
                ac.data_date,
                ac.check_type,
                ac.left_amount,
                ac.right_amount,
                ac.diff_amount
            FROM all_checks ac
            INNER JOIN trust_assets ta ON ta.id = ac.trust_asset_id
            INNER JOIN trust_products tp ON tp.id = ac.trust_product_id
            WHERE ABS(ac.diff_amount) > :tolerance
            ORDER BY ac.asset_code, ac.check_type
        """),
        query_params,
    )

    items = []
    for r in rows:
        items.append({
            "trust_asset_id": r.trust_asset_id,
            "asset_code": r.asset_code,
            "asset_name": r.asset_name,
            "trust_product_id": r.trust_product_id,
            "trust_product_name": r.trust_product_name,
            "data_date": str(r.data_date),
            "check_type": r.check_type,
            "left_amount": float(r.left_amount),
            "right_amount": float(r.right_amount),
            "diff_amount": float(r.diff_amount),
            "passed": False,
        })

    return {"data_date": resolved_data_date, "items": items}


def fetch_overdue_followups(conn, trust_product_id: int | None = None, status: str | None = None):
    sql = """
        SELECT
            f.id,
            f.trust_product_id,
            tp.name AS trust_product_name,
            f.trust_asset_id,
            ta.asset_code,
            ta.asset_name,
            f.data_date,
            f.trigger_source,
            f.overdue_reason,
            f.follow_up_plan,
            f.status,
            f.owner_name,
            f.last_follow_up_at,
            f.trust_feedback,
            f.created_at,
            f.updated_at
        FROM trust_overdue_followups f
        INNER JOIN trust_assets ta ON ta.id = f.trust_asset_id
        INNER JOIN trust_products tp ON tp.id = f.trust_product_id
        WHERE 1 = 1
    """
    params: dict = {}
    if trust_product_id is not None:
        sql += " AND f.trust_product_id = :trust_product_id"
        params["trust_product_id"] = trust_product_id
    if status is not None:
        sql += " AND f.status = :status"
        params["status"] = status
    sql += " ORDER BY f.last_follow_up_at DESC NULLS LAST, f.id DESC"

    rows = conn.execute(text(sql), params)
    items = []
    for row in rows:
        items.append({
            "id": row.id,
            "trust_product_id": row.trust_product_id,
            "trust_product_name": row.trust_product_name,
            "trust_asset_id": row.trust_asset_id,
            "asset_code": row.asset_code,
            "asset_name": row.asset_name,
            "data_date": str(row.data_date),
            "trigger_source": row.trigger_source,
            "overdue_reason": row.overdue_reason,
            "follow_up_plan": row.follow_up_plan,
            "status": row.status,
            "owner_name": row.owner_name,
            "last_follow_up_at": str(row.last_follow_up_at) if row.last_follow_up_at else None,
            "trust_feedback": row.trust_feedback,
            "created_at": str(row.created_at),
            "updated_at": str(row.updated_at),
        })

    return items


def _recon_checks_for_asset(
    initial: float, repaid: float, remaining: float, detail_total: float
) -> dict:
    balance_diff = (initial - repaid) - remaining
    cross_diff = repaid - detail_total
    return {
        "balance_equation": {
            "passed": abs(balance_diff) <= RECONCILIATION_TOLERANCE,
            "left_amount": initial - repaid,
            "right_amount": remaining,
            "diff_amount": balance_diff,
        },
        "cross_sheet_repayment": {
            "passed": abs(cross_diff) <= RECONCILIATION_TOLERANCE,
            "left_amount": repaid,
            "right_amount": detail_total,
            "diff_amount": cross_diff,
        },
    }


def fetch_overdue_workbench(
    conn,
    trust_product_id: int | None = None,
    trust_asset_id: int | None = None,
    data_date: str | None = None,
):
    monitor_filter, params = _latest_monitor_filter(trust_product_id, data_date)

    date_row = conn.execute(
        text(f"SELECT m.data_date FROM trust_asset_monitor_records m WHERE {monitor_filter} LIMIT 1"),
        params,
    ).fetchone()
    if date_row is None:
        return {"data_date": data_date, "queue": [], "selected_asset_id": None, "detail": None}

    resolved_data_date = date_row.data_date
    query_params = dict(params)
    if "data_date" not in query_params:
        query_params["data_date"] = resolved_data_date
    query_params["tolerance"] = RECONCILIATION_TOLERANCE

    recon_filter = monitor_filter
    if "data_date" not in params:
        if trust_product_id is not None:
            recon_filter = "m.trust_product_id = :trust_product_id AND m.data_date = :data_date"
        else:
            recon_filter = "m.data_date = :data_date"

    rows = conn.execute(
        text(f"""
            WITH monitor AS (
                SELECT
                    m.trust_asset_id,
                    m.asset_code,
                    COALESCE(m.custody_asset_code, ta.custody_asset_code) AS custody_asset_code,
                    COALESCE(m.source_asset_code, ta.source_asset_code, m.asset_code) AS source_asset_code,
                    m.trust_product_id,
                    m.data_date,
                    m.overdue_days,
                    m.risk_score,
                    m.risk_level,
                    m.initial_transfer_amount,
                    m.repaid_amount,
                    m.remaining_amount,
                    m.last_payment_date,
                    m.max_payment_date,
                    ta.asset_name,
                    tp.name AS trust_product_name
                FROM trust_asset_monitor_records m
                INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
                INNER JOIN trust_products tp ON tp.id = m.trust_product_id
                WHERE {recon_filter}
                  AND m.overdue_days > 0
            ),
            repayment_sum AS (
                SELECT trust_asset_id, COALESCE(SUM(actual_repayment_amount), 0) AS total_repaid
                FROM trust_repayment_detail_records
                WHERE data_date = :data_date
                  {"AND trust_product_id = :trust_product_id" if trust_product_id is not None else ""}
                GROUP BY trust_asset_id
            )
            SELECT
                mon.*,
                COALESCE(rs.total_repaid, 0) AS detail_total_repaid,
                f.id AS followup_id,
                f.status AS followup_status,
                f.owner_name AS followup_owner,
                f.overdue_reason AS followup_reason,
                f.follow_up_plan AS followup_plan,
                f.trust_feedback AS followup_feedback,
                f.last_follow_up_at AS followup_last_at
            FROM monitor mon
            LEFT JOIN repayment_sum rs ON rs.trust_asset_id = mon.trust_asset_id
            LEFT JOIN LATERAL (
                SELECT id, status, owner_name, overdue_reason, follow_up_plan,
                       trust_feedback, last_follow_up_at
                FROM trust_overdue_followups
                WHERE trust_asset_id = mon.trust_asset_id
                  AND status IN ('open', 'in_progress')
                ORDER BY id DESC
                LIMIT 1
            ) f ON TRUE
            ORDER BY mon.risk_score DESC NULLS LAST, mon.overdue_days DESC, mon.asset_code
        """),
        query_params,
    )

    queue = []
    for r in rows:
        checks = _recon_checks_for_asset(
            float(r.initial_transfer_amount),
            float(r.repaid_amount),
            float(r.remaining_amount),
            float(r.detail_total_repaid),
        )
        queue.append({
            "trust_asset_id": r.trust_asset_id,
            "asset_code": r.asset_code,
            "custody_asset_code": r.custody_asset_code,
            "source_asset_code": r.source_asset_code,
            "asset_name": r.asset_name,
            "trust_product_id": r.trust_product_id,
            "trust_product_name": r.trust_product_name,
            "data_date": str(r.data_date),
            "overdue_days": int(r.overdue_days),
            "risk_score": int(r.risk_score) if r.risk_score is not None else None,
            "risk_level": r.risk_level,
            "delinquency_bucket": delinquency_bucket(int(r.overdue_days)),
            "last_payment_date": str(r.last_payment_date) if r.last_payment_date else None,
            "checks": checks,
            "followup_id": r.followup_id,
            "followup_status": r.followup_status,
            "has_follow_up": r.followup_id is not None,
        })

    selected_id = trust_asset_id
    if selected_id is None and queue:
        selected_id = queue[0]["trust_asset_id"]

    detail = None
    if selected_id is not None:
        detail = next((q for q in queue if q["trust_asset_id"] == selected_id), None)
        if detail:
            history = [
                f for f in fetch_overdue_followups(conn, trust_product_id=trust_product_id)
                if f["trust_asset_id"] == selected_id
            ]
            detail = {**detail, "followup_history": history}

    return {
        "data_date": str(resolved_data_date),
        "queue": queue,
        "selected_asset_id": selected_id,
        "detail": detail,
    }


def create_overdue_followup_record(
    conn,
    trust_asset_id: int,
    overdue_reason: str | None,
    follow_up_plan: str | None,
    owner_name: str | None,
    trust_feedback: str | None,
) -> int:
    row = conn.execute(
        text("""
            SELECT trust_product_id, data_date, risk_score, risk_level
            FROM trust_asset_monitor_records
            WHERE trust_asset_id = :trust_asset_id
            ORDER BY data_date DESC
            LIMIT 1
        """),
        {"trust_asset_id": trust_asset_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Asset monitor record not found")

    existing = conn.execute(
        text("""
            SELECT id FROM trust_overdue_followups
            WHERE trust_asset_id = :trust_asset_id AND status IN ('open', 'in_progress')
            LIMIT 1
        """),
        {"trust_asset_id": trust_asset_id},
    ).fetchone()
    if existing:
        raise HTTPException(status_code=400, detail="Active follow-up already exists for this asset")

    result = conn.execute(
        text("""
            INSERT INTO trust_overdue_followups (
                trust_product_id, trust_asset_id, data_date, trigger_source,
                overdue_reason, follow_up_plan, status, owner_name,
                trust_feedback, risk_score, risk_level, last_follow_up_at
            ) VALUES (
                :trust_product_id, :trust_asset_id, :data_date, 'system',
                :overdue_reason, :follow_up_plan, 'open', :owner_name,
                :trust_feedback, :risk_score, :risk_level, NOW()
            )
            RETURNING id
        """),
        {
            "trust_product_id": row.trust_product_id,
            "trust_asset_id": trust_asset_id,
            "data_date": row.data_date,
            "overdue_reason": overdue_reason or None,
            "follow_up_plan": follow_up_plan or None,
            "owner_name": owner_name or None,
            "trust_feedback": trust_feedback or None,
            "risk_score": row.risk_score,
            "risk_level": row.risk_level,
        },
    ).fetchone()
    conn.commit()
    return int(result.id)


def update_overdue_followup_record(
    conn,
    followup_id: int,
    status: str | None = None,
    owner_name: str | None = None,
    overdue_reason: str | None = None,
    follow_up_plan: str | None = None,
    trust_feedback: str | None = None,
) -> None:
    row = conn.execute(
        text("SELECT id FROM trust_overdue_followups WHERE id = :id"),
        {"id": followup_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Follow-up not found")

    conn.execute(
        text("""
            UPDATE trust_overdue_followups SET
                status = COALESCE(:status, status),
                owner_name = COALESCE(:owner_name, owner_name),
                overdue_reason = COALESCE(:overdue_reason, overdue_reason),
                follow_up_plan = COALESCE(:follow_up_plan, follow_up_plan),
                trust_feedback = COALESCE(:trust_feedback, trust_feedback),
                last_follow_up_at = NOW()
            WHERE id = :id
        """),
        {
            "id": followup_id,
            "status": status,
            "owner_name": owner_name,
            "overdue_reason": overdue_reason,
            "follow_up_plan": follow_up_plan,
            "trust_feedback": trust_feedback,
        },
    )
    conn.commit()


def fmt_asset_identity(item: dict) -> str:
    custody = item.get("custody_asset_code") or "—"
    source = item.get("source_asset_code") or item.get("asset_code") or "—"
    return (
        f'<span class="asset-id">'
        f'<span title="托管房源号">{escape(str(custody))}</span>'
        f' <span class="muted" title="资产分笔号">/ {escape(str(source))}</span>'
        f"</span>"
    )


def fmt_asset_identity_block(item: dict) -> str:
    custody = item.get("custody_asset_code") or "—"
    source = item.get("source_asset_code") or item.get("asset_code") or "—"
    return f"""
      <p><span class="lbl">托管房源号</span>{escape(str(custody))}</p>
      <p><span class="lbl">资产分笔号</span>{escape(str(source))}</p>
  """


def fmt_check_result(passed: bool, label: str = "") -> str:
    if passed:
        return f'<span class="badge ok-badge">{escape(label)}通过</span>'
    return f'<span class="badge fail-badge">{escape(label)}异常</span>'


def render_overdue_workbench_html(data: dict, trust_product_id: int | None = None):
    queue = data["queue"]
    detail = data.get("detail")
    selected_id = data.get("selected_asset_id")
    data_date = data.get("data_date") or "—"

    def workbench_qs(trust_asset_id: int | None = None) -> str:
        parts = []
        if trust_product_id is not None:
            parts.append(f"trust_product_id={trust_product_id}")
        if trust_asset_id is not None:
            parts.append(f"trust_asset_id={trust_asset_id}")
        return "?" + "&".join(parts) if parts else ""

    product_hidden = (
        f'<input type="hidden" name="trust_product_id" value="{trust_product_id}">'
        if trust_product_id is not None
        else ""
    )

    queue_items = ""
    for item in queue:
        active = "active" if item["trust_asset_id"] == selected_id else ""
        recon_flag = "" if item["checks"]["cross_sheet_repayment"]["passed"] else " ⚠"
        queue_items += f"""
            <a class="queue-item {active}"
               href="/overdue/workbench{workbench_qs(item['trust_asset_id'])}">
                <div class="queue-top">
                    <span class="queue-code">{fmt_asset_identity(item)}{recon_flag}</span>
                    {fmt_risk_badge(item['risk_level']) if item.get('risk_level') else fmt_delinquency_badge(item['delinquency_bucket'])}
                </div>
                <div class="queue-meta">
                    <span>逾期 {item['overdue_days']}天</span>
                    <span>评分 {item['risk_score'] if item['risk_score'] is not None else '—'}</span>
                    <span>{'已跟进' if item['has_follow_up'] else '未跟进'}</span>
                </div>
            </a>
        """
    if not queue_items:
        queue_items = '<div class="empty">暂无逾期房源</div>'

    detail_html = '<div class="empty">请从左侧选择房源</div>'
    if detail:
        checks = detail["checks"]
        bal = checks["balance_equation"]
        cross = checks["cross_sheet_repayment"]
        owner_val = escape(detail.get("followup_owner") or "")

        followup_section = ""
        if detail.get("followup_id"):
            fid = detail["followup_id"]
            followup_section = f"""
                <div class="panel-section">
                    <h3>跟进台账</h3>
                    <p><span class="lbl">状态</span>
                       {escape(FOLLOWUP_STATUS_LABELS.get(detail['followup_status'], detail['followup_status'] or '—'))}</p>
                    <p><span class="lbl">负责人</span>{escape(detail.get('followup_owner') or '—')}</p>
                    <p><span class="lbl">逾期原因</span>{escape(detail.get('followup_reason') or '—')}</p>
                    <p><span class="lbl">跟进方案</span>{escape(detail.get('followup_plan') or '—')}</p>
                    <form class="inline-form" method="post"
                          action="/overdue/workbench/followups/{fid}/update{workbench_qs()}">
                        <input type="hidden" name="trust_asset_id" value="{detail['trust_asset_id']}">
                        {product_hidden}
                        <label>更新状态
                            <select name="status">
                                <option value="open">待处理</option>
                                <option value="in_progress">跟进中</option>
                                <option value="resolved">已解决</option>
                                <option value="closed">已关闭</option>
                            </select>
                        </label>
                        <label>负责人 <input name="owner_name" value="{owner_val}"></label>
                        <button type="submit" class="btn">更新</button>
                    </form>
                    <form class="inline-form" method="post"
                          action="/overdue/workbench/followups/{fid}/resolve{workbench_qs()}">
                        <input type="hidden" name="trust_asset_id" value="{detail['trust_asset_id']}">
                        {product_hidden}
                        <button type="submit" class="btn primary">标记已解决</button>
                    </form>
                </div>
            """
        else:
            followup_section = f"""
                <div class="panel-section">
                    <h3>创建跟进台账</h3>
                    <form method="post" action="/overdue/workbench/followups{workbench_qs()}">
                        <input type="hidden" name="trust_asset_id" value="{detail['trust_asset_id']}">
                        {product_hidden}
                        <label>逾期原因<textarea name="overdue_reason" rows="2"></textarea></label>
                        <label>跟进方案<textarea name="follow_up_plan" rows="2"></textarea></label>
                        <label>负责人<input name="owner_name"></label>
                        <label>信托反馈口径<textarea name="trust_feedback" rows="2"></textarea></label>
                        <button type="submit" class="btn primary">创建跟进</button>
                    </form>
                </div>
            """

        detail_html = f"""
            <div class="panel-section">
                <h3>{escape(detail.get('asset_name') or '房源详情')}</h3>
                {fmt_asset_identity_block(detail)}
                <p class="muted">{escape(detail['trust_product_name'])} · 数据日期 {escape(detail['data_date'])}</p>
            </div>
            <div class="panel-section kpi-row">
                <div class="kpi"><span class="lbl">逾期天数</span><span class="val warn">{detail['overdue_days']}</span></div>
                <div class="kpi"><span class="lbl">风险等级</span>{fmt_risk_badge(detail.get('risk_level'))}</div>
                <div class="kpi"><span class="lbl">M级</span>{fmt_delinquency_badge(detail['delinquency_bucket'])}</div>
                <div class="kpi"><span class="lbl">最后回款</span><span class="val">{escape(detail.get('last_payment_date') or '—')}</span></div>
            </div>
            <div class="panel-section">
                <h3>金额核对</h3>
                <table>
                    <thead><tr><th>核对项</th><th>结果</th><th>左侧</th><th>右侧</th><th>差额</th></tr></thead>
                    <tbody>
                        <tr>
                            <td>余额等式</td>
                            <td>{fmt_check_result(bal['passed'])}</td>
                            <td class="num">{fmt_money(bal['left_amount'])}</td>
                            <td class="num">{fmt_money(bal['right_amount'])}</td>
                            <td class="num {'warn' if not bal['passed'] else ''}">{fmt_money(bal['diff_amount'])}</td>
                        </tr>
                        <tr>
                            <td>跨表已还</td>
                            <td>{fmt_check_result(cross['passed'])}</td>
                            <td class="num">{fmt_money(cross['left_amount'])}</td>
                            <td class="num">{fmt_money(cross['right_amount'])}</td>
                            <td class="num {'warn' if not cross['passed'] else ''}">{fmt_money(cross['diff_amount'])}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            {followup_section}
            <div class="panel-section">
                <h3>API</h3>
                <p class="muted">
                    <a href="/overdue/checks">/overdue/checks</a> ·
                    <a href="/overdue/reconciliation">/overdue/reconciliation</a> ·
                    <a href="/overdue/followups">/overdue/followups</a>
                </p>
            </div>
        """

    json_qs = workbench_qs()
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>逾期工作台 · 房地产资产证券化平台</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
            min-height: 100vh; color: #e2e8f0; padding: 1.5rem 1rem;
        }}
        a {{ color: #38bdf8; text-decoration: none; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .breadcrumb {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 1rem; }}
        header h1 {{ font-size: 1.5rem; color: #f8fafc; }}
        header p {{ color: #94a3b8; margin-top: 0.35rem; font-size: 0.9rem; }}
        .workbench {{ display: grid; grid-template-columns: 340px 1fr; gap: 1rem; margin-top: 1.25rem; min-height: 520px; }}
        @media (max-width: 900px) {{ .workbench {{ grid-template-columns: 1fr; }} }}
        .panel {{ background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; overflow: hidden; }}
        .panel-hd {{ padding: 0.85rem 1rem; border-bottom: 1px solid rgba(255,255,255,0.08); font-weight: 600; }}
        .panel-body {{ padding: 1rem; }}
        .queue-item {{ display: block; padding: 0.85rem 1rem; border-bottom: 1px solid rgba(255,255,255,0.06); color: inherit; text-decoration: none; }}
        .queue-item:hover, .queue-item.active {{ background: rgba(56,189,248,0.08); }}
        .queue-top {{ display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }}
        .queue-code {{ font-weight: 600; color: #f8fafc; font-size: 0.9rem; }}
        .queue-meta {{ font-size: 0.78rem; color: #94a3b8; margin-top: 0.35rem; display: flex; gap: 0.65rem; flex-wrap: wrap; }}
        .panel-section {{ margin-bottom: 1.25rem; }}
        .panel-section h3 {{ font-size: 0.95rem; color: #f8fafc; margin-bottom: 0.6rem; }}
        .kpi-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0.75rem; }}
        .kpi .lbl {{ display: block; font-size: 0.75rem; color: #94a3b8; }}
        .kpi .val {{ font-size: 1.25rem; font-weight: 700; color: #f8fafc; }}
        .kpi .val.warn {{ color: #f87171; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
        th, td {{ padding: 0.5rem; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.06); }}
        th {{ color: #94a3b8; }}
        td.num {{ color: #38bdf8; font-weight: 600; }}
        td.num.warn {{ color: #f87171; }}
        .badge {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px; font-size: 0.72rem; border: 1px solid rgba(255,255,255,0.15); }}
        .ok-badge {{ background: #34d39922; color: #34d399; border-color: #34d39955; }}
        .fail-badge {{ background: #f8717122; color: #f87171; border-color: #f8717155; }}
        .empty {{ color: #64748b; text-align: center; padding: 1.5rem; }}
        .muted {{ color: #94a3b8; font-size: 0.85rem; }}
        .lbl {{ color: #64748b; font-size: 0.8rem; }}
        form label {{ display: block; margin-bottom: 0.65rem; font-size: 0.85rem; color: #94a3b8; }}
        input, select, textarea {{
            width: 100%; margin-top: 0.25rem; padding: 0.45rem 0.6rem;
            border-radius: 6px; border: 1px solid rgba(255,255,255,0.15);
            background: rgba(0,0,0,0.2); color: #e2e8f0; font-size: 0.85rem;
        }}
        .inline-form {{ display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: flex-end; margin-top: 0.75rem; }}
        .inline-form label {{ flex: 1; min-width: 140px; margin-bottom: 0; }}
        .btn {{
            display: inline-block; padding: 0.45rem 0.85rem; border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.2); background: rgba(255,255,255,0.06);
            color: #e2e8f0; font-size: 0.85rem; cursor: pointer;
        }}
        .btn.primary {{ background: rgba(56,189,248,0.25); border-color: rgba(56,189,248,0.5); }}
        footer {{ margin-top: 1.5rem; text-align: center; font-size: 0.8rem; color: #64748b; }}
    </style>
</head>
<body>
    <div class="container">
        <nav class="breadcrumb">
            <a href="/">首页</a> / <a href="/overdue">逾期管理</a> / 工作台
        </nav>
        <header>
            <h1>逾期工作台</h1>
            <p>数据日期 {escape(data_date)} · 共 {len(queue)} 户逾期 ·
               <a href="/overdue/workbench/data{json_qs}">JSON</a></p>
        </header>
        <div class="workbench">
            <div class="panel">
                <div class="panel-hd">逾期房源（按风险排序）</div>
                <div>{queue_items}</div>
            </div>
            <div class="panel">
                <div class="panel-hd">房源详情</div>
                <div class="panel-body">{detail_html}</div>
            </div>
        </div>
        <footer>Real Estate Securitization Platform</footer>
    </div>
</body>
</html>"""


def render_overdue_html(overview: dict, checks: list, reconciliation: list, followups: list):
    top_rows = ""
    for item in overview["top_overdue"]:
        top_rows += f"""
            <tr>
                <td>{escape(item["asset_code"])}</td>
                <td>{escape(item["asset_name"] or "—")}</td>
                <td>{escape(item["trust_product_name"])}</td>
                <td class="num">{item["overdue_days"]}</td>
                <td>{fmt_delinquency_badge(item["delinquency_bucket"])}</td>
                <td>{"是" if item["has_follow_up"] else "否"}</td>
            </tr>
        """
    if not top_rows:
        top_rows = '<tr><td colspan="6" class="empty">暂无逾期房源</td></tr>'

    check_rows = ""
    for item in checks[:10]:
        check_rows += f"""
            <tr>
                <td>{escape(item["asset_code"])}</td>
                <td>{item["overdue_days"]}</td>
                <td>{fmt_delinquency_badge(item["delinquency_bucket"])}</td>
                <td>{escape(item["last_payment_date"] or "—")}</td>
            </tr>
        """
    if not check_rows:
        check_rows = '<tr><td colspan="4" class="empty">暂无逾期记录</td></tr>'

    recon_rows = ""
    check_type_labels = {
        "balance_equation": "余额等式",
        "cross_sheet_repayment": "跨表已还",
    }
    for item in reconciliation[:10]:
        recon_rows += f"""
            <tr>
                <td>{escape(item["asset_code"])}</td>
                <td>{escape(check_type_labels.get(item["check_type"], item["check_type"]))}</td>
                <td class="num">{fmt_money(item["left_amount"])}</td>
                <td class="num">{fmt_money(item["right_amount"])}</td>
                <td class="num warn">{fmt_money(item["diff_amount"])}</td>
            </tr>
        """
    if not recon_rows:
        recon_rows = '<tr><td colspan="5" class="empty">暂无核对异常</td></tr>'

    followup_rows = ""
    for item in followups[:10]:
        followup_rows += f"""
            <tr>
                <td>{escape(item["asset_code"])}</td>
                <td>{escape(TRIGGER_SOURCE_LABELS.get(item["trigger_source"], item["trigger_source"]))}</td>
                <td>{escape(FOLLOWUP_STATUS_LABELS.get(item["status"], item["status"]))}</td>
                <td>{escape(item["owner_name"] or "—")}</td>
                <td>{escape(item["last_follow_up_at"] or "—")}</td>
            </tr>
        """
    if not followup_rows:
        followup_rows = '<tr><td colspan="5" class="empty">暂无跟进台账</td></tr>'

    data_date = overview.get("data_date") or "—"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>逾期管理 · 房地产资产证券化平台</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
            min-height: 100vh;
            color: #e2e8f0;
            padding: 2rem 1rem;
        }}
        a {{ color: #38bdf8; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .container {{ max-width: 960px; margin: 0 auto; }}
        .breadcrumb {{ font-size: 0.875rem; color: #94a3b8; margin-bottom: 1.5rem; }}
        header {{ margin-bottom: 2rem; }}
        header h1 {{ font-size: 1.75rem; font-weight: 700; color: #f8fafc; }}
        header p {{ margin-top: 0.5rem; color: #94a3b8; font-size: 0.95rem; }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .card {{
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 1.25rem;
            backdrop-filter: blur(8px);
        }}
        .card-label {{ font-size: 0.8rem; color: #94a3b8; margin-bottom: 0.5rem; }}
        .card-value {{ font-size: 1.75rem; font-weight: 700; color: #f8fafc; }}
        .card-value.warn {{ color: #f87171; }}
        .card-value.ok {{ color: #34d399; }}
        .section {{ margin-top: 1.5rem; }}
        .section-title {{
            font-size: 1.05rem; font-weight: 600; color: #f8fafc;
            margin-bottom: 0.75rem;
            display: flex; justify-content: space-between; align-items: center;
        }}
        .api-link {{ font-size: 0.8rem; font-weight: 400; color: #64748b; }}
        .table-wrap {{ overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
        th, td {{
            padding: 0.65rem 0.85rem;
            text-align: left;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }}
        th {{ color: #94a3b8; font-weight: 500; font-size: 0.78rem; }}
        td.num {{ color: #38bdf8; font-weight: 600; white-space: nowrap; }}
        td.num.warn {{ color: #f87171; }}
        .badge {{
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 999px;
            font-size: 0.75rem;
            background: rgba(56, 189, 248, 0.15);
            color: #7dd3fc;
            border: 1px solid rgba(56, 189, 248, 0.25);
        }}
        .empty {{ color: #64748b; text-align: center; }}
        footer {{ margin-top: 2.5rem; text-align: center; font-size: 0.8rem; color: #64748b; }}
    </style>
</head>
<body>
    <div class="container">
        <nav class="breadcrumb"><a href="/">首页</a> / 逾期管理</nav>
        <header>
            <h1>信托资产逾期管理</h1>
            <p>数据日期 {escape(data_date)} · <a href="/overdue/workbench">逾期工作台 →</a></p>
        </header>

        <div class="grid">
            <div class="card">
                <div class="card-label">逾期房源</div>
                <div class="card-value warn">{overview["overdue_count"]}</div>
            </div>
            <div class="card">
                <div class="card-label">M1 / M2 / M3 / M3+</div>
                <div class="card-value" style="font-size:1.1rem;">
                    {overview["m1_count"]} / {overview["m2_count"]} / {overview["m3_count"]} / {overview["m3_plus_count"]}
                </div>
            </div>
            <div class="card">
                <div class="card-label">核对异常</div>
                <div class="card-value warn">{overview["reconciliation_failed_count"]}</div>
            </div>
            <div class="card">
                <div class="card-label">跟进中台账</div>
                <div class="card-value">{overview["active_followup_count"]}</div>
            </div>
            <div class="card">
                <div class="card-label">监控房源总数</div>
                <div class="card-value ok">{overview["total_asset_count"]}</div>
            </div>
        </div>

        <section class="section">
            <h2 class="section-title">
                逾期房源 Top 5
                <a class="api-link" href="/overdue/checks">JSON → /overdue/checks</a>
            </h2>
            <div class="card table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>房源编号</th><th>名称</th><th>信托产品</th>
                            <th>逾期天数</th><th>等级</th><th>已建台账</th>
                        </tr>
                    </thead>
                    <tbody>{top_rows}</tbody>
                </table>
            </div>
        </section>

        <section class="section">
            <h2 class="section-title">
                逾期自检（节选）
                <a class="api-link" href="/overdue/checks">查看全部 JSON</a>
            </h2>
            <div class="card table-wrap">
                <table>
                    <thead>
                        <tr><th>房源</th><th>逾期天数</th><th>等级</th><th>最后回款日</th></tr>
                    </thead>
                    <tbody>{check_rows}</tbody>
                </table>
            </div>
        </section>

        <section class="section">
            <h2 class="section-title">
                金额核对异常
                <a class="api-link" href="/overdue/reconciliation">JSON → /overdue/reconciliation</a>
            </h2>
            <div class="card table-wrap">
                <table>
                    <thead>
                        <tr><th>房源</th><th>核对项</th><th>左侧</th><th>右侧</th><th>差额</th></tr>
                    </thead>
                    <tbody>{recon_rows}</tbody>
                </table>
            </div>
        </section>

        <section class="section">
            <h2 class="section-title">
                跟进台账
                <a class="api-link" href="/overdue/followups">JSON → /overdue/followups</a>
            </h2>
            <div class="card table-wrap">
                <table>
                    <thead>
                        <tr><th>房源</th><th>来源</th><th>状态</th><th>负责人</th><th>最近跟进</th></tr>
                    </thead>
                    <tbody>{followup_rows}</tbody>
                </table>
            </div>
        </section>

        <footer>Real Estate Securitization Platform</footer>
    </div>
</body>
</html>"""


def fmt_risk_badge(level: str | None) -> str:
    if not level:
        return '<span class="badge">—</span>'
    label = f"{level} · {risk_hub.RISK_LEVEL_LABELS.get(level, level)}"
    color = risk_hub.RISK_LEVEL_COLORS.get(level, "#94a3b8")
    return (
        f'<span class="badge" style="background:{color}22;color:{color};'
        f'border-color:{color}55;">{escape(label)}</span>'
    )


def fmt_sla_badge(status: str | None) -> str:
    if not status:
        return '<span class="badge">—</span>'
    label = risk_hub.SLA_STATUS_LABELS.get(status, status)
    color = {"on_time": "#34d399", "overdue": "#fbbf24", "breached": "#f87171"}.get(status, "#94a3b8")
    icon = "⚠️ " if status in ("overdue", "breached") else ""
    return (
        f'<span class="badge" style="background:{color}22;color:{color};'
        f'border-color:{color}55;">{icon}{escape(label)}</span>'
    )


def render_risk_workbench_html(data: dict):
    summary = data["summary"]
    queue = data["queue"]
    detail = data.get("detail")
    selected_id = data.get("selected_asset_id")

    queue_rows = ""
    for item in queue:
        active = "active" if item["trust_asset_id"] == selected_id else ""
        queue_rows += f"""
            <a class="queue-item {active}" href="/risk/workbench?trust_asset_id={item['trust_asset_id']}">
                <div class="queue-top">
                    <span class="queue-code">{fmt_asset_identity(item)}</span>
                    {fmt_risk_badge(item['risk_level'])}
                </div>
                <div class="queue-meta">
                    <span>评分 {item['risk_score'] or '—'}</span>
                    <span>逾期 {item['overdue_days']}天</span>
                    <span>预警 {item['alert_count']}</span>
                </div>
                <div class="queue-meta">
                    {fmt_sla_badge(item['sla_status'])}
                    <span>{escape(item['case_priority'] or '—')}</span>
                    <span>{escape(item['case_status'] or '无案件')}</span>
                </div>
            </a>
        """
    if not queue_rows:
        queue_rows = '<div class="empty">暂无风险队列数据</div>'

    detail_html = '<div class="empty">请从左侧选择房源查看风险画像</div>'
    if detail:
        triggers = "".join(f"<li>{escape(t)}</li>" for t in detail["risk_triggers"]) or "<li>暂无触发项</li>"
        bd = detail["score_breakdown"]
        alerts_html = ""
        for alert in detail["alerts"]:
            alerts_html += f"""
                <tr>
                    <td>{escape(alert['trigger_rule'])}</td>
                    <td>{fmt_risk_badge(alert['risk_level'])}</td>
                    <td>{escape(risk_hub.ALERT_STATUS_LABELS.get(alert['status'], alert['status']))}</td>
                </tr>
            """
        if not alerts_html:
            alerts_html = '<tr><td colspan="3" class="empty">暂无预警</td></tr>'

        case = detail.get("case")
        case_html = "暂无进行中案件"
        if case:
            case_html = f"""
                <div class="case-grid">
                    <div><span class="lbl">状态</span>{escape(FOLLOWUP_STATUS_LABELS.get(case['status'], case['status']))}</div>
                    <div><span class="lbl">负责人</span>{escape(case['owner_name'] or '—')}</div>
                    <div><span class="lbl">优先级</span>{escape(case['case_priority'] or '—')}</div>
                    <div><span class="lbl">SLA</span>{fmt_sla_badge(case['sla_status'])}</div>
                    <div><span class="lbl">截止</span>{escape(case['sla_due_date'] or '—')}</div>
                    <div><span class="lbl">下次行动</span>{escape(case['next_action_date'] or '—')}</div>
                </div>
                <p class="case-text">{escape(case['follow_up_plan'] or '—')}</p>
            """

        detail_html = f"""
            <div class="panel-section">
                <h3>风险画像</h3>
                {fmt_asset_identity_block(detail)}
                <div class="hero-score">
                    <div class="score">{detail['risk_score'] or '—'}</div>
                    <div>{fmt_risk_badge(detail['risk_level'])} {fmt_sla_badge(case['sla_status'] if case else None)}</div>
                </div>
                <div class="breakdown">
                    逾期权重 {bd['overdue_weight']} +
                    金额异常 {bd['reconciliation_weight']} +
                    回款波动 {bd['volatility_weight']}
                </div>
            </div>
            <div class="panel-section">
                <h3>风险触发源</h3>
                <ul class="triggers">{triggers}</ul>
            </div>
            <div class="panel-section">
                <h3>预警列表</h3>
                <table><thead><tr><th>规则</th><th>等级</th><th>状态</th></tr></thead>
                <tbody>{alerts_html}</tbody></table>
            </div>
            <div class="panel-section">
                <h3>案件（Case）</h3>
                {case_html}
            </div>
            <div class="panel-section actions">
                <h3>操作</h3>
                <p class="muted">API: PATCH /risk/alerts/{{id}} · POST /risk/cases · POST /risk/score/recalculate</p>
                <div class="btn-row">
                    <a class="btn" href="/risk/alerts">查看全部预警</a>
                    <a class="btn" href="/risk/cases">查看全部案件</a>
                    <a class="btn primary" href="/risk/assets/{detail['trust_asset_id']}">JSON 详情</a>
                </div>
            </div>
        """

    data_date = data.get("data_date") or "—"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>风控工作台 · 房地产资产证券化平台</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
            min-height: 100vh; color: #e2e8f0; padding: 1.5rem 1rem;
        }}
        a {{ color: #38bdf8; text-decoration: none; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .breadcrumb {{ font-size: 0.85rem; color: #94a3b8; margin-bottom: 1rem; }}
        header h1 {{ font-size: 1.6rem; color: #f8fafc; }}
        header p {{ color: #94a3b8; margin-top: 0.35rem; font-size: 0.9rem; }}
        .kpi-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 0.75rem; margin: 1.25rem 0;
        }}
        .kpi {{
            background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 10px; padding: 0.85rem;
        }}
        .kpi .lbl {{ font-size: 0.75rem; color: #94a3b8; }}
        .kpi .val {{ font-size: 1.35rem; font-weight: 700; margin-top: 0.25rem; }}
        .kpi .val.warn {{ color: #f87171; }}
        .workbench {{
            display: grid; grid-template-columns: 360px 1fr; gap: 1rem; min-height: 520px;
        }}
        @media (max-width: 900px) {{ .workbench {{ grid-template-columns: 1fr; }} }}
        .panel {{
            background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px; overflow: hidden;
        }}
        .panel-hd {{
            padding: 0.85rem 1rem; border-bottom: 1px solid rgba(255,255,255,0.08);
            font-weight: 600; color: #f8fafc;
        }}
        .queue-item {{
            display: block; padding: 0.85rem 1rem; border-bottom: 1px solid rgba(255,255,255,0.06);
            color: inherit; text-decoration: none;
        }}
        .queue-item:hover, .queue-item.active {{
            background: rgba(56,189,248,0.08);
        }}
        .queue-top {{ display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }}
        .queue-code {{ font-weight: 600; color: #f8fafc; }}
        .queue-meta {{ font-size: 0.78rem; color: #94a3b8; margin-top: 0.35rem; display: flex; gap: 0.65rem; flex-wrap: wrap; }}
        .panel-body {{ padding: 1rem; }}
        .panel-section {{ margin-bottom: 1.25rem; }}
        .panel-section h3 {{ font-size: 0.9rem; color: #94a3b8; margin-bottom: 0.6rem; }}
        .hero-score {{ display: flex; align-items: center; gap: 1rem; }}
        .hero-score .score {{ font-size: 2.5rem; font-weight: 700; color: #f87171; }}
        .breakdown {{ font-size: 0.82rem; color: #94a3b8; margin-top: 0.5rem; }}
        .triggers {{ margin-left: 1.1rem; font-size: 0.9rem; color: #e2e8f0; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
        th, td {{ padding: 0.5rem; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.06); }}
        th {{ color: #94a3b8; font-weight: 500; }}
        .badge {{
            display: inline-block; padding: 0.15rem 0.5rem; border-radius: 999px;
            font-size: 0.72rem; border: 1px solid rgba(255,255,255,0.15);
        }}
        .case-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.5rem; font-size: 0.85rem; }}
        .case-grid .lbl {{ display: block; color: #64748b; font-size: 0.75rem; }}
        .case-text {{ margin-top: 0.5rem; font-size: 0.85rem; color: #cbd5e1; }}
        .btn-row {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }}
        .btn {{
            display: inline-block; padding: 0.45rem 0.85rem; border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.15); font-size: 0.82rem; color: #e2e8f0;
        }}
        .btn.primary {{ background: rgba(56,189,248,0.2); border-color: rgba(56,189,248,0.4); }}
        .empty {{ color: #64748b; text-align: center; padding: 1.5rem; }}
        .muted {{ color: #64748b; font-size: 0.8rem; }}
        footer {{ margin-top: 1.5rem; text-align: center; font-size: 0.8rem; color: #64748b; }}
    </style>
</head>
<body>
    <div class="container">
        <nav class="breadcrumb"><a href="/">首页</a> / 信托资产风险中台 / 工作台</nav>
        <header>
            <h1>信托资产风险中台 · Risk Control Hub</h1>
            <p>数据日期 {escape(data_date)} · <a href="/risk/workbench/data">JSON</a> · <a href="/overdue">V1 逾期视图</a></p>
        </header>
        <div class="kpi-grid">
            <div class="kpi"><div class="lbl">A 高风险</div><div class="val warn">{summary['level_a_count']}</div></div>
            <div class="kpi"><div class="lbl">B / C</div><div class="val">{summary['level_b_count']} / {summary['level_c_count']}</div></div>
            <div class="kpi"><div class="lbl">平均风险分</div><div class="val">{summary['avg_risk_score']}</div></div>
            <div class="kpi"><div class="lbl">开放预警</div><div class="val warn">{summary['open_alert_count']}</div></div>
            <div class="kpi"><div class="lbl">SLA 异常案件</div><div class="val warn">{summary['sla_breached_count']}</div></div>
            <div class="kpi"><div class="lbl">逾期房源</div><div class="val">{summary['overdue_count']}</div></div>
        </div>
        <div class="workbench">
            <div class="panel">
                <div class="panel-hd">Risk Queue · 风险队列</div>
                <div>{queue_rows}</div>
            </div>
            <div class="panel">
                <div class="panel-hd">Risk Control Panel · 风控面板</div>
                <div class="panel-body">{detail_html}</div>
            </div>
        </div>
        <footer>Real Estate Securitization Platform · Risk Ops Platform</footer>
    </div>
</body>
</html>"""


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
def dashboard(page_user: Annotated[dict, Depends(get_page_user)]):
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

        overdue_count = 0
        high_risk_count = 0
        try:
            overdue_row = conn.execute(text("""
                SELECT COUNT(*) AS cnt
                FROM trust_asset_monitor_records m
                WHERE m.data_date = (SELECT MAX(data_date) FROM trust_asset_monitor_records)
                  AND m.overdue_days > 0
            """)).fetchone()
            if overdue_row:
                overdue_count = int(overdue_row.cnt)
            risk_row = conn.execute(text("""
                SELECT COUNT(*) AS cnt
                FROM trust_asset_monitor_records m
                WHERE m.data_date = (SELECT MAX(data_date) FROM trust_asset_monitor_records)
                  AND m.risk_level = 'A'
            """)).fetchone()
            if risk_row:
                high_risk_count = int(risk_row.cnt)
        except Exception:
            overdue_count = 0
            high_risk_count = 0

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
        a.card-link {{
            display: block;
            color: inherit;
            text-decoration: none;
        }}
        a.card-link:hover {{
            text-decoration: none;
        }}
        .card-value.overdue {{
            color: #f87171;
        }}
        .card-value.risk {{
            color: #fb923c;
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
            <a href="/ingestion/upload" class="card card-link">
                <div class="card-label">数据导入 V2</div>
                <div class="card-value" style="font-size:1.25rem;">Excel</div>
                <div class="card-label" style="margin-top:0.5rem;margin-bottom:0;">还款明细 / 监控快照 →</div>
            </a>
            <a href="/ingestion/repayment-records" class="card card-link">
                <div class="card-label">还款明细</div>
                <div class="card-value" style="font-size:1.25rem;">查看</div>
            </a>
            <a href="/ingestion/monitor-records" class="card card-link">
                <div class="card-label">监控快照</div>
                <div class="card-value" style="font-size:1.25rem;">查看</div>
            </a>
            <a href="/risk/workbench" class="card card-link">
                <div class="card-label">风控中台</div>
                <div class="card-value risk">{high_risk_count}</div>
                <div class="card-label" style="margin-top:0.5rem;margin-bottom:0;">A 类高风险资产 →</div>
            </a>
            <a href="/overdue" class="card card-link">
                <div class="card-label">逾期管理 (V1)</div>
                <div class="card-value overdue">{overdue_count}</div>
                <div class="card-label" style="margin-top:0.5rem;margin-bottom:0;">当前逾期房源 →</div>
            </a>
        </div>
        <footer>Real Estate Securitization Platform</footer>
    </div>
</body>
</html>"""
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))

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
def asset_pool_detail(
    asset_pool_id: int,
    page_user: Annotated[dict, Depends(get_page_user)],
):
    with engine.connect() as conn:
        data = fetch_asset_pool_overview(conn, asset_pool_id)
        if data is None:
            return HTMLResponse(content=render_not_found_html(), status_code=404)
        investor_map = fetch_investor_map(conn)
        html = render_asset_pool_detail_html(data, investor_map)

    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))

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

@app.get("/overdue/overview")
def overdue_overview(trust_product_id: int | None = None, data_date: str | None = None):
    with engine.connect() as conn:
        return fetch_overdue_overview(conn, trust_product_id, data_date)


@app.get("/overdue/checks")
def overdue_checks(trust_product_id: int | None = None, data_date: str | None = None):
    with engine.connect() as conn:
        return fetch_overdue_checks(conn, trust_product_id, data_date)


@app.get("/overdue/reconciliation")
def overdue_reconciliation(trust_product_id: int | None = None, data_date: str | None = None):
    with engine.connect() as conn:
        return fetch_reconciliation(conn, trust_product_id, data_date)


@app.get("/overdue/followups")
def overdue_followups(trust_product_id: int | None = None, status: str | None = None):
    with engine.connect() as conn:
        return fetch_overdue_followups(conn, trust_product_id, status)


@app.get("/overdue", response_class=HTMLResponse)
def overdue_dashboard(page_user: Annotated[dict, Depends(get_page_user)]):
    with engine.connect() as conn:
        overview = fetch_overdue_overview(conn)
        checks_data = fetch_overdue_checks(conn)
        recon_data = fetch_reconciliation(conn)
        followups = fetch_overdue_followups(conn)

    html = render_overdue_html(
        overview,
        checks_data["items"],
        recon_data["items"],
        followups,
    )
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


def _workbench_redirect(trust_asset_id: int, trust_product_id: int | None) -> RedirectResponse:
    qs = f"?trust_asset_id={trust_asset_id}"
    if trust_product_id is not None:
        qs += f"&trust_product_id={trust_product_id}"
    return RedirectResponse(url=f"/overdue/workbench{qs}", status_code=303)


@app.get("/overdue/workbench/data")
def overdue_workbench_data(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: int | None = None,
    trust_asset_id: int | None = None,
    data_date: str | None = None,
):
    with engine.connect() as conn:
        return fetch_overdue_workbench(conn, trust_product_id, trust_asset_id, data_date)


@app.get("/overdue/workbench", response_class=HTMLResponse)
def overdue_workbench_page(
    page_user: Annotated[dict, Depends(get_page_user)],
    trust_product_id: int | None = None,
    trust_asset_id: int | None = None,
    data_date: str | None = None,
):
    with engine.connect() as conn:
        data = fetch_overdue_workbench(conn, trust_product_id, trust_asset_id, data_date)
    html = render_overdue_workbench_html(data, trust_product_id)
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


@app.post("/overdue/workbench/followups")
def overdue_workbench_create_followup(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_asset_id: int = Form(...),
    trust_product_id: int | None = Form(None),
    overdue_reason: str = Form(""),
    follow_up_plan: str = Form(""),
    owner_name: str = Form(""),
    trust_feedback: str = Form(""),
):
    with engine.connect() as conn:
        create_overdue_followup_record(
            conn, trust_asset_id, overdue_reason, follow_up_plan, owner_name, trust_feedback
        )
    return _workbench_redirect(trust_asset_id, trust_product_id)


@app.post("/overdue/workbench/followups/{followup_id}/update")
def overdue_workbench_update_followup(
    followup_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_asset_id: int = Form(...),
    trust_product_id: int | None = Form(None),
    status: str = Form("in_progress"),
    owner_name: str = Form(""),
):
    with engine.connect() as conn:
        update_overdue_followup_record(
            conn, followup_id, status=status or None, owner_name=owner_name or None
        )
    return _workbench_redirect(trust_asset_id, trust_product_id)


@app.post("/overdue/workbench/followups/{followup_id}/resolve")
def overdue_workbench_resolve_followup(
    followup_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_asset_id: int = Form(...),
    trust_product_id: int | None = Form(None),
):
    with engine.connect() as conn:
        update_overdue_followup_record(conn, followup_id, status="resolved")
    return _workbench_redirect(trust_asset_id, trust_product_id)


@app.get("/risk/workbench/data")
def risk_workbench_data(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: int | None = None,
    trust_asset_id: int | None = None,
):
    with engine.connect() as conn:
        return risk_hub.fetch_risk_workbench(conn, trust_product_id, trust_asset_id)


@app.get("/risk/workbench", response_class=HTMLResponse)
def risk_workbench_page(
    page_user: Annotated[dict, Depends(get_page_user)],
    trust_product_id: int | None = None,
    trust_asset_id: int | None = None,
):
    with engine.connect() as conn:
        data = risk_hub.fetch_risk_workbench(conn, trust_product_id, trust_asset_id)
    html = render_risk_workbench_html(data)
    return HTMLResponse(content=auth_html.inject_user_bar(html, page_user["username"]))


@app.get("/risk/assets")
def risk_assets(trust_product_id: int | None = None, risk_level: str | None = None):
    with engine.connect() as conn:
        return risk_hub.fetch_risk_assets(conn, trust_product_id, risk_level)


@app.get("/risk/assets/{trust_asset_id}")
def risk_asset_detail(trust_asset_id: int):
    with engine.connect() as conn:
        detail = risk_hub.fetch_risk_asset_detail(conn, trust_asset_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Risk asset not found")
    return detail


@app.post("/risk/score/recalculate")
def risk_score_recalculate(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: int | None = None,
):
    with engine.connect() as conn:
        return risk_hub.recalculate_risk_scores(conn, trust_product_id)


@app.get("/risk/alerts")
def risk_alerts(
    trust_product_id: int | None = None,
    trust_asset_id: int | None = None,
    status: str | None = None,
):
    with engine.connect() as conn:
        return risk_hub.fetch_risk_alerts(conn, trust_product_id, trust_asset_id, status=status)


@app.patch("/risk/alerts/{alert_id}")
def risk_alert_patch(
    alert_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(...),
):
    with engine.connect() as conn:
        result = risk_hub.patch_risk_alert(conn, alert_id, body)
    if result is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return result


@app.get("/risk/cases")
def risk_cases(
    trust_product_id: int | None = None,
    trust_asset_id: int | None = None,
    status: str | None = None,
):
    with engine.connect() as conn:
        return risk_hub.fetch_risk_cases(conn, trust_product_id, trust_asset_id, status)


@app.post("/risk/cases")
def risk_case_create(
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(...),
):
    if "trust_asset_id" not in body:
        raise HTTPException(status_code=400, detail="trust_asset_id is required")
    with engine.connect() as conn:
        result = risk_hub.create_risk_case(conn, body)
    if result is None:
        raise HTTPException(status_code=404, detail="Asset monitor data not found")
    return result


@app.patch("/risk/cases/{case_id}")
def risk_case_patch(
    case_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(...),
):
    with engine.connect() as conn:
        result = risk_hub.patch_risk_case(conn, case_id, body)
    if result is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return result


@app.get("/login", response_class=HTMLResponse)
def login_page(next: str = "/"):
    return HTMLResponse(content=auth_html.render_login_page(None, _safe_next_path(next)))


@app.post("/login")
def login_submit(
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    next_safe = _safe_next_path(next)
    with engine.connect() as conn:
        user = auth.authenticate_user(conn, username, password)
    if user is None:
        return HTMLResponse(
            content=auth_html.render_login_page("用户名或密码错误", next_safe),
            status_code=401,
        )
    token = auth.create_access_token(user["id"], user["username"], user["role"])
    redirect = RedirectResponse(url=next_safe, status_code=303)
    auth.set_auth_cookie(redirect, token)
    return redirect


@app.post("/logout")
def logout():
    redirect = RedirectResponse(url="/login", status_code=303)
    auth.clear_auth_cookie(redirect)
    return redirect


@app.post("/auth/login")
def auth_login(body: auth.LoginRequest, response: Response):
    with engine.connect() as conn:
        result = auth.login(conn, body.username, body.password)
    auth.set_auth_cookie(response, result["access_token"])
    return result


@app.get("/auth/me")
def auth_me(current_user: Annotated[dict, Depends(get_current_user)]):
    return current_user


@app.post("/ingestion/pipeline")
def ingestion_pipeline_run(
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(default={}),
):
    trust_product_id = body.get("trust_product_id")
    if trust_product_id is None:
        raise HTTPException(status_code=400, detail="trust_product_id is required")
    with engine.connect() as conn:
        return ingestion_pipeline.run_ingestion_pipeline(
            conn,
            trust_product_id=int(trust_product_id),
            trust_plan_alias=body.get("trust_plan_alias"),
            excel_path=body.get("excel_path"),
            asset_lookup_path=body.get("asset_lookup_path"),
            user_id=current_user["id"],
        )


@app.get("/ingestion/upload", response_class=HTMLResponse)
def ingestion_upload_page(page_user: Annotated[dict, Depends(get_page_user)]):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, name FROM trust_products ORDER BY id"))
        products = [{"id": r.id, "name": r.name} for r in rows]
    return HTMLResponse(content=ingestion_html.render_upload_page(products, page_user["username"]))


@app.post("/ingestion/preview")
async def ingestion_preview(
    current_user: Annotated[dict, Depends(get_current_user)],
    trust_product_id: int = Form(...),
    files: list[UploadFile] = File(...),
):
    batch_uuid = str(uuid.uuid4())
    saved = await ingestion_upload.save_batch_files(batch_uuid, files)
    with engine.connect() as conn:
        return ingestion_upload.run_preview(conn, trust_product_id, batch_uuid, saved)


@app.post("/ingestion/import")
def ingestion_import(
    current_user: Annotated[dict, Depends(get_current_user)],
    body: dict = Body(...),
):
    batch_uuid = body.get("batch_uuid")
    trust_product_id = body.get("trust_product_id")
    if not batch_uuid or trust_product_id is None:
        raise HTTPException(status_code=400, detail="batch_uuid and trust_product_id required")
    with engine.connect() as conn:
        return ingestion_upload.run_import(
            conn,
            batch_uuid=batch_uuid,
            trust_product_id=int(trust_product_id),
            user_id=current_user["id"],
            confirm_sheet_keys=body.get("confirm_sheet_keys"),
        )


@app.get("/ingestion/repayment-records/data")
def ingestion_repayment_records_data(
    current_user: Annotated[dict, Depends(get_current_user)],
    page: int = 1,
    page_size: int = 50,
    trust_product_id: str | None = Query(default=None),
    data_date: str | None = Query(default=None),
    asset_code: str | None = Query(default=None),
    custody_asset_code: str | None = Query(default=None),
    source_asset_code: str | None = Query(default=None),
    source_file_name: str | None = Query(default=None),
    source_sheet_name: str | None = Query(default=None),
):
    filters = ingestion_upload.build_record_filters(
        trust_product_id=trust_product_id,
        data_date=data_date,
        asset_code=asset_code,
        custody_asset_code=custody_asset_code,
        source_asset_code=source_asset_code,
        source_file_name=source_file_name,
        source_sheet_name=source_sheet_name,
    )
    with engine.connect() as conn:
        return ingestion_upload.fetch_paginated_records(
            conn, "repayment", page, page_size, filters,
        )


@app.get("/ingestion/repayment-records", response_class=HTMLResponse)
def ingestion_repayment_records_page(
    page_user: Annotated[dict, Depends(get_page_user)],
    page: int = 1,
    page_size: int = 50,
    trust_product_id: str | None = Query(default=None),
    data_date: str | None = Query(default=None),
    asset_code: str | None = Query(default=None),
    custody_asset_code: str | None = Query(default=None),
    source_asset_code: str | None = Query(default=None),
    source_file_name: str | None = Query(default=None),
    source_sheet_name: str | None = Query(default=None),
):
    filters = ingestion_upload.build_record_filters(
        trust_product_id=trust_product_id,
        data_date=data_date,
        asset_code=asset_code,
        custody_asset_code=custody_asset_code,
        source_asset_code=source_asset_code,
        source_file_name=source_file_name,
        source_sheet_name=source_sheet_name,
    )
    with engine.connect() as conn:
        data = ingestion_upload.fetch_paginated_records(
            conn, "repayment", page, page_size, filters,
        )
        products = [
            {"id": r.id, "name": r.name}
            for r in conn.execute(text("SELECT id, name FROM trust_products ORDER BY id"))
        ]
    return HTMLResponse(content=ingestion_html.render_records_page(
        "还款明细", "/ingestion/repayment-records/data", filters, data, products,
        page_user["username"],
        record_type="repayment",
    ))


@app.get("/ingestion/monitor-records/data")
def ingestion_monitor_records_data(
    current_user: Annotated[dict, Depends(get_current_user)],
    page: int = 1,
    page_size: int = 50,
    trust_product_id: str | None = Query(default=None),
    data_date: str | None = Query(default=None),
    asset_code: str | None = Query(default=None),
    custody_asset_code: str | None = Query(default=None),
    source_asset_code: str | None = Query(default=None),
    source_file_name: str | None = Query(default=None),
    source_sheet_name: str | None = Query(default=None),
):
    filters = ingestion_upload.build_record_filters(
        trust_product_id=trust_product_id,
        data_date=data_date,
        asset_code=asset_code,
        custody_asset_code=custody_asset_code,
        source_asset_code=source_asset_code,
        source_file_name=source_file_name,
        source_sheet_name=source_sheet_name,
    )
    with engine.connect() as conn:
        return ingestion_upload.fetch_paginated_records(
            conn, "monitor", page, page_size, filters,
        )


@app.get("/ingestion/monitor-records", response_class=HTMLResponse)
def ingestion_monitor_records_page(
    page_user: Annotated[dict, Depends(get_page_user)],
    page: int = 1,
    page_size: int = 50,
    trust_product_id: str | None = Query(default=None),
    data_date: str | None = Query(default=None),
    asset_code: str | None = Query(default=None),
    custody_asset_code: str | None = Query(default=None),
    source_asset_code: str | None = Query(default=None),
    source_file_name: str | None = Query(default=None),
    source_sheet_name: str | None = Query(default=None),
):
    filters = ingestion_upload.build_record_filters(
        trust_product_id=trust_product_id,
        data_date=data_date,
        asset_code=asset_code,
        custody_asset_code=custody_asset_code,
        source_asset_code=source_asset_code,
        source_file_name=source_file_name,
        source_sheet_name=source_sheet_name,
    )
    with engine.connect() as conn:
        data = ingestion_upload.fetch_paginated_records(
            conn, "monitor", page, page_size, filters,
        )
        products = [
            {"id": r.id, "name": r.name}
            for r in conn.execute(text("SELECT id, name FROM trust_products ORDER BY id"))
        ]
    return HTMLResponse(content=ingestion_html.render_records_page(
        "资产监控快照", "/ingestion/monitor-records/data", filters, data, products,
        page_user["username"],
        record_type="monitor",
    ))
