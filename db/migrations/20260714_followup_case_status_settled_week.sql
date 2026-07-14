-- 跟进事项状态新增 settled_week（本周结算）；回写派生内部状态

ALTER TABLE trust_overdue_followup_cases
    DROP CONSTRAINT IF EXISTS chk_followup_cases_status;

ALTER TABLE trust_overdue_followup_cases
    ADD CONSTRAINT chk_followup_cases_status
    CHECK (status IN ('open', 'in_progress', 'settled_week', 'resolved', 'closed'));

-- 按事项状态重算 marks.internal_status（问题优先 > 本周结算 > 正常）
UPDATE trust_asset_trust_marks tm
SET
    internal_status = sub.label,
    updated_at = NOW()
FROM (
    SELECT
        trust_product_id,
        asset_code,
        CASE
            WHEN COUNT(*) FILTER (WHERE status IN ('open', 'in_progress')) > 0
                THEN '待跟进(' || COUNT(*) FILTER (WHERE status IN ('open', 'in_progress'))::text || ')'
            WHEN COUNT(*) FILTER (WHERE status = 'settled_week') > 0
                THEN '本周结算(' || COUNT(*) FILTER (WHERE status = 'settled_week')::text || ')'
            ELSE '正常'
        END AS label
    FROM trust_overdue_followup_cases
    GROUP BY trust_product_id, asset_code
) sub
WHERE tm.trust_product_id = sub.trust_product_id
  AND tm.asset_code = sub.asset_code;
