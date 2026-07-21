"""Monitor overdue_days recalculation (repayment + manual settlement aware)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.assetinfo_pipeline import RECONCILIATION_TOLERANCE


def recompute_monitor_overdue_for_scope(
    conn: Connection,
    *,
    trust_product_id: int,
    data_date: date,
    as_of: date,
    tolerance: float = RECONCILIATION_TOLERANCE,
) -> dict[str, Any]:
    """按 as_of 重算指定产品某一监控快照层的 overdue_days / last_payment_date。

    手工结算（``voided_at IS NULL`` 且 ``settlement_date <= as_of``）：
    - 有效剩余 = max(0, remaining − Σ结算)；≤容差则逾期置空
    - 锚点 = MAX(导入还款最大还款日, 结算最大结算日)；仅有结算也算「有还款」
    - 不写回 remaining_amount / repaid_amount
    """
    params = {
        "trust_product_id": int(trust_product_id),
        "data_date": data_date,
        "as_of": as_of,
        "tolerance": float(tolerance),
    }
    scope_sql = (
        "m.trust_product_id = :trust_product_id AND m.data_date = :data_date"
    )

    # 1) 有导入还款和/或手工结算：锚点取二者最大日
    with_repayment = conn.execute(
        text(
            """
            UPDATE trust_asset_monitor_records m
            SET
                last_payment_date = anchors.anchor_date,
                max_payment_date = anchors.anchor_date,
                overdue_days = CASE
                    WHEN GREATEST(
                        0::numeric,
                        COALESCE(m.remaining_amount, 0) - anchors.settlement_sum
                    ) <= :tolerance THEN NULL
                    ELSE (
                        CAST(:as_of AS date)
                        - (anchors.anchor_date + INTERVAL '1 month')::date
                    )
                END,
                overdue_days_as_of = :as_of,
                updated_at = NOW()
            FROM (
                SELECT
                    m2.id AS monitor_id,
                    (
                        SELECT MAX(d)
                        FROM (VALUES (rp.max_rd), (ms.max_sd)) AS t(d)
                    ) AS anchor_date,
                    COALESCE(ms.settlement_sum, 0) AS settlement_sum
                FROM trust_asset_monitor_records m2
                LEFT JOIN (
                    SELECT
                        ta.asset_code,
                        MAX(r.repayment_date) AS max_rd
                    FROM trust_repayment_detail_records r
                    INNER JOIN trust_assets ta ON ta.id = r.trust_asset_id
                    WHERE r.trust_product_id = :trust_product_id
                    GROUP BY ta.asset_code
                ) rp ON rp.asset_code = m2.asset_code
                LEFT JOIN (
                    SELECT
                        s.asset_code,
                        MAX(s.settlement_date) AS max_sd,
                        COALESCE(SUM(s.amount), 0) AS settlement_sum
                    FROM trust_asset_manual_settlements s
                    WHERE s.trust_product_id = :trust_product_id
                      AND s.voided_at IS NULL
                      AND s.settlement_date <= CAST(:as_of AS date)
                    GROUP BY s.asset_code
                ) ms ON ms.asset_code = m2.asset_code
                WHERE m2.trust_product_id = :trust_product_id
                  AND m2.data_date = :data_date
                  AND (rp.max_rd IS NOT NULL OR ms.max_sd IS NOT NULL)
            ) anchors
            WHERE m.id = anchors.monitor_id
              AND anchors.anchor_date IS NOT NULL
            """
        ),
        params,
    )

    # 2) 无导入还款且无（≤as_of）结算：按发行日（本分支无结算，有效剩余=事实剩余）
    without_repayment_from_issue = conn.execute(
        text(
            """
            UPDATE trust_asset_monitor_records m
            SET
                last_payment_date = NULL,
                max_payment_date = NULL,
                overdue_days = CASE
                    WHEN COALESCE(m.remaining_amount, 0) <= :tolerance THEN NULL
                    ELSE (
                        CAST(:as_of AS date)
                        - (iss.min_issue_date + INTERVAL '1 month')::date
                    )
                END,
                overdue_days_as_of = :as_of,
                updated_at = NOW()
            FROM (
                SELECT
                    m2.id AS monitor_id,
                    COALESCE(ip.min_issue_date, ia.min_issue_date) AS min_issue_date
                FROM trust_asset_monitor_records m2
                LEFT JOIN (
                    SELECT
                        i.trust_product_id,
                        regexp_replace(COALESCE(i.custody_asset_code, ''), '\\.0$', '')
                            AS custody_norm,
                        MIN(i.issue_date) AS min_issue_date
                    FROM trust_product_issuance_asset_records i
                    WHERE i.trust_product_id = :trust_product_id
                    GROUP BY i.trust_product_id, custody_norm
                ) ip
                  ON ip.trust_product_id = m2.trust_product_id
                 AND ip.custody_norm = regexp_replace(
                     COALESCE(m2.custody_asset_code, m2.asset_code, ''), '\\.0$', ''
                 )
                LEFT JOIN (
                    SELECT
                        regexp_replace(COALESCE(i.custody_asset_code, ''), '\\.0$', '')
                            AS custody_norm,
                        MIN(i.issue_date) AS min_issue_date
                    FROM trust_product_issuance_asset_records i
                    GROUP BY custody_norm
                ) ia
                  ON ia.custody_norm = regexp_replace(
                      COALESCE(m2.custody_asset_code, m2.asset_code, ''), '\\.0$', ''
                  )
                WHERE m2.trust_product_id = :trust_product_id
                  AND m2.data_date = :data_date
                  AND COALESCE(ip.min_issue_date, ia.min_issue_date) IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM trust_repayment_detail_records r
                      INNER JOIN trust_assets ta ON ta.id = r.trust_asset_id
                      WHERE r.trust_product_id = m2.trust_product_id
                        AND ta.asset_code = m2.asset_code
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM trust_asset_manual_settlements s
                      WHERE s.trust_product_id = m2.trust_product_id
                        AND s.asset_code = m2.asset_code
                        AND s.voided_at IS NULL
                        AND s.settlement_date <= CAST(:as_of AS date)
                  )
            ) iss
            WHERE m.id = iss.monitor_id
            """
        ),
        params,
    )

    # 3) 无还款、无结算、无发行日 → 置空
    missing_issuance = conn.execute(
        text(
            f"""
            UPDATE trust_asset_monitor_records m
            SET
                last_payment_date = NULL,
                max_payment_date = NULL,
                overdue_days = NULL,
                overdue_days_as_of = :as_of,
                updated_at = NOW()
            WHERE {scope_sql}
              AND NOT EXISTS (
                  SELECT 1
                  FROM trust_repayment_detail_records r
                  INNER JOIN trust_assets ta ON ta.id = r.trust_asset_id
                  WHERE r.trust_product_id = m.trust_product_id
                    AND ta.asset_code = m.asset_code
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM trust_asset_manual_settlements s
                  WHERE s.trust_product_id = m.trust_product_id
                    AND s.asset_code = m.asset_code
                    AND s.voided_at IS NULL
                    AND s.settlement_date <= CAST(:as_of AS date)
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM trust_product_issuance_asset_records i
                  WHERE regexp_replace(COALESCE(i.custody_asset_code, ''), '\\.0$', '')
                      = regexp_replace(
                          COALESCE(m.custody_asset_code, m.asset_code, ''), '\\.0$', ''
                      )
              )
            """
        ),
        params,
    )

    # 4) 有效剩余结清兜底（事实剩余或叠加结算后 ≤ 容差）
    conn.execute(
        text(
            """
            UPDATE trust_asset_monitor_records m
            SET
                overdue_days = NULL,
                overdue_days_as_of = :as_of,
                updated_at = NOW()
            FROM (
                SELECT
                    m2.id AS monitor_id,
                    COALESCE(ms.settlement_sum, 0) AS settlement_sum
                FROM trust_asset_monitor_records m2
                LEFT JOIN (
                    SELECT
                        s.asset_code,
                        COALESCE(SUM(s.amount), 0) AS settlement_sum
                    FROM trust_asset_manual_settlements s
                    WHERE s.trust_product_id = :trust_product_id
                      AND s.voided_at IS NULL
                      AND s.settlement_date <= CAST(:as_of AS date)
                    GROUP BY s.asset_code
                ) ms ON ms.asset_code = m2.asset_code
                WHERE m2.trust_product_id = :trust_product_id
                  AND m2.data_date = :data_date
            ) x
            WHERE m.id = x.monitor_id
              AND GREATEST(
                  0::numeric,
                  COALESCE(m.remaining_amount, 0) - x.settlement_sum
              ) <= :tolerance
              AND m.overdue_days IS NOT NULL
            """
        ),
        params,
    )

    return {
        "with_repayment_updated": int(with_repayment.rowcount or 0),
        "no_repayment_from_issue_count": int(without_repayment_from_issue.rowcount or 0),
        "missing_issuance_count": int(missing_issuance.rowcount or 0),
    }
