-- 统一生产数据修复审计日志
-- 适用：所有新 Repair Job（见 docs/engineering/production_data_repair_standard.md）
-- 执行：DBA 在生产/预发执行一次；勿在 Repair apply 中重复 CREATE（框架会 IF NOT EXISTS）

CREATE TABLE IF NOT EXISTS repair_log (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repair_name     VARCHAR(128)  NOT NULL,
    operator        VARCHAR(64)   NOT NULL DEFAULT 'ops',
    start_time      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    finish_time     TIMESTAMPTZ,
    status          VARCHAR(32)   NOT NULL,
    rows_checked    INT,
    rows_updated    INT,
    rows_rollback   INT,
    verify_result   TEXT,
    remark          TEXT,
    backup_table    VARCHAR(128),
    CONSTRAINT chk_repair_log_status CHECK (
        status IN (
            'check', 'dry_run', 'applied', 'verified',
            'rolled_back', 'failed'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_repair_log_name_time
    ON repair_log (repair_name, start_time DESC);

COMMENT ON TABLE repair_log IS '生产数据修复统一审计日志；禁止各 Repair 自建 log 表';
