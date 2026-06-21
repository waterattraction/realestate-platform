-- ============================================================
-- 测试数据
-- 执行顺序：先运行 schema.sql，再运行本文件
-- ============================================================

BEGIN;

-- 1. 3 个装修项目
INSERT INTO projects (code, name, status, address, city, total_budget, planned_start_date, planned_end_date)
VALUES
    (
        'PRJ-2026-00001',
        '上海浦东滨江公寓 A 栋装修',
        'in_progress',
        '上海市浦东新区滨江大道 100 号 A 栋',
        '上海',
        3200000.00,
        '2026-01-10',
        '2026-06-30'
    ),
    (
        'PRJ-2026-00002',
        '上海浦东滨江公寓 B 栋装修',
        'in_progress',
        '上海市浦东新区滨江大道 100 号 B 栋',
        '上海',
        2800000.00,
        '2026-02-01',
        '2026-07-31'
    ),
    (
        'PRJ-2026-00003',
        '上海浦东滨江公寓地下车库改造',
        'completed',
        '上海市浦东新区滨江大道 100 号 地下一层',
        '上海',
        1500000.00,
        '2025-10-01',
        '2026-01-31'
    );

-- 2. 1 个资产包（组合上述 3 个项目）
INSERT INTO asset_pools (code, name, status, appraised_value)
VALUES (
    'AP-2026-00001',
    '滨江公寓组合资产包',
    'active',
    8500000.00
);

-- 3. 多对多关联：3 个项目 → 1 个资产包
INSERT INTO project_asset_pools (project_id, asset_pool_id)
VALUES
    (1, 1),
    (2, 1),
    (3, 1);

-- 4. 1 个信托产品
INSERT INTO trust_products (
    asset_pool_id, code, name, status,
    target_amount, raised_amount, expected_return_rate,
    open_date, close_date
)
VALUES (
    1,
    'TRU-2026-00001',
    '滨江公寓信托一期',
    'raising',
    5000000.00,
    0.00,
    0.0650,
    '2026-03-01',
    '2026-06-30'
);

-- 5. 2 个投资人
INSERT INTO investors (code, name, investor_type, kyc_status, phone, email)
VALUES
    ('INV-2026-00001', '张三',   'individual',      'approved', '13800000001', 'zhangsan@example.com'),
    ('INV-2026-00002', '明德资本', 'institutional', 'approved', '021-88888888', 'contact@mingde-cap.com');

-- 6. 2 条投资记录
INSERT INTO investments (investor_id, trust_product_id, subscription_no, amount, status, invested_at)
VALUES
    (1, 1, 'SUB-2026-00000001', 800000.00,  'confirmed', '2026-03-05 10:30:00+08'),
    (2, 1, 'SUB-2026-00000002', 1200000.00, 'confirmed', '2026-03-08 14:20:00+08');

-- 同步信托产品已募集金额
UPDATE trust_products
SET raised_amount = (
    SELECT COALESCE(SUM(amount), 0)
    FROM investments
    WHERE trust_product_id = 1
      AND status = 'confirmed'
)
WHERE id = 1;

COMMIT;
