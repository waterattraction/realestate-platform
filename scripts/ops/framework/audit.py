"""RepairJob 审计：统一 backup 命名与 repair_log 写入."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

REPAIR_LOG_DDL = """
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
"""


def backup_table_name(repair_name: str) -> str:
    """统一备份表名：_ops_backup_<repair_name>"""
    safe = repair_name.replace("-", "_").replace(".", "_")
    return f"_ops_backup_{safe}"


def legacy_backup_table_name(repair_name: str) -> str | None:
    """历史 Repair 可能使用非标准备份表名；子类可 override backup_table property。"""
    return None


def operator_name() -> str:
    return os.environ.get("REPAIR_OPERATOR") or os.environ.get("USER") or "ops"


def ensure_repair_log_table(conn: Connection) -> None:
    conn.execute(text(REPAIR_LOG_DDL))


def write_repair_log(
    conn: Connection,
    *,
    repair_name: str,
    status: str,
    rows_checked: int | None = None,
    rows_updated: int | None = None,
    rows_rollback: int | None = None,
    verify_result: Any = None,
    remark: str | None = None,
    backup_table: str | None = None,
    log_id: int | None = None,
) -> int:
    """插入或更新 repair_log 行；返回 log id。"""
    ensure_repair_log_table(conn)
    verify_text = None
    if verify_result is not None:
        verify_text = (
            verify_result
            if isinstance(verify_result, str)
            else json.dumps(verify_result, ensure_ascii=False, default=str)
        )

    if log_id is None:
        row = conn.execute(
            text("""
                INSERT INTO repair_log (
                    repair_name, operator, status,
                    rows_checked, rows_updated, rows_rollback,
                    verify_result, remark, backup_table, finish_time
                ) VALUES (
                    :name, :op, :status,
                    :checked, :updated, :rollback,
                    :verify, :remark, :backup,
                    CASE WHEN :status IN ('applied','verified','rolled_back','failed')
                         THEN NOW() ELSE NULL END
                )
                RETURNING id
            """),
            {
                "name": repair_name,
                "op": operator_name(),
                "status": status,
                "checked": rows_checked,
                "updated": rows_updated,
                "rollback": rows_rollback,
                "verify": verify_text,
                "remark": remark,
                "backup": backup_table,
            },
        ).fetchone()
        return int(row.id)

    conn.execute(
        text("""
            UPDATE repair_log SET
                status = :status,
                rows_checked = COALESCE(:checked, rows_checked),
                rows_updated = COALESCE(:updated, rows_updated),
                rows_rollback = COALESCE(:rollback, rows_rollback),
                verify_result = COALESCE(:verify, verify_result),
                remark = COALESCE(:remark, remark),
                backup_table = COALESCE(:backup, backup_table),
                finish_time = NOW()
            WHERE id = :id
        """),
        {
            "id": log_id,
            "status": status,
            "checked": rows_checked,
            "updated": rows_updated,
            "rollback": rows_rollback,
            "verify": verify_text,
            "remark": remark,
            "backup": backup_table,
        },
    )
    return log_id


def default_output_dir(repair_name: str) -> str:
    return os.environ.get(
        "OPS_OUTPUT_DIR",
        f"/data/uploads/ops/{repair_name}",
    )
