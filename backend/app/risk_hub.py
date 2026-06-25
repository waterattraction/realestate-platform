"""信托资产风险中台 V2 — Risk Control Hub helpers."""

from sqlalchemy import text

from app.overdue.buckets import (
    M1_MAX_DAYS,
    M2_MAX_DAYS,
    M3_MAX_DAYS,
    M3_MIN_DAYS,
    M2_MIN_DAYS,
    M3_PLUS_MIN_DAYS,
    OVERDUE_ASSET_MIN_DAYS,
    PERFORMING_MAX_DAYS,
    RECONCILIATION_TOLERANCE_DEFAULT,
    is_payment_gap_risk,
    sql_risk_payment_gap_component,
    sql_risk_score_overdue_component,
)

RECONCILIATION_TOLERANCE = RECONCILIATION_TOLERANCE_DEFAULT

RISK_LEVEL_LABELS = {
    "ES": "提前结清",
    "A": "高风险",
    "B": "中高风险",
    "C": "中风险",
    "D": "正常",
}

RISK_LEVEL_COLORS = {
    "ES": "#38bdf8",
    "A": "#f87171",
    "B": "#fb923c",
    "C": "#fbbf24",
    "D": "#34d399",
}


def is_es_closed(remaining_amount: float) -> bool:
    return remaining_amount <= RECONCILIATION_TOLERANCE


def _nullable_int(value) -> int | None:
    if value is None:
        return None
    return int(value)


def _settlement_date(last_payment_date, max_payment_date) -> str | None:
    if max_payment_date:
        return str(max_payment_date)
    if last_payment_date:
        return str(last_payment_date)
    return None


def resolve_lifecycle_risk_level(remaining_amount: float, stored_risk_level: str | None) -> str:
    if is_es_closed(remaining_amount):
        return "ES"
    return stored_risk_level or "D"


def monitor_record_api_fields(row) -> dict:
    """API 字段：保留 overdue_days=NULL（ES），另提供 overdue_days_safe 供计算兼容。"""
    remaining = float(row.remaining_amount)
    is_es = is_es_closed(remaining)
    od_raw = row.overdue_days if hasattr(row, "overdue_days") else None
    if hasattr(row, "overdue_days_safe") and row.overdue_days_safe is not None:
        overdue_days_safe = int(row.overdue_days_safe)
    else:
        overdue_days_safe = 0 if od_raw is None else int(od_raw)
    overdue_days = None if is_es else _nullable_int(od_raw)
    last_pd = getattr(row, "last_payment_date", None)
    max_pd = getattr(row, "max_payment_date", None)
    settlement = _settlement_date(last_pd, max_pd)
    stored_rl = getattr(row, "risk_level", None)
    lifecycle = resolve_lifecycle_risk_level(remaining, stored_rl)
    return {
        "remaining_amount": remaining,
        "overdue_days": overdue_days,
        "overdue_days_safe": overdue_days_safe,
        "risk_level": lifecycle,
        "stored_risk_level": stored_rl,
        "status": "closed" if is_es else "active",
        "is_es": is_es,
        "last_payment_date": settlement if is_es else (str(last_pd) if last_pd else None),
        "settlement_date": settlement if is_es else None,
    }

ALERT_STATUS_LABELS = {
    "open": "待处理",
    "acknowledged": "已确认",
    "resolved": "已解决",
    "ignored": "已忽略",
}

SLA_STATUS_LABELS = {
    "on_time": "正常",
    "overdue": "临近超时",
    "breached": "已超时",
}

CASE_PRIORITY_MAP = {"A": "P0", "B": "P1", "C": "P2", "D": "P3"}

RISK_SCORE_UPDATE_SQL = f"""
WITH latest AS (
    SELECT trust_product_id, MAX(data_date) AS data_date
    FROM trust_asset_monitor_records
    GROUP BY trust_product_id
),
monitor AS (
    SELECT m.*
    FROM trust_asset_monitor_records m
    INNER JOIN latest l
        ON l.trust_product_id = m.trust_product_id AND l.data_date = m.data_date
),
repayment_sum AS (
    SELECT r.trust_asset_id, r.data_date, COALESCE(SUM(r.actual_repayment_amount), 0) AS total_repaid
    FROM trust_repayment_detail_records r
    INNER JOIN latest l ON l.trust_product_id = r.trust_product_id AND l.data_date = r.data_date
    GROUP BY r.trust_asset_id, r.data_date
),
scored AS (
    SELECT
        m.id,
        m.trust_asset_id,
        m.trust_product_id,
        m.data_date,
        m.overdue_days,
        (
            {sql_risk_score_overdue_component()}
            + CASE
                WHEN m.remaining_amount <= :tolerance THEN 0
                WHEN ABS((m.initial_transfer_amount - m.repaid_amount) - m.remaining_amount)
                     > :tolerance THEN 30
                WHEN ABS(m.repaid_amount - COALESCE(rs.total_repaid, 0)) > :tolerance THEN 30
                ELSE 0
            END
            + {sql_risk_payment_gap_component()}
        ) AS risk_score
    FROM monitor m
    LEFT JOIN repayment_sum rs
        ON rs.trust_asset_id = m.trust_asset_id AND rs.data_date = m.data_date
)
UPDATE trust_asset_monitor_records m
SET
    risk_score = s.risk_score,
    risk_level = CASE
        WHEN s.risk_score >= 80 THEN 'A'
        WHEN s.risk_score >= 60 THEN 'B'
        WHEN s.risk_score >= 40 THEN 'C'
        ELSE 'D'
    END
FROM scored s
WHERE m.id = s.id
"""


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
                SELECT MAX(data_date) FROM trust_asset_monitor_records
                WHERE trust_product_id = :trust_product_id
            )
            """,
            {"trust_product_id": trust_product_id},
        )

    return (
        "m.data_date = (SELECT MAX(data_date) FROM trust_asset_monitor_records)",
        {},
    )


def _sla_interval_sql(risk_level_expr: str) -> str:
    return f"""
        CASE {risk_level_expr}
            WHEN 'A' THEN INTERVAL '1 day'
            WHEN 'B' THEN INTERVAL '3 days'
            WHEN 'C' THEN INTERVAL '7 days'
            ELSE NULL
        END
    """


def compute_sla_status(sla_due_date, case_status: str, created_at) -> str:
    if case_status in ("resolved", "closed") or sla_due_date is None:
        return "on_time"
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    due = sla_due_date
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    created = created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if now <= due:
        return "on_time"
    window = due - created
    if window.total_seconds() <= 0:
        window = due - due
    breach_at = due + window
    if now <= breach_at:
        return "overdue"
    return "breached"


def recalculate_risk_scores(conn, trust_product_id: int | None = None) -> dict:
    conn.execute(
        text(RISK_SCORE_UPDATE_SQL),
        {"tolerance": RECONCILIATION_TOLERANCE},
    )

    alert_stats = sync_risk_alerts(conn, trust_product_id)
    case_stats = sync_risk_cases(conn, trust_product_id)

    count_sql = """
        SELECT COUNT(*) AS cnt, MAX(data_date) AS data_date
        FROM trust_asset_monitor_records m
        WHERE m.risk_score IS NOT NULL
    """
    params: dict = {}
    if trust_product_id is not None:
        count_sql += " AND m.trust_product_id = :trust_product_id"
        params["trust_product_id"] = trust_product_id

    row = conn.execute(text(count_sql), params).fetchone()
    conn.commit()

    return {
        "updated_count": int(row.cnt) if row else 0,
        "data_date": str(row.data_date) if row and row.data_date else None,
        "alerts_created": alert_stats["created"],
        "cases_created": case_stats["created"],
        "cases_updated": case_stats["updated"],
    }


def sync_risk_alerts(conn, trust_product_id: int | None = None) -> dict:
    params: dict = {
        "tolerance": RECONCILIATION_TOLERANCE,
        "m3_plus_min_days": M3_PLUS_MIN_DAYS,
    }
    product_filter = ""
    if trust_product_id is not None:
        product_filter = "AND m.trust_product_id = :trust_product_id"
        params["trust_product_id"] = trust_product_id

    rows = conn.execute(
        text(f"""
            WITH latest AS (
                SELECT trust_product_id, MAX(data_date) AS data_date
                FROM trust_asset_monitor_records
                GROUP BY trust_product_id
            ),
            monitor AS (
                SELECT m.*
                FROM trust_asset_monitor_records m
                INNER JOIN latest l
                    ON l.trust_product_id = m.trust_product_id AND l.data_date = m.data_date
                WHERE 1=1 {product_filter}
            ),
            repayment_sum AS (
                SELECT r.trust_asset_id, r.data_date,
                       COALESCE(SUM(r.actual_repayment_amount), 0) AS total_repaid
                FROM trust_repayment_detail_records r
                INNER JOIN latest l
                    ON l.trust_product_id = r.trust_product_id AND l.data_date = r.data_date
                GROUP BY r.trust_asset_id, r.data_date
            ),
            triggers AS (
                SELECT m.trust_product_id, m.trust_asset_id, m.data_date, m.risk_level,
                       'delinquency_m3_plus' AS risk_type,
                       '逾期天数 ≥92（M3+）' AS trigger_rule
                FROM monitor m
                WHERE m.remaining_amount > :tolerance
                  AND COALESCE(m.overdue_days, 0) >= :m3_plus_min_days
                UNION ALL
                SELECT m.trust_product_id, m.trust_asset_id, m.data_date, m.risk_level,
                       'reconciliation_failure',
                       '金额核对失败'
                FROM monitor m
                LEFT JOIN repayment_sum rs
                    ON rs.trust_asset_id = m.trust_asset_id AND rs.data_date = m.data_date
                WHERE m.remaining_amount > :tolerance
                  AND (
                      ABS((m.initial_transfer_amount - m.repaid_amount) - m.remaining_amount) > :tolerance
                   OR ABS(m.repaid_amount - COALESCE(rs.total_repaid, 0)) > :tolerance
                  )
                UNION ALL
                SELECT m.trust_product_id, m.trust_asset_id, m.data_date, m.risk_level,
                       'high_risk_score',
                       'risk_score >= 80'
                FROM monitor m
                WHERE m.remaining_amount > :tolerance
                  AND m.risk_score >= 80
            )
            SELECT * FROM triggers
        """),
        params,
    )

    created = 0
    for row in rows:
        result = conn.execute(
            text("""
                INSERT INTO risk_alerts (
                    trust_product_id, trust_asset_id, data_date,
                    risk_type, risk_level, trigger_rule, status
                )
                SELECT :trust_product_id, :trust_asset_id, :data_date,
                       :risk_type, :risk_level, :trigger_rule, 'open'
                WHERE NOT EXISTS (
                    SELECT 1 FROM risk_alerts
                    WHERE trust_asset_id = :trust_asset_id
                      AND data_date = :data_date
                      AND risk_type = :risk_type
                      AND status IN ('open', 'acknowledged')
                )
            """),
            {
                "trust_product_id": row.trust_product_id,
                "trust_asset_id": row.trust_asset_id,
                "data_date": row.data_date,
                "risk_type": row.risk_type,
                "risk_level": row.risk_level,
                "trigger_rule": row.trigger_rule,
            },
        )
        created += result.rowcount

    return {"created": created}


def sync_risk_cases(conn, trust_product_id: int | None = None) -> dict:
    params: dict = {
        "tolerance": RECONCILIATION_TOLERANCE,
        "overdue_min_days": OVERDUE_ASSET_MIN_DAYS,
    }
    product_filter = ""
    if trust_product_id is not None:
        product_filter = "AND m.trust_product_id = :trust_product_id"
        params["trust_product_id"] = trust_product_id

    rows = conn.execute(
        text(f"""
            WITH latest AS (
                SELECT trust_product_id, MAX(data_date) AS data_date
                FROM trust_asset_monitor_records
                GROUP BY trust_product_id
            ),
            monitor AS (
                SELECT m.*
                FROM trust_asset_monitor_records m
                INNER JOIN latest l
                    ON l.trust_product_id = m.trust_product_id AND l.data_date = m.data_date
                WHERE m.remaining_amount > :tolerance
                  AND COALESCE(m.overdue_days, 0) >= :overdue_min_days
                  AND m.risk_level IN ('A', 'B', 'C')
                {product_filter}
            )
            SELECT * FROM monitor
        """),
        params,
    )

    created = 0
    updated = 0
    for row in rows:
        priority = CASE_PRIORITY_MAP.get(row.risk_level, "P3")
        existing = conn.execute(
            text("""
                SELECT id, status FROM trust_overdue_followups
                WHERE trust_asset_id = :trust_asset_id
                  AND status IN ('open', 'in_progress')
                LIMIT 1
            """),
            {"trust_asset_id": row.trust_asset_id},
        ).fetchone()

        sla_interval = {"A": "1 day", "B": "3 days", "C": "7 days"}.get(row.risk_level)

        if existing is None:
            conn.execute(
                text("""
                    INSERT INTO trust_overdue_followups (
                        trust_product_id, trust_asset_id, data_date,
                        trigger_source, status, risk_score, risk_level,
                        case_priority, alert_source, sla_due_date, sla_status
                    ) VALUES (
                        :trust_product_id, :trust_asset_id, :data_date,
                        'system', 'open', :risk_score, :risk_level,
                        :case_priority, 'system',
                        NOW() + CAST(:sla_interval AS INTERVAL),
                        'on_time'
                    )
                """),
                {
                    "trust_product_id": row.trust_product_id,
                    "trust_asset_id": row.trust_asset_id,
                    "data_date": row.data_date,
                    "risk_score": row.risk_score,
                    "risk_level": row.risk_level,
                    "case_priority": priority,
                    "sla_interval": sla_interval,
                },
            )
            created += 1
        else:
            conn.execute(
                text("""
                    UPDATE trust_overdue_followups SET
                        risk_score = :risk_score,
                        risk_level = :risk_level,
                        case_priority = :case_priority,
                        data_date = :data_date,
                        sla_due_date = COALESCE(sla_due_date, NOW() + CAST(:sla_interval AS INTERVAL))
                    WHERE id = :id
                """),
                {
                    "id": existing.id,
                    "risk_score": row.risk_score,
                    "risk_level": row.risk_level,
                    "case_priority": priority,
                    "data_date": row.data_date,
                    "sla_interval": sla_interval,
                },
            )
            updated += 1

    _refresh_case_sla_statuses(conn, trust_product_id)
    return {"created": created, "updated": updated}


def _refresh_case_sla_statuses(conn, trust_product_id: int | None = None):
    sql = """
        SELECT id, sla_due_date, status, created_at
        FROM trust_overdue_followups
        WHERE sla_due_date IS NOT NULL
    """
    params: dict = {}
    if trust_product_id is not None:
        sql += " AND trust_product_id = :trust_product_id"
        params["trust_product_id"] = trust_product_id

    for row in conn.execute(text(sql), params):
        sla_status = compute_sla_status(row.sla_due_date, row.status, row.created_at)
        conn.execute(
            text("UPDATE trust_overdue_followups SET sla_status = :sla_status WHERE id = :id"),
            {"id": row.id, "sla_status": sla_status},
        )


def fetch_risk_workbench(conn, trust_product_id: int | None = None, trust_asset_id: int | None = None):
    monitor_filter, params = _latest_monitor_filter(trust_product_id, None)
    if "tolerance" not in params:
        params = {**params, "tolerance": RECONCILIATION_TOLERANCE}
    if "performing_max_days" not in params:
        params = {
            **params,
            "performing_max_days": PERFORMING_MAX_DAYS,
            "m2_min_days": M2_MIN_DAYS,
            "m2_max_days": M2_MAX_DAYS,
            "m3_min_days": M3_MIN_DAYS,
            "m3_max_days": M3_MAX_DAYS,
            "m3_plus_min_days": M3_PLUS_MIN_DAYS,
        }

    summary_row = conn.execute(
        text(f"""
            SELECT
                m.data_date,
                COUNT(*) AS total_assets,
                COUNT(*) FILTER (WHERE m.risk_level = 'A') AS level_a_count,
                COUNT(*) FILTER (WHERE m.risk_level = 'B') AS level_b_count,
                COUNT(*) FILTER (WHERE m.risk_level = 'C') AS level_c_count,
                COUNT(*) FILTER (WHERE m.risk_level = 'D') AS level_d_count,
                COUNT(*) AS exposure_count,
                COUNT(*) FILTER (WHERE m.remaining_amount <= :tolerance) AS es_count,
                COUNT(*) FILTER (
                    WHERE m.remaining_amount > :tolerance
                      AND COALESCE(m.overdue_days, 0) <= :performing_max_days
                ) AS m1_count,
                COUNT(*) FILTER (
                    WHERE m.remaining_amount > :tolerance
                      AND COALESCE(m.overdue_days, 0) BETWEEN :m2_min_days AND :m2_max_days
                ) AS m2_count,
                COUNT(*) FILTER (
                    WHERE m.remaining_amount > :tolerance
                      AND COALESCE(m.overdue_days, 0) BETWEEN :m3_min_days AND :m3_max_days
                ) AS m3_count,
                COUNT(*) FILTER (
                    WHERE m.remaining_amount > :tolerance
                      AND COALESCE(m.overdue_days, 0) >= :m3_plus_min_days
                ) AS m3_plus_count,
                ROUND(
                    AVG(m.risk_score) FILTER (WHERE m.remaining_amount > :tolerance)::numeric,
                    1
                ) AS avg_risk_score
            FROM trust_asset_monitor_records m
            WHERE {monitor_filter}
            GROUP BY m.data_date
        """),
        params,
    ).fetchone()

    alert_open = conn.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM risk_alerts
            WHERE status IN ('open', 'acknowledged')
        """)
    ).fetchone()

    sla_breached = conn.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM trust_overdue_followups
            WHERE sla_status IN ('overdue', 'breached')
              AND status IN ('open', 'in_progress')
        """)
    ).fetchone()

    queue_rows = conn.execute(
        text(f"""
            SELECT
                m.trust_asset_id,
                ta.asset_code,
                ta.custody_asset_code,
                ta.source_asset_code,
                ta.asset_name,
                m.trust_product_id,
                tp.name AS trust_product_name,
                m.risk_score,
                m.risk_level,
                m.overdue_days,
                COALESCE(m.overdue_days, 0) AS overdue_days_safe,
                m.remaining_amount,
                m.last_payment_date,
                m.max_payment_date,
                m.data_date,
                f.id AS case_id,
                f.status AS case_status,
                f.sla_status,
                f.case_priority,
                (
                    SELECT COUNT(*) FROM risk_alerts ra
                    WHERE ra.trust_asset_id = m.trust_asset_id
                      AND ra.data_date = m.data_date
                      AND ra.status IN ('open', 'acknowledged')
                ) AS alert_count
            FROM trust_asset_monitor_records m
            INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
            INNER JOIN trust_products tp ON tp.id = m.trust_product_id
            LEFT JOIN trust_overdue_followups f
                ON f.trust_asset_id = m.trust_asset_id
               AND f.status IN ('open', 'in_progress')
            WHERE {monitor_filter}
            ORDER BY m.risk_score DESC NULLS LAST,
                     COALESCE(m.overdue_days, 0) DESC,
                     ta.asset_code
        """),
        params,
    )

    queue = []
    for r in queue_rows:
        lifecycle = monitor_record_api_fields(r)
        queue.append({
            "trust_asset_id": r.trust_asset_id,
            "asset_code": r.asset_code,
            "custody_asset_code": r.custody_asset_code,
            "source_asset_code": r.source_asset_code,
            "asset_name": r.asset_name,
            "trust_product_id": r.trust_product_id,
            "trust_product_name": r.trust_product_name,
            "risk_score": int(r.risk_score) if r.risk_score is not None else None,
            "data_date": str(r.data_date),
            "case_id": r.case_id,
            "case_status": r.case_status,
            "sla_status": r.sla_status,
            "case_priority": r.case_priority,
            "alert_count": int(r.alert_count),
            **lifecycle,
        })

    selected_id = trust_asset_id
    if selected_id is None and queue:
        selected_id = queue[0]["trust_asset_id"]

    detail = None
    if selected_id is not None:
        detail = fetch_risk_asset_detail(conn, selected_id)

    es = int(summary_row.es_count) if summary_row else 0
    m1 = int(summary_row.m1_count) if summary_row else 0
    m2 = int(summary_row.m2_count) if summary_row else 0
    m3 = int(summary_row.m3_count) if summary_row else 0
    m3_plus = int(summary_row.m3_plus_count) if summary_row else 0
    exposure_total = es + m1 + m2 + m3 + m3_plus
    overdue_total = m2 + m3 + m3_plus

    return {
        "data_date": str(summary_row.data_date) if summary_row else None,
        "summary": {
            "total_assets": int(summary_row.total_assets) if summary_row else 0,
            "level_a_count": int(summary_row.level_a_count) if summary_row else 0,
            "level_b_count": int(summary_row.level_b_count) if summary_row else 0,
            "level_c_count": int(summary_row.level_c_count) if summary_row else 0,
            "level_d_count": int(summary_row.level_d_count) if summary_row else 0,
            "overdue_count": exposure_total,
            "overdue_count_deprecated": True,
            "es_count": es,
            "exposure_total": exposure_total,
            "overdue_total": overdue_total,
            "breakdown": {"ES": es, "M1": m1, "M2": m2, "M3": m3, "M3+": m3_plus},
            "avg_risk_score": float(summary_row.avg_risk_score) if summary_row and summary_row.avg_risk_score else 0,
            "open_alert_count": int(alert_open.cnt) if alert_open else 0,
            "sla_breached_count": int(sla_breached.cnt) if sla_breached else 0,
        },
        "queue": queue,
        "selected_asset_id": selected_id,
        "detail": detail,
    }


def fetch_risk_assets(conn, trust_product_id: int | None = None, risk_level: str | None = None):
    monitor_filter, params = _latest_monitor_filter(trust_product_id, None)
    sql = f"""
        SELECT
            m.trust_asset_id,
            ta.asset_code,
            ta.asset_name,
            m.trust_product_id,
            tp.name AS trust_product_name,
            m.data_date,
            m.overdue_days,
            COALESCE(m.overdue_days, 0) AS overdue_days_safe,
            m.risk_score,
            m.risk_level,
            m.repaid_amount,
            m.remaining_amount,
            m.last_payment_date,
            m.max_payment_date,
            f.sla_status,
            f.case_priority
        FROM trust_asset_monitor_records m
        INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
        INNER JOIN trust_products tp ON tp.id = m.trust_product_id
        LEFT JOIN trust_overdue_followups f
            ON f.trust_asset_id = m.trust_asset_id AND f.status IN ('open', 'in_progress')
        WHERE {monitor_filter}
    """
    if risk_level:
        sql += " AND m.risk_level = :risk_level"
        params["risk_level"] = risk_level
    sql += " ORDER BY m.risk_score DESC NULLS LAST, ta.asset_code"

    items = []
    data_date = None
    for row in conn.execute(text(sql), params):
        data_date = str(row.data_date)
        lifecycle = monitor_record_api_fields(row)
        items.append({
            "trust_asset_id": row.trust_asset_id,
            "asset_code": row.asset_code,
            "asset_name": row.asset_name,
            "trust_product_id": row.trust_product_id,
            "trust_product_name": row.trust_product_name,
            "data_date": data_date,
            "risk_score": int(row.risk_score) if row.risk_score is not None else None,
            "repaid_amount": float(row.repaid_amount),
            "sla_status": row.sla_status,
            "case_priority": row.case_priority,
            **lifecycle,
        })

    return {"data_date": data_date, "items": items}


def _risk_triggers_for_asset(conn, trust_asset_id: int, data_date: str) -> list:
    rows = conn.execute(
        text("""
            WITH m AS (
                SELECT * FROM trust_asset_monitor_records
                WHERE trust_asset_id = :trust_asset_id AND data_date = :data_date
            ),
            rs AS (
                SELECT COALESCE(SUM(actual_repayment_amount), 0) AS total_repaid
                FROM trust_repayment_detail_records
                WHERE trust_asset_id = :trust_asset_id AND data_date = :data_date
            )
            SELECT
                m.overdue_days,
                m.remaining_amount,
                m.last_payment_date,
                m.max_payment_date,
                m.risk_score,
                m.risk_level,
                ABS((m.initial_transfer_amount - m.repaid_amount) - m.remaining_amount) AS balance_diff,
                ABS(m.repaid_amount - rs.total_repaid) AS cross_diff
            FROM m, rs
        """),
        {"trust_asset_id": trust_asset_id, "data_date": data_date},
    ).fetchone()

    if rows is None:
        return []

    if is_es_closed(float(rows.remaining_amount)):
        return []

    od = 0 if rows.overdue_days is None else int(rows.overdue_days)
    triggers = []
    if od > 0:
        triggers.append(f"逾期 {od} 天")
    if float(rows.balance_diff) > RECONCILIATION_TOLERANCE:
        triggers.append("余额等式不一致")
    if float(rows.cross_diff) > RECONCILIATION_TOLERANCE:
        triggers.append("跨表已还金额不一致")
    if rows.last_payment_date and rows.max_payment_date and is_payment_gap_risk(od):
        triggers.append("回款中断 / 波动偏高")
    if rows.risk_score and int(rows.risk_score) >= 80:
        triggers.append("综合风险评分 ≥ 80")
    return triggers


def fetch_risk_asset_detail(conn, trust_asset_id: int):
    row = conn.execute(
        text("""
            SELECT
                m.trust_asset_id,
                ta.asset_code,
                ta.custody_asset_code,
                ta.source_asset_code,
                ta.asset_name,
                m.trust_product_id,
                tp.name AS trust_product_name,
                m.data_date,
                m.overdue_days,
                m.risk_score,
                m.risk_level,
                m.initial_transfer_amount,
                m.repaid_amount,
                m.remaining_amount,
                m.last_payment_date,
                m.max_payment_date,
                m.source_file_name,
                m.source_sheet_name
            FROM trust_asset_monitor_records m
            INNER JOIN trust_assets ta ON ta.id = m.trust_asset_id
            INNER JOIN trust_products tp ON tp.id = m.trust_product_id
            WHERE m.trust_asset_id = :trust_asset_id
            ORDER BY m.data_date DESC
            LIMIT 1
        """),
        {"trust_asset_id": trust_asset_id},
    ).fetchone()

    if row is None:
        return None

    data_date = str(row.data_date)
    triggers = _risk_triggers_for_asset(conn, trust_asset_id, data_date)

    alerts = fetch_risk_alerts(conn, trust_asset_id=trust_asset_id, data_date=data_date)
    cases = fetch_risk_cases(conn, trust_asset_id=trust_asset_id)

    score_breakdown = conn.execute(
        text(f"""
            WITH m AS (
                SELECT * FROM trust_asset_monitor_records
                WHERE trust_asset_id = :trust_asset_id AND data_date = :data_date
            ),
            rs AS (
                SELECT COALESCE(SUM(actual_repayment_amount), 0) AS total_repaid
                FROM trust_repayment_detail_records
                WHERE trust_asset_id = :trust_asset_id AND data_date = :data_date
            )
            SELECT
                m.remaining_amount,
                {sql_risk_score_overdue_component()} AS overdue_component,
                CASE
                    WHEN m.remaining_amount <= :tolerance THEN 0
                    WHEN ABS((m.initial_transfer_amount - m.repaid_amount) - m.remaining_amount) > :tolerance
                      OR ABS(m.repaid_amount - rs.total_repaid) > :tolerance THEN 30
                    ELSE 0
                END AS reconciliation_component,
                {sql_risk_payment_gap_component()} AS volatility_component
            FROM m, rs
        """),
        {"trust_asset_id": trust_asset_id, "data_date": data_date, "tolerance": RECONCILIATION_TOLERANCE},
    ).fetchone()

    active_case = next((c for c in cases if c["status"] in ("open", "in_progress")), None)
    lifecycle = monitor_record_api_fields(row)

    return {
        "trust_asset_id": row.trust_asset_id,
        "asset_code": row.asset_code,
        "custody_asset_code": row.custody_asset_code,
        "source_asset_code": row.source_asset_code,
        "asset_name": row.asset_name,
        "trust_product_id": row.trust_product_id,
        "trust_product_name": row.trust_product_name,
        "data_date": data_date,
        "risk_score": int(row.risk_score) if row.risk_score is not None else None,
        "initial_transfer_amount": float(row.initial_transfer_amount),
        "repaid_amount": float(row.repaid_amount),
        "max_payment_date": str(row.max_payment_date) if row.max_payment_date else None,
        "source_file_name": row.source_file_name,
        "source_sheet_name": row.source_sheet_name,
        "risk_triggers": triggers,
        "score_breakdown": {
            "overdue_weight": int(score_breakdown.overdue_component) if score_breakdown else 0,
            "reconciliation_weight": int(score_breakdown.reconciliation_component) if score_breakdown else 0,
            "volatility_weight": int(score_breakdown.volatility_component) if score_breakdown else 0,
        },
        "alerts": alerts,
        "case": active_case,
        "cases": cases,
        **lifecycle,
    }


def fetch_risk_alerts(
    conn,
    trust_product_id: int | None = None,
    trust_asset_id: int | None = None,
    data_date: str | None = None,
    status: str | None = None,
):
    sql = """
        SELECT
            a.id, a.trust_product_id, tp.name AS trust_product_name,
            a.trust_asset_id, ta.asset_code, ta.asset_name,
            a.data_date, a.risk_type, a.risk_level, a.trigger_rule,
            a.status, a.generated_at, a.resolved_at
        FROM risk_alerts a
        INNER JOIN trust_assets ta ON ta.id = a.trust_asset_id
        INNER JOIN trust_products tp ON tp.id = a.trust_product_id
        WHERE 1=1
    """
    params: dict = {}
    if trust_product_id is not None:
        sql += " AND a.trust_product_id = :trust_product_id"
        params["trust_product_id"] = trust_product_id
    if trust_asset_id is not None:
        sql += " AND a.trust_asset_id = :trust_asset_id"
        params["trust_asset_id"] = trust_asset_id
    if data_date is not None:
        sql += " AND a.data_date = :data_date"
        params["data_date"] = data_date
    if status is not None:
        sql += " AND a.status = :status"
        params["status"] = status
    sql += " ORDER BY a.generated_at DESC, a.id DESC"

    items = []
    for row in conn.execute(text(sql), params):
        items.append({
            "id": row.id,
            "trust_product_id": row.trust_product_id,
            "trust_product_name": row.trust_product_name,
            "trust_asset_id": row.trust_asset_id,
            "asset_code": row.asset_code,
            "asset_name": row.asset_name,
            "data_date": str(row.data_date),
            "risk_type": row.risk_type,
            "risk_level": row.risk_level,
            "trigger_rule": row.trigger_rule,
            "status": row.status,
            "generated_at": str(row.generated_at),
            "resolved_at": str(row.resolved_at) if row.resolved_at else None,
        })
    return items


def patch_risk_alert(conn, alert_id: int, fields: dict):
    row = conn.execute(
        text("SELECT id, status FROM risk_alerts WHERE id = :id"),
        {"id": alert_id},
    ).fetchone()
    if row is None:
        return None

    new_status = fields.get("status", row.status)
    resolved_at = fields.get("resolved_at")
    if new_status in ("resolved", "ignored") and resolved_at is None:
        resolved_at = "NOW()"

    if resolved_at == "NOW()":
        conn.execute(
            text("""
                UPDATE risk_alerts SET status = :status, resolved_at = NOW()
                WHERE id = :id
            """),
            {"id": alert_id, "status": new_status},
        )
    else:
        conn.execute(
            text("UPDATE risk_alerts SET status = :status WHERE id = :id"),
            {"id": alert_id, "status": new_status},
        )
    conn.commit()
    alerts = fetch_risk_alerts(conn)
    return next((a for a in alerts if a["id"] == alert_id), None)


def fetch_risk_cases(
    conn,
    trust_product_id: int | None = None,
    trust_asset_id: int | None = None,
    status: str | None = None,
):
    sql = """
        SELECT
            f.id, f.trust_product_id, tp.name AS trust_product_name,
            f.trust_asset_id, ta.asset_code, ta.asset_name,
            f.data_date, f.trigger_source, f.alert_source,
            f.overdue_reason, f.follow_up_plan, f.status,
            f.owner_name, f.last_follow_up_at, f.trust_feedback,
            f.risk_score, f.risk_level, f.sla_due_date, f.sla_status,
            f.case_priority, f.next_action_date,
            f.created_at, f.updated_at
        FROM trust_overdue_followups f
        INNER JOIN trust_assets ta ON ta.id = f.trust_asset_id
        INNER JOIN trust_products tp ON tp.id = f.trust_product_id
        WHERE 1=1
    """
    params: dict = {}
    if trust_product_id is not None:
        sql += " AND f.trust_product_id = :trust_product_id"
        params["trust_product_id"] = trust_product_id
    if trust_asset_id is not None:
        sql += " AND f.trust_asset_id = :trust_asset_id"
        params["trust_asset_id"] = trust_asset_id
    if status is not None:
        sql += " AND f.status = :status"
        params["status"] = status
    sql += " ORDER BY f.case_priority NULLS LAST, f.last_follow_up_at DESC NULLS LAST, f.id DESC"

    items = []
    for row in conn.execute(text(sql), params):
        sla_status = row.sla_status
        if row.sla_due_date:
            sla_status = compute_sla_status(row.sla_due_date, row.status, row.created_at)
        items.append({
            "id": row.id,
            "trust_product_id": row.trust_product_id,
            "trust_product_name": row.trust_product_name,
            "trust_asset_id": row.trust_asset_id,
            "asset_code": row.asset_code,
            "asset_name": row.asset_name,
            "data_date": str(row.data_date),
            "trigger_source": row.trigger_source,
            "alert_source": row.alert_source,
            "overdue_reason": row.overdue_reason,
            "follow_up_plan": row.follow_up_plan,
            "status": row.status,
            "owner_name": row.owner_name,
            "last_follow_up_at": str(row.last_follow_up_at) if row.last_follow_up_at else None,
            "trust_feedback": row.trust_feedback,
            "risk_score": int(row.risk_score) if row.risk_score is not None else None,
            "risk_level": row.risk_level,
            "sla_due_date": str(row.sla_due_date) if row.sla_due_date else None,
            "sla_status": sla_status,
            "case_priority": row.case_priority,
            "next_action_date": str(row.next_action_date) if row.next_action_date else None,
            "created_at": str(row.created_at),
            "updated_at": str(row.updated_at),
        })
    return items


def create_risk_case(conn, payload: dict) -> dict:
    asset_row = conn.execute(
        text("""
            SELECT m.trust_product_id, m.data_date, m.risk_score, m.risk_level, m.overdue_days
            FROM trust_asset_monitor_records m
            WHERE m.trust_asset_id = :trust_asset_id
            ORDER BY m.data_date DESC LIMIT 1
        """),
        {"trust_asset_id": payload["trust_asset_id"]},
    ).fetchone()
    if asset_row is None:
        return None

    risk_level = payload.get("risk_level") or asset_row.risk_level or "C"
    risk_score = payload.get("risk_score") or asset_row.risk_score or 40
    priority = CASE_PRIORITY_MAP.get(risk_level, "P2")
    sla_interval = {"A": "1 day", "B": "3 days", "C": "7 days"}.get(risk_level, "7 days")

    result = conn.execute(
        text("""
            INSERT INTO trust_overdue_followups (
                trust_product_id, trust_asset_id, data_date,
                trigger_source, alert_source, overdue_reason, follow_up_plan,
                status, owner_name, trust_feedback,
                risk_score, risk_level, case_priority,
                sla_due_date, sla_status, next_action_date
            ) VALUES (
                :trust_product_id, :trust_asset_id, :data_date,
                :trigger_source, :alert_source, :overdue_reason, :follow_up_plan,
                :status, :owner_name, :trust_feedback,
                :risk_score, :risk_level, :case_priority,
                NOW() + CAST(:sla_interval AS INTERVAL), 'on_time', :next_action_date
            )
            RETURNING id
        """),
        {
            "trust_product_id": asset_row.trust_product_id,
            "trust_asset_id": payload["trust_asset_id"],
            "data_date": str(asset_row.data_date),
            "trigger_source": payload.get("trigger_source", "trust"),
            "alert_source": payload.get("alert_source", "manual"),
            "overdue_reason": payload.get("overdue_reason"),
            "follow_up_plan": payload.get("follow_up_plan"),
            "status": payload.get("status", "open"),
            "owner_name": payload.get("owner_name"),
            "trust_feedback": payload.get("trust_feedback"),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "case_priority": priority,
            "sla_interval": sla_interval,
            "next_action_date": payload.get("next_action_date"),
        },
    )
    case_id = result.fetchone().id
    conn.commit()
    cases = fetch_risk_cases(conn, trust_asset_id=payload["trust_asset_id"])
    return next((c for c in cases if c["id"] == case_id), None)


def patch_risk_case(conn, case_id: int, fields: dict) -> dict | None:
    row = conn.execute(
        text("SELECT id FROM trust_overdue_followups WHERE id = :id"),
        {"id": case_id},
    ).fetchone()
    if row is None:
        return None

    allowed = (
        "overdue_reason", "follow_up_plan", "status", "owner_name",
        "last_follow_up_at", "trust_feedback", "next_action_date",
        "risk_level", "case_priority",
    )
    sets = []
    params: dict = {"id": case_id}
    for key in allowed:
        if key in fields:
            sets.append(f"{key} = :{key}")
            params[key] = fields[key]

    if "risk_level" in fields:
        rl = fields["risk_level"]
        sla_interval = {"A": "1 day", "B": "3 days", "C": "7 days"}.get(rl)
        if sla_interval:
            sets.append("sla_due_date = NOW() + CAST(:sla_interval AS INTERVAL)")
            params["sla_interval"] = sla_interval
        sets.append("case_priority = :case_priority")
        params["case_priority"] = CASE_PRIORITY_MAP.get(rl, "P2")

    if not sets:
        cases = fetch_risk_cases(conn)
        return next((c for c in cases if c["id"] == case_id), None)

    conn.execute(
        text(f"UPDATE trust_overdue_followups SET {', '.join(sets)} WHERE id = :id"),
        params,
    )
    _refresh_case_sla_statuses(conn)
    conn.commit()
    cases = fetch_risk_cases(conn)
    return next((c for c in cases if c["id"] == case_id), None)
