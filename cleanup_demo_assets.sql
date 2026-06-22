-- ============================================================
-- FY-* 演示数据清理脚本
-- 来源：overdue_seed.sql / risk_v2_seed.sql（滨江公寓演示房源）
-- 原则：不 TRUNCATE；仅删除 asset_code LIKE 'FY-%' 关联数据
-- 执行前请阅读影响分析；建议在事务中执行并先完成备份
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- A. 删除前统计
-- ------------------------------------------------------------
SELECT '=== 删除前统计 ===' AS section;

SELECT 'trust_assets (FY-*)' AS metric, COUNT(*) AS cnt
FROM trust_assets WHERE asset_code LIKE 'FY-%';

SELECT 'trust_repayment_detail_records (FY-*)' AS metric, COUNT(*) AS cnt
FROM trust_repayment_detail_records r
JOIN trust_assets ta ON ta.id = r.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%';

SELECT 'trust_asset_monitor_records (FY-*)' AS metric, COUNT(*) AS cnt
FROM trust_asset_monitor_records m
JOIN trust_assets ta ON ta.id = m.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%';

SELECT 'trust_overdue_followups (FY-*)' AS metric, COUNT(*) AS cnt
FROM trust_overdue_followups f
JOIN trust_assets ta ON ta.id = f.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%';

SELECT 'risk_alerts (FY-*)' AS metric, COUNT(*) AS cnt
FROM risk_alerts a
JOIN trust_assets ta ON ta.id = a.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%';

-- risk_scores / risk_history 表当前不存在（统计固定为 0）
SELECT 'risk_scores (FY-*)' AS metric, 0 AS cnt
WHERE to_regclass('public.risk_scores') IS NULL;

SELECT 'risk_history (FY-*)' AS metric, 0 AS cnt
WHERE to_regclass('public.risk_history') IS NULL;

-- ------------------------------------------------------------
-- B. 备份（回滚用）— 重复执行会先 DROP 再重建
-- ------------------------------------------------------------
DROP TABLE IF EXISTS _demo_fy_backup_risk_alerts;
DROP TABLE IF EXISTS _demo_fy_backup_trust_overdue_followups;
DROP TABLE IF EXISTS _demo_fy_backup_trust_repayment_detail_records;
DROP TABLE IF EXISTS _demo_fy_backup_trust_asset_monitor_records;
DROP TABLE IF EXISTS _demo_fy_backup_trust_assets;

CREATE TABLE _demo_fy_backup_trust_assets AS
SELECT ta.*
FROM trust_assets ta
WHERE ta.asset_code LIKE 'FY-%';

CREATE TABLE _demo_fy_backup_trust_asset_monitor_records AS
SELECT m.*
FROM trust_asset_monitor_records m
JOIN trust_assets ta ON ta.id = m.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%';

CREATE TABLE _demo_fy_backup_trust_repayment_detail_records AS
SELECT r.*
FROM trust_repayment_detail_records r
JOIN trust_assets ta ON ta.id = r.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%';

CREATE TABLE _demo_fy_backup_trust_overdue_followups AS
SELECT f.*
FROM trust_overdue_followups f
JOIN trust_assets ta ON ta.id = f.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%';

CREATE TABLE _demo_fy_backup_risk_alerts AS
SELECT a.*
FROM risk_alerts a
JOIN trust_assets ta ON ta.id = a.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%';

SELECT '=== 备份行数 ===' AS section;
SELECT 'backup trust_assets' AS metric, COUNT(*) FROM _demo_fy_backup_trust_assets
UNION ALL SELECT 'backup monitor', COUNT(*) FROM _demo_fy_backup_trust_asset_monitor_records
UNION ALL SELECT 'backup repayment', COUNT(*) FROM _demo_fy_backup_trust_repayment_detail_records
UNION ALL SELECT 'backup followups', COUNT(*) FROM _demo_fy_backup_trust_overdue_followups
UNION ALL SELECT 'backup risk_alerts', COUNT(*) FROM _demo_fy_backup_risk_alerts;

-- ------------------------------------------------------------
-- C. 按外键依赖顺序删除（子表 → 主表）
-- ------------------------------------------------------------
DELETE FROM risk_alerts a
USING trust_assets ta
WHERE a.trust_asset_id = ta.id
  AND ta.asset_code LIKE 'FY-%';

DELETE FROM trust_overdue_followups f
USING trust_assets ta
WHERE f.trust_asset_id = ta.id
  AND ta.asset_code LIKE 'FY-%';

DELETE FROM trust_repayment_detail_records r
USING trust_assets ta
WHERE r.trust_asset_id = ta.id
  AND ta.asset_code LIKE 'FY-%';

DELETE FROM trust_asset_monitor_records m
USING trust_assets ta
WHERE m.trust_asset_id = ta.id
  AND ta.asset_code LIKE 'FY-%';

DELETE FROM trust_assets
WHERE asset_code LIKE 'FY-%';

-- ------------------------------------------------------------
-- D. 删除后统计
-- ------------------------------------------------------------
SELECT '=== 删除后统计 ===' AS section;

SELECT 'trust_assets (FY-*)' AS metric, COUNT(*) AS cnt
FROM trust_assets WHERE asset_code LIKE 'FY-%';

SELECT 'trust_repayment_detail_records (FY-*)' AS metric, COUNT(*) AS cnt
FROM trust_repayment_detail_records r
JOIN trust_assets ta ON ta.id = r.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%';

SELECT 'trust_asset_monitor_records (FY-*)' AS metric, COUNT(*) AS cnt
FROM trust_asset_monitor_records m
JOIN trust_assets ta ON ta.id = m.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%';

SELECT 'trust_overdue_followups (FY-*)' AS metric, COUNT(*) AS cnt
FROM trust_overdue_followups f
JOIN trust_assets ta ON ta.id = f.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%';

SELECT 'risk_alerts (FY-*)' AS metric, COUNT(*) AS cnt
FROM risk_alerts a
JOIN trust_assets ta ON ta.id = a.trust_asset_id
WHERE ta.asset_code LIKE 'FY-%';

COMMIT;

-- ============================================================
-- E. 回滚方案（单独执行 rollback_demo_assets.sql 或以下语句）
-- 前提：_demo_fy_backup_* 表仍存在且未 DROP
-- ============================================================
-- 见 rollback_demo_assets.sql
