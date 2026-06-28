-- type: ops/cleanup
-- status: executed
-- safe_to_rerun: no
-- scope: baseline demo — projects / investors / investments（保留 asset_pools id=1 与 trust_products）
-- ============================================================

BEGIN;

SELECT '=== 删除前 ===' AS section;
SELECT 'projects' AS metric, COUNT(*) AS cnt FROM projects
UNION ALL SELECT 'project_asset_pools', COUNT(*) FROM project_asset_pools
UNION ALL SELECT 'investors', COUNT(*) FROM investors
UNION ALL SELECT 'investments', COUNT(*) FROM investments;

DROP TABLE IF EXISTS _demo_baseline_backup_project_asset_pools;
DROP TABLE IF EXISTS _demo_baseline_backup_projects;
DROP TABLE IF EXISTS _demo_baseline_backup_investments;
DROP TABLE IF EXISTS _demo_baseline_backup_investors;

CREATE TABLE _demo_baseline_backup_projects AS
SELECT * FROM projects WHERE code LIKE 'PRJ-2026-%';

CREATE TABLE _demo_baseline_backup_project_asset_pools AS
SELECT pap.*
FROM project_asset_pools pap
JOIN projects p ON p.id = pap.project_id
WHERE p.code LIKE 'PRJ-2026-%';

CREATE TABLE _demo_baseline_backup_investments AS
SELECT * FROM investments
WHERE subscription_no IN ('SUB-2026-00000001', 'SUB-2026-00000002');

CREATE TABLE _demo_baseline_backup_investors AS
SELECT * FROM investors
WHERE code IN ('INV-2026-00001', 'INV-2026-00002');

DELETE FROM project_asset_pools
WHERE project_id IN (SELECT id FROM projects WHERE code LIKE 'PRJ-2026-%');

DELETE FROM projects WHERE code LIKE 'PRJ-2026-%';

DELETE FROM investments
WHERE subscription_no IN ('SUB-2026-00000001', 'SUB-2026-00000002');

DELETE FROM investors
WHERE code IN ('INV-2026-00001', 'INV-2026-00002');

UPDATE trust_products
SET raised_amount = 0, updated_at = NOW()
WHERE id = 1;

SELECT '=== 删除后 ===' AS section;
SELECT 'projects' AS metric, COUNT(*) AS cnt FROM projects
UNION ALL SELECT 'project_asset_pools', COUNT(*) FROM project_asset_pools
UNION ALL SELECT 'investors', COUNT(*) FROM investors
UNION ALL SELECT 'investments', COUNT(*) FROM investments
UNION ALL SELECT 'trust_products', COUNT(*) FROM trust_products
UNION ALL SELECT 'trust_assets', COUNT(*) FROM trust_assets
UNION ALL SELECT 'trust_asset_monitor_records', COUNT(*) FROM trust_asset_monitor_records
UNION ALL SELECT 'trust_repayment_detail_records', COUNT(*) FROM trust_repayment_detail_records
UNION ALL SELECT 'trust_product_issuance_asset_records', COUNT(*) FROM trust_product_issuance_asset_records;

SELECT id, code, name, raised_amount FROM trust_products ORDER BY id;

COMMIT;
