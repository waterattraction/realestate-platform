#!/usr/bin/env python3
"""美好生活3号 · 0612已还款 · 托管编码归属修正（RepairJob 参考实现）。

规范：docs/engineering/production_data_repair_standard.md
历史审计：使用 legacy 备份表 / 日志表（规范建立前已执行 apply）。
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.ops.framework.base import RepairContext, RepairJob
from scripts.ops.framework.cli import run_repair_cli

PRODUCT_ID = 3
SOURCE_FILE = "美好生活3号-还款明细披露信息_20260612.xlsx"
SOURCE_SHEET = "0612已还款"
EXPECTED_MISMATCH = 71

# 规范建立前已执行的审计对象（保留，勿删）
LEGACY_BACKUP_TABLE = "_ops_p3_repay_0612_custody_fix_backup"
LEGACY_LOG_TABLE = "_ops_p3_repay_0612_custody_fix_log"

SCOPE_WHERE = """
    r.trust_product_id = :pid
    AND r.source_file_name = :file
    AND r.source_sheet_name = :sheet
    AND regexp_replace(COALESCE(r.custody_asset_code, ''), '\\.0$', '')
     <> regexp_replace(COALESCE(r.source_asset_code, ''), '\\.0$', '')
"""

DRY_RUN_QUERY = f"""
SELECT
    r.id,
    r.trust_asset_id AS old_trust_asset_id,
    ta_new.id AS new_trust_asset_id,
    regexp_replace(COALESCE(r.custody_asset_code, ''), '\\.0$', '') AS old_custody_asset_code,
    regexp_replace(COALESCE(r.source_asset_code, r.asset_code), '\\.0$', '') AS auth_source_asset_code,
    regexp_replace(COALESCE(r.asset_code, ''), '\\.0$', '') AS old_asset_code,
    regexp_replace(COALESCE(r.source_asset_code, r.asset_code), '\\.0$', '') AS new_custody_asset_code,
    regexp_replace(COALESCE(r.source_asset_code, r.asset_code), '\\.0$', '') AS new_asset_code,
    r.actual_repayment_amount,
    r.period_no,
    r.repayment_date,
    r.source_file_name,
    r.source_sheet_name
FROM trust_repayment_detail_records r
JOIN trust_assets ta_new
  ON ta_new.trust_product_id = :pid
 AND regexp_replace(COALESCE(ta_new.source_asset_code, ta_new.asset_code), '\\.0$', '')
   = regexp_replace(COALESCE(r.source_asset_code, r.asset_code), '\\.0$', '')
WHERE {SCOPE_WHERE}
ORDER BY r.id
"""


def _params() -> dict:
    return {"pid": PRODUCT_ID, "file": SOURCE_FILE, "sheet": SOURCE_SHEET}


def strict_min_multiple(amts: list[float]) -> bool:
    uniq = sorted(set(round(float(a), 2) for a in amts))
    if len(uniq) <= 1:
        return True
    base = min(a for a in uniq if a > 0)
    return all(abs(a / base - round(a / base)) <= 0.01 for a in uniq)


class Product3Repay0612CustodyRepair(RepairJob):
    repair_name = "product3_repay_0612_custody"
    expected_rows = EXPECTED_MISMATCH
    legacy_backup_table = LEGACY_BACKUP_TABLE

    def check(self, ctx: RepairContext) -> int:
        p = _params()
        conn = ctx.conn
        row = conn.execute(
            text("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (
                         WHERE regexp_replace(COALESCE(custody_asset_code,''), '\\.0$', '')
                            <> regexp_replace(COALESCE(source_asset_code,''), '\\.0$', '')
                       ) AS mismatch
                FROM trust_repayment_detail_records r
                WHERE r.trust_product_id = :pid
                  AND r.source_file_name = :file
                  AND r.source_sheet_name = :sheet
            """),
            p,
        ).fetchone()
        print(f"sheet_total={row.total} mismatch_rows={row.mismatch} (expect 111 / {EXPECTED_MISMATCH})")

        dup = conn.execute(
            text("""
                SELECT COUNT(*) FROM (
                  SELECT source_asset_code FROM trust_assets
                  WHERE trust_product_id = :pid AND source_asset_code IS NOT NULL
                  GROUP BY source_asset_code HAVING COUNT(*) > 1
                ) t
            """),
            p,
        ).scalar()
        print(f"trust_assets duplicate source_asset_code groups: {dup} (expect 0)")

        missing = conn.execute(
            text(f"""
                SELECT COUNT(*) FROM trust_repayment_detail_records r
                WHERE {SCOPE_WHERE}
                  AND NOT EXISTS (
                    SELECT 1 FROM trust_assets ta
                    WHERE ta.trust_product_id = :pid
                      AND regexp_replace(COALESCE(ta.source_asset_code, ta.asset_code), '\\.0$', '')
                        = regexp_replace(COALESCE(r.source_asset_code, r.asset_code), '\\.0$', '')
                  )
            """),
            p,
        ).scalar()
        print(f"missing target trust_assets for mismatch rows: {missing} (expect 0)")

        rows = conn.execute(
            text("""
                SELECT regexp_replace(COALESCE(source_asset_code, asset_code), '\\.0$', '') AS auth,
                       actual_repayment_amount AS amt
                FROM trust_repayment_detail_records WHERE trust_product_id = :pid
            """),
            p,
        ).fetchall()
        by_auth: dict[str, list[float]] = defaultdict(list)
        for r in rows:
            by_auth[r.auth].append(float(r.amt))
        strict_fail = [a for a, amts in by_auth.items() if not strict_min_multiple(amts)]
        print(f"strict_rule_pass={len(by_auth) - len(strict_fail)}/407 strict_rule_fail={len(strict_fail)}/407")

        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        baseline_path = ctx.output_dir / "strict_fail_baseline_p3.txt"
        if not baseline_path.exists():
            baseline_path.write_text("\n".join(sorted(strict_fail)) + "\n", encoding="utf-8")
            print(f"wrote baseline: {baseline_path}")

        try:
            ctx.log("check", rows_checked=int(row.total), remark=f"mismatch={row.mismatch}")
        except Exception:
            pass
        return 0

    def dry_run(self, ctx: RepairContext) -> int:
        p = _params()
        rows = ctx.conn.execute(text(DRY_RUN_QUERY), p).mappings().all()
        print(f"dry_run_rows={len(rows)} (expect {EXPECTED_MISMATCH})")
        if len(rows) != EXPECTED_MISMATCH:
            print("ERROR: row count mismatch — abort dry-run export", file=sys.stderr)
            return 1

        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        csv_path = ctx.output_dir / f"product3_repay_0612_custody_dry_run_{ts}.csv"
        json_path = ctx.output_dir / f"product3_repay_0612_custody_dry_run_{ts}.json"

        fieldnames = list(rows[0].keys()) if rows else []
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                w.writerow({k: r[k] for k in fieldnames})

        json_path.write_text(
            json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"written: {csv_path}")
        print(f"written: {json_path}")
        try:
            ctx.log("dry_run", rows_checked=len(rows))
        except Exception:
            pass
        return 0

    def apply(self, ctx: RepairContext) -> int:
        p = _params()
        backup = ctx.backup_table
        with ctx.transaction():
            ctx.conn.execute(text(f"DROP TABLE IF EXISTS {backup}"))
            ctx.conn.execute(
                text(f"""
                    CREATE TABLE {backup} AS
                    SELECT r.*, NOW() AS backed_up_at
                    FROM trust_repayment_detail_records r
                    WHERE {SCOPE_WHERE}
                """),
                p,
            )
            backup_cnt = ctx.conn.execute(text(f"SELECT COUNT(*) FROM {backup}")).scalar()
            ctx.assert_rowcount(int(backup_cnt), EXPECTED_MISMATCH, action="BACKUP")

            dup = ctx.conn.execute(
                text("""
                    SELECT COUNT(*) FROM (
                      SELECT source_asset_code FROM trust_assets
                      WHERE trust_product_id = :pid AND source_asset_code IS NOT NULL
                      GROUP BY source_asset_code HAVING COUNT(*) > 1
                    ) t
                """),
                p,
            ).scalar()
            if int(dup) > 0:
                raise RuntimeError(f"trust_assets has {dup} duplicate source_asset_code groups")

            result = ctx.conn.execute(
                text(f"""
                    UPDATE trust_repayment_detail_records r
                    SET
                      custody_asset_code = regexp_replace(
                          COALESCE(r.source_asset_code, r.asset_code), '\\.0$', ''
                      ),
                      asset_code = regexp_replace(
                          COALESCE(r.source_asset_code, r.asset_code), '\\.0$', ''
                      ),
                      trust_asset_id = ta.id
                    FROM trust_assets ta
                    WHERE {SCOPE_WHERE}
                      AND ta.trust_product_id = :pid
                      AND regexp_replace(COALESCE(ta.source_asset_code, ta.asset_code), '\\.0$', '')
                        = regexp_replace(COALESCE(r.source_asset_code, r.asset_code), '\\.0$', '')
                """),
                p,
            )
            updated = int(result.rowcount or 0)
            ctx.assert_rowcount(updated, EXPECTED_MISMATCH)

            unchanged = ctx.conn.execute(
                text(f"""
                    SELECT COUNT(*) FROM {backup} b
                    JOIN trust_repayment_detail_records r ON r.id = b.id
                    WHERE r.actual_repayment_amount IS DISTINCT FROM b.actual_repayment_amount
                       OR r.period_no IS DISTINCT FROM b.period_no
                       OR r.repayment_date IS DISTINCT FROM b.repayment_date
                       OR r.data_date IS DISTINCT FROM b.data_date
                       OR r.source_file_name IS DISTINCT FROM b.source_file_name
                       OR r.source_sheet_name IS DISTINCT FROM b.source_sheet_name
                       OR r.synced_at IS DISTINCT FROM b.synced_at
                       OR r.created_at IS DISTINCT FROM b.created_at
                       OR r.source_asset_code IS DISTINCT FROM b.source_asset_code
                """),
            ).scalar()
            if int(unchanged) > 0:
                raise RuntimeError(f"immutable fields changed on {unchanged} rows")

            # Legacy log（本案例规范前已使用）
            ctx.conn.execute(
                text(f"""
                    CREATE TABLE IF NOT EXISTS {LEGACY_LOG_TABLE} (
                        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                        executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        operator TEXT,
                        updated_count INT NOT NULL,
                        backup_table TEXT NOT NULL
                    )
                """),
            )
            ctx.conn.execute(
                text(f"""
                    INSERT INTO {LEGACY_LOG_TABLE} (operator, updated_count, backup_table)
                    VALUES (:op, :cnt, :tbl)
                """),
                {"op": os.environ.get("USER", "ops"), "cnt": updated, "tbl": backup},
            )

        print(f"apply OK: updated {updated} rows, backup={backup}")
        try:
            ctx.log("applied", rows_updated=updated, backup_table=backup)
        except Exception:
            pass
        return 0

    def verify(self, ctx: RepairContext) -> int:
        p = _params()
        aligned = ctx.conn.execute(
            text("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (
                         WHERE regexp_replace(COALESCE(custody_asset_code,''), '\\.0$', '')
                            = regexp_replace(COALESCE(source_asset_code,''), '\\.0$', '')
                           AND regexp_replace(COALESCE(asset_code,''), '\\.0$', '')
                            = regexp_replace(COALESCE(source_asset_code,''), '\\.0$', '')
                       ) AS aligned
                FROM trust_repayment_detail_records
                WHERE trust_product_id = :pid
                  AND source_file_name = :file
                  AND source_sheet_name = :sheet
            """),
            p,
        ).fetchone()
        print(f"sheet aligned {aligned.aligned}/{aligned.total} (expect 111/111)")

        mismatch_left = ctx.conn.execute(
            text(f"SELECT COUNT(*) FROM trust_repayment_detail_records r WHERE {SCOPE_WHERE}"),
            p,
        ).scalar()
        print(f"mismatch_rows_remaining={mismatch_left} (expect 0)")

        still_wrong = 0
        if int(mismatch_left) == 0 and ctx.table_exists(ctx.backup_table):
            still_wrong = ctx.conn.execute(
                text(f"""
                    SELECT COUNT(*) FROM {ctx.backup_table} b
                    JOIN trust_repayment_detail_records r ON r.id = b.id
                    JOIN trust_assets ta ON ta.id = r.trust_asset_id
                    WHERE regexp_replace(COALESCE(ta.source_asset_code, ta.asset_code), '\\.0$', '')
                       <> regexp_replace(COALESCE(r.source_asset_code, r.asset_code), '\\.0$', '')
                """),
            ).scalar()
            print(f"backup_rows_with_wrong_trust_asset_id={still_wrong} (expect 0)")

        ok = int(mismatch_left) == 0
        verify_result = {
            "aligned": f"{aligned.aligned}/{aligned.total}",
            "mismatch_remaining": int(mismatch_left),
            "wrong_trust_asset_id": int(still_wrong),
        }
        try:
            ctx.log("verified", verify_result=verify_result)
        except Exception:
            pass
        return 0 if ok else 1

    def rollback(self, ctx: RepairContext) -> int:
        backup = ctx.backup_table
        if not ctx.table_exists(backup):
            raise SystemExit(f"backup table {backup} not found")

        with ctx.transaction():
            result = ctx.conn.execute(
                text(f"""
                    UPDATE trust_repayment_detail_records r
                    SET trust_asset_id = b.trust_asset_id,
                        asset_code = b.asset_code,
                        custody_asset_code = b.custody_asset_code
                    FROM {backup} b
                    WHERE r.id = b.id
                """),
            )
            restored = int(result.rowcount or 0)
        print(f"rollback restored {restored} rows from {backup}")
        try:
            ctx.log("rolled_back", rows_rollback=restored, backup_table=backup)
        except Exception:
            pass
        return 0


def main() -> int:
    return run_repair_cli(Product3Repay0612CustodyRepair)


if __name__ == "__main__":
    raise SystemExit(main())
