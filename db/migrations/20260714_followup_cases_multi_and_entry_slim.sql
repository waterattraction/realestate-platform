-- type: migration
-- created_at: 2026-07-14
-- author: ops
-- purpose: 多跟进事项 + entries 精简列 + 信托标记简化 + internal_status 派生回填
-- dependencies: 20260628_overdue_asset_code_aggregate.sql
-- idempotent: partial

-- 1) 允许多个活跃事项
DROP INDEX IF EXISTS uq_followup_cases_active_asset;
DROP INDEX IF EXISTS uq_followup_cases_active_custody;

-- 2) cases 增加分类 / 描述
ALTER TABLE trust_overdue_followup_cases
    ADD COLUMN IF NOT EXISTS category VARCHAR(64),
    ADD COLUMN IF NOT EXISTS description TEXT;

UPDATE trust_overdue_followup_cases
SET category = COALESCE(NULLIF(TRIM(category), ''), '轻度逾期')
WHERE category IS NULL OR TRIM(category) = '';

ALTER TABLE trust_overdue_followup_cases
    ALTER COLUMN category SET DEFAULT '轻度逾期';

ALTER TABLE trust_overdue_followup_cases
    DROP CONSTRAINT IF EXISTS chk_followup_cases_category;

ALTER TABLE trust_overdue_followup_cases
    ADD CONSTRAINT chk_followup_cases_category
    CHECK (category IN ('轻度逾期', '重度逾期', '回购', '置换', '潜在风险'));

-- 默认待跟进（open）；展示文案改为「待跟进」
ALTER TABLE trust_overdue_followup_cases
    ALTER COLUMN status SET DEFAULT 'open';

-- 3) entries 删除废弃列（含历史数据）
ALTER TABLE trust_overdue_followup_entries
    DROP COLUMN IF EXISTS status_snapshot,
    DROP COLUMN IF EXISTS trust_feedback,
    DROP COLUMN IF EXISTS note;

-- 4) 信托标记简化并迁移历史值
UPDATE trust_asset_trust_marks
SET trust_marker = CASE
    WHEN trust_marker IN ('信托已关注', '已关注') THEN '已关注'
    WHEN trust_marker IN ('信托要求跟进', '重点关注') THEN '重点关注'
    ELSE '无标记'
END;

ALTER TABLE trust_asset_trust_marks
    ALTER COLUMN trust_marker SET DEFAULT '无标记';

-- 5) 按活跃 cases 重算 internal_status：正常 | 待跟进(N)
UPDATE trust_asset_trust_marks m
SET internal_status = COALESCE(
    (
        SELECT CASE
            WHEN COUNT(*) FILTER (
                WHERE c.status IN ('open', 'in_progress')
            ) = 0 THEN '正常'
            ELSE '待跟进(' || COUNT(*) FILTER (
                WHERE c.status IN ('open', 'in_progress')
            )::text || ')'
        END
        FROM trust_overdue_followup_cases c
        WHERE c.trust_product_id = m.trust_product_id
          AND c.asset_code = m.asset_code
    ),
    '正常'
);

CREATE INDEX IF NOT EXISTS idx_followup_cases_product_asset_status
    ON trust_overdue_followup_cases (trust_product_id, asset_code, status);
