-- ============================================================
-- 信托产品别名表 — trust_product_aliases
-- 执行顺序：… → issuance_schema.sql → 本文件
-- ============================================================

CREATE TABLE IF NOT EXISTS trust_product_aliases (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trust_product_id    BIGINT NOT NULL REFERENCES trust_products (id),
    alias_name          VARCHAR(200) NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_trust_product_aliases_alias_name UNIQUE (alias_name)
);

CREATE INDEX IF NOT EXISTS idx_trust_product_aliases_product
    ON trust_product_aliases (trust_product_id);

-- 美好生活3号发行底表：「当前信托计划（已发行）」= 单一信托 → 美润1号
INSERT INTO trust_product_aliases (trust_product_id, alias_name)
SELECT id, '单一信托'
FROM trust_products
WHERE name = '美润1号'
ON CONFLICT (alias_name) DO NOTHING;
