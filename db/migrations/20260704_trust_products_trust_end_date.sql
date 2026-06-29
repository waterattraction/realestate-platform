-- 信托产品主数据 V1 Lite：信托结束日期
-- trust_end_date：可选 DATE，管理端录入

ALTER TABLE trust_products
ADD COLUMN IF NOT EXISTS trust_end_date DATE;
