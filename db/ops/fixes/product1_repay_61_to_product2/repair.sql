-- 61 笔还款误挂在美好生活1号 (trust_product_id=1)，应属美好生活2号 (id=2)
-- 依据：excel文件/repay_asset_code_not_in_issuance_product1.csv

BEGIN;

CREATE TEMP TABLE _repair_asset_codes (asset_code VARCHAR(64) PRIMARY KEY) ON COMMIT DROP;

INSERT INTO _repair_asset_codes (asset_code) VALUES
    ('101127783856'), ('101128478335'), ('101128726646'), ('101130675302'), ('101131087180'),
    ('101131125096'), ('101131142921'), ('101131349350'), ('101131367081'), ('101131451551'),
    ('101131459050'), ('101132542218'), ('107106277578'), ('107112133348'), ('107112596941'),
    ('107112644751'), ('107112671893'), ('107112807360'), ('107112816726'), ('107112817776'),
    ('107112879720'), ('107112911956'), ('107112922865'), ('107112933847'), ('107112969764'),
    ('107113109822'), ('107113115957'), ('107113118457'), ('107113123463'), ('107113137962'),
    ('107113154700'), ('107113166110'), ('107113176082'), ('107113176120'), ('107113190147'),
    ('107113192257'), ('107113248283'), ('107113264309'), ('107113268763'), ('107113269783'),
    ('107113274815'), ('107113286656'), ('107113314832'), ('107113323285'), ('107113339249'),
    ('107113349156'), ('107113358211'), ('107113393932'), ('107113395543'), ('107113400065'),
    ('107113409032'), ('107113409067'), ('107113440441'), ('107113446879'), ('107113459477'),
    ('107113460237'), ('107113463609'), ('107113466592'), ('107113483637'), ('107113648070'),
    ('107114866922');

-- 107114866922 在 product2 无 trust_assets，先补建
INSERT INTO trust_assets (
    trust_product_id, asset_code, custody_asset_code, source_asset_code, initial_transfer_amount
)
SELECT 2, c.asset_code, c.asset_code, c.asset_code, 0
FROM _repair_asset_codes c
WHERE c.asset_code = '107114866922'
  AND NOT EXISTS (
      SELECT 1 FROM trust_assets ta
      WHERE ta.trust_product_id = 2 AND ta.asset_code = c.asset_code
  );

UPDATE trust_repayment_detail_records r
SET
    trust_product_id = 2,
    trust_asset_id = ta2.id
FROM _repair_asset_codes c
JOIN trust_assets ta2
  ON ta2.trust_product_id = 2 AND ta2.asset_code = c.asset_code
WHERE r.trust_product_id = 1
  AND r.asset_code = c.asset_code;

-- 删除 product1 下因误导入产生的孤立 trust_assets（60 个 asset_code 对齐的）
DELETE FROM trust_assets ta
USING _repair_asset_codes c
WHERE ta.trust_product_id = 1
  AND ta.asset_code = c.asset_code
  AND c.asset_code <> '107114866922'
  AND NOT EXISTS (
      SELECT 1 FROM trust_repayment_detail_records r WHERE r.trust_asset_id = ta.id
  )
  AND NOT EXISTS (
      SELECT 1 FROM trust_asset_monitor_records m WHERE m.trust_asset_id = ta.id
  );

COMMIT;
