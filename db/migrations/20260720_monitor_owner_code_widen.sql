-- 监控 owner_code：Excel 业主代码可达 ~118 字符，原 VARCHAR(100) 过短
ALTER TABLE trust_asset_monitor_records
    ALTER COLUMN owner_code TYPE VARCHAR(200);
