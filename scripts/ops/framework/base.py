"""RepairJob 抽象基类与执行上下文."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from scripts.ops.framework.audit import (
    backup_table_name,
    default_output_dir,
    write_repair_log,
)


@dataclass
class RepairContext:
    conn: Connection
    repair_name: str
    output_dir: Path
    backup_table: str
    _log_id: int | None = field(default=None, repr=False)

    def log(
        self,
        status: str,
        *,
        rows_checked: int | None = None,
        rows_updated: int | None = None,
        rows_rollback: int | None = None,
        verify_result: object = None,
        remark: str | None = None,
    ) -> None:
        self._log_id = write_repair_log(
            self.conn,
            repair_name=self.repair_name,
            status=status,
            rows_checked=rows_checked,
            rows_updated=rows_updated,
            rows_rollback=rows_rollback,
            verify_result=verify_result,
            remark=remark,
            backup_table=self.backup_table,
            log_id=self._log_id,
        )

    @contextmanager
    def transaction(self) -> Generator[Connection, None, None]:
        """可嵌套于 engine.connect()；失败自动 ROLLBACK。"""
        if self.conn.in_transaction():
            with self.conn.begin_nested():
                yield self.conn
        else:
            with self.conn.begin():
                yield self.conn

    def assert_rowcount(self, actual: int, expected: int, *, action: str = "UPDATE") -> None:
        if actual != expected:
            raise RuntimeError(
                f"{action} rowcount {actual} != expected {expected} — transaction rolled back"
            )

    def table_exists(self, table_name: str) -> bool:
        return bool(
            self.conn.execute(
                text("""
                    SELECT EXISTS (
                      SELECT 1 FROM information_schema.tables
                      WHERE table_name = :t
                    )
                """),
                {"t": table_name},
            ).scalar()
        )


class RepairJob(ABC):
    """生产数据修复标准生命周期。"""

    repair_name: str
    expected_rows: int | None = None
    use_legacy_backup: bool = False
    legacy_backup_table: str | None = None

    @property
    def backup_table(self) -> str:
        if self.legacy_backup_table:
            return self.legacy_backup_table
        return backup_table_name(self.repair_name)

    @property
    def output_dir(self) -> Path:
        return Path(default_output_dir(self.repair_name))

    @classmethod
    def create_engine(cls) -> Engine:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise SystemExit("DATABASE_URL not set")
        return create_engine(url)

    def make_context(self, conn: Connection, output_dir: Path | None = None) -> RepairContext:
        return RepairContext(
            conn=conn,
            repair_name=self.repair_name,
            output_dir=output_dir or self.output_dir,
            backup_table=self.backup_table,
        )

    @abstractmethod
    def check(self, ctx: RepairContext) -> int:
        """只读检查；返回 0 成功，非 0 失败。"""

    @abstractmethod
    def dry_run(self, ctx: RepairContext) -> int:
        """导出对照，不写库。"""

    @abstractmethod
    def apply(self, ctx: RepairContext) -> int:
        """事务内修改；必须 backup + 行数断言。"""

    @abstractmethod
    def verify(self, ctx: RepairContext) -> int:
        """修正后验收。"""

    @abstractmethod
    def rollback(self, ctx: RepairContext) -> int:
        """从备份表恢复。"""
