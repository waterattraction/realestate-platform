#!/usr/bin/env python3
"""美好生活1号 · 还款 id=33841 · asset_code 对齐 trust_assets（不改 source / 导入逻辑）。"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.ops.framework.base import RepairContext, RepairJob
from scripts.ops.framework.cli import run_repair_cli

REPAIR_ID = 33841
EXPECTED_ROWS = 1
CANONICAL = "101130798182"
SOURCE_UNCHANGED = "101135047520"


class Product1Repay33841AssetCodeRepair(RepairJob):
    repair_name = "product1_repay_33841_asset_code"
    expected_rows = EXPECTED_ROWS

    def check(self, ctx: RepairContext) -> int:
        row = ctx.conn.execute(
            text("""
                SELECT
                    r.id,
                    r.trust_product_id,
                    r.trust_asset_id,
                    r.asset_code AS stored_asset_code,
                    ta.asset_code AS canonical_asset_code,
                    r.custody_asset_code,
                    r.source_asset_code,
                    r.repayment_date,
                    r.actual_repayment_amount,
                    r.source_file_name,
                    r.source_sheet_name
                FROM trust_repayment_detail_records r
                JOIN trust_assets ta ON ta.id = r.trust_asset_id
                WHERE r.id = :id
            """),
            {"id": REPAIR_ID},
        ).mappings().first()
        if not row:
            print(f"ERROR: id={REPAIR_ID} not found", file=sys.stderr)
            return 1
        print(dict(row))
        mismatch = int(row["stored_asset_code"] != row["canonical_asset_code"])
        print(f"mismatch={mismatch} (expect 1)")
        print(f"source_asset_code={row['source_asset_code']} (must remain {SOURCE_UNCHANGED})")
        if mismatch != 1:
            print("ERROR: expected exactly 1 mismatch", file=sys.stderr)
            return 1
        if row["canonical_asset_code"] != CANONICAL:
            print(f"ERROR: canonical expected {CANONICAL}", file=sys.stderr)
            return 1
        if row["source_asset_code"] != SOURCE_UNCHANGED:
            print("ERROR: source_asset_code unexpected — abort", file=sys.stderr)
            return 1
        try:
            ctx.log("check", rows_checked=1, remark="mismatch=1")
        except Exception:
            pass
        return 0

    def dry_run(self, ctx: RepairContext) -> int:
        row = ctx.conn.execute(
            text("""
                SELECT
                    r.id,
                    r.trust_asset_id,
                    r.asset_code AS old_asset_code,
                    ta.asset_code AS new_asset_code,
                    r.custody_asset_code,
                    r.source_asset_code,
                    r.repayment_date,
                    r.actual_repayment_amount,
                    r.source_file_name,
                    r.source_sheet_name
                FROM trust_repayment_detail_records r
                JOIN trust_assets ta ON ta.id = r.trust_asset_id
                WHERE r.id = :id
                  AND r.asset_code IS DISTINCT FROM ta.asset_code
            """),
            {"id": REPAIR_ID},
        ).mappings().all()
        print(f"dry_run_rows={len(row)} (expect {EXPECTED_ROWS})")
        if len(row) != EXPECTED_ROWS:
            return 1
        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        csv_path = ctx.output_dir / f"{self.repair_name}_dry_run_{ts}.csv"
        json_path = ctx.output_dir / f"{self.repair_name}_dry_run_{ts}.json"
        fieldnames = list(row[0].keys())
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in row:
                w.writerow({k: r[k] for k in fieldnames})
        json_path.write_text(
            json.dumps([dict(r) for r in row], ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"written: {csv_path}")
        print(f"written: {json_path}")
        try:
            ctx.log("dry_run", rows_checked=len(row))
        except Exception:
            pass
        return 0

    def apply(self, ctx: RepairContext) -> int:
        backup = ctx.backup_table
        with ctx.transaction():
            ctx.conn.execute(text(f"DROP TABLE IF EXISTS {backup}"))
            ctx.conn.execute(
                text(f"""
                    CREATE TABLE {backup} AS
                    SELECT r.*, NOW() AS backed_up_at
                    FROM trust_repayment_detail_records r
                    WHERE r.id = :id
                """),
                {"id": REPAIR_ID},
            )
            n_backup = ctx.conn.execute(
                text(f"SELECT COUNT(*) FROM {backup}")
            ).scalar()
            ctx.assert_rowcount(int(n_backup), EXPECTED_ROWS, action="backup")

            result = ctx.conn.execute(
                text("""
                    UPDATE trust_repayment_detail_records r
                    SET asset_code = ta.asset_code
                    FROM trust_assets ta
                    WHERE r.id = :id
                      AND ta.id = r.trust_asset_id
                      AND r.asset_code IS DISTINCT FROM ta.asset_code
                """),
                {"id": REPAIR_ID},
            )
            ctx.assert_rowcount(result.rowcount, EXPECTED_ROWS, action="UPDATE")
            try:
                ctx.log("applied", rows_updated=EXPECTED_ROWS, remark=f"backup={backup}")
            except Exception:
                pass
        print(f"apply OK: updated {EXPECTED_ROWS} row, backup={backup}")
        return 0

    def verify(self, ctx: RepairContext) -> int:
        row = ctx.conn.execute(
            text("""
                SELECT
                    r.asset_code,
                    ta.asset_code AS canonical,
                    r.source_asset_code,
                    r.custody_asset_code
                FROM trust_repayment_detail_records r
                JOIN trust_assets ta ON ta.id = r.trust_asset_id
                WHERE r.id = :id
            """),
            {"id": REPAIR_ID},
        ).mappings().first()
        if not row:
            print("ERROR: row missing after apply", file=sys.stderr)
            return 1
        print(dict(row))
        ok = (
            row["asset_code"] == CANONICAL
            and row["asset_code"] == row["canonical"]
            and row["source_asset_code"] == SOURCE_UNCHANGED
        )
        global_m = ctx.conn.execute(
            text("""
                SELECT COUNT(*)
                FROM trust_repayment_detail_records r
                JOIN trust_assets ta ON ta.id = r.trust_asset_id
                WHERE r.asset_code IS DISTINCT FROM ta.asset_code
            """)
        ).scalar()
        print(f"global_mismatch={global_m} (expect 0)")
        if not ok or int(global_m) != 0:
            print("ERROR: verify failed", file=sys.stderr)
            try:
                ctx.log("failed", verify_result={"ok": False, "global_mismatch": global_m})
            except Exception:
                pass
            return 1
        try:
            ctx.log("verified", verify_result={"ok": True, "global_mismatch": 0})
        except Exception:
            pass
        print("verify OK")
        return 0

    def rollback(self, ctx: RepairContext) -> int:
        backup = ctx.backup_table
        if not ctx.table_exists(backup):
            print(f"ERROR: backup table {backup} missing", file=sys.stderr)
            return 1
        with ctx.transaction():
            result = ctx.conn.execute(
                text(f"""
                    UPDATE trust_repayment_detail_records r
                    SET asset_code = b.asset_code
                    FROM {backup} b
                    WHERE r.id = :id AND b.id = :id
                """),
                {"id": REPAIR_ID},
            )
            ctx.assert_rowcount(result.rowcount, EXPECTED_ROWS, action="rollback")
            try:
                ctx.log("rolled_back", rows_rollback=EXPECTED_ROWS)
            except Exception:
                pass
        print("rollback OK")
        return 0


def main() -> int:
    return run_repair_cli(Product1Repay33841AssetCodeRepair)


if __name__ == "__main__":
    raise SystemExit(main())
