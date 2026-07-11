-- repair_name: product2_repay_33600_asset_code
-- 修正还款 id=33600：asset_code 对齐 trust_assets 权威主编号 107113281945
-- 不改：trust_asset_id, custody, source, 金额, 日期, 来源文件

BEGIN;

DROP TABLE IF EXISTS _ops_p2_repay_33600_asset_code_backup;

CREATE TABLE _ops_p2_repay_33600_asset_code_backup AS
SELECT r.*, NOW() AS backed_up_at
FROM trust_repayment_detail_records r
WHERE r.id = 33600;

DO $$
DECLARE
    v_backup INT;
    v_mismatch INT;
    v_updated INT;
BEGIN
    SELECT COUNT(*) INTO v_backup FROM _ops_p2_repay_33600_asset_code_backup;
    IF v_backup <> 1 THEN
        RAISE EXCEPTION 'backup rows % <> 1', v_backup;
    END IF;

    SELECT COUNT(*) INTO v_mismatch
    FROM trust_repayment_detail_records r
    JOIN trust_assets ta ON ta.id = r.trust_asset_id
    WHERE r.id = 33600
      AND r.asset_code IS DISTINCT FROM ta.asset_code;
    IF v_mismatch <> 1 THEN
        RAISE EXCEPTION 'mismatch rows % <> 1 (already fixed?)', v_mismatch;
    END IF;

    UPDATE trust_repayment_detail_records r
    SET asset_code = ta.asset_code
    FROM trust_assets ta
    WHERE r.id = 33600
      AND ta.id = r.trust_asset_id
      AND r.asset_code IS DISTINCT FROM ta.asset_code;

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    IF v_updated <> 1 THEN
        RAISE EXCEPTION 'UPDATE rowcount % <> 1', v_updated;
    END IF;
END $$;

COMMIT;
