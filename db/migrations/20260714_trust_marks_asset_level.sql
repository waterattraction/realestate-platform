-- 信托标记 / 内部状态按资产主编号唯一，与监控 data_date 解绑

-- 每个 (trust_product_id, asset_code) 保留最新一行
DELETE FROM trust_asset_trust_marks tm
USING (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY trust_product_id, asset_code
               ORDER BY updated_at DESC NULLS LAST, data_date DESC NULLS LAST, id DESC
           ) AS rn
    FROM trust_asset_trust_marks
) ranked
WHERE tm.id = ranked.id
  AND ranked.rn > 1;

ALTER TABLE trust_asset_trust_marks
    DROP CONSTRAINT IF EXISTS uq_trust_asset_trust_marks;

ALTER TABLE trust_asset_trust_marks
    ADD CONSTRAINT uq_trust_asset_trust_marks
    UNIQUE (trust_product_id, asset_code);

DROP INDEX IF EXISTS idx_trust_asset_trust_marks_lookup;

CREATE INDEX IF NOT EXISTS idx_trust_asset_trust_marks_lookup
    ON trust_asset_trust_marks (trust_product_id, asset_code);
