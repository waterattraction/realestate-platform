#!/usr/bin/env python3
"""美好生活3号 · 0612已还款 · 托管编码归属修正（可审计 / 可回滚 / 可重复验证）。

子命令：
  check    — 只读检查 + 严格倍数基线
  dry-run  — 输出全部错挂行修正前后对照（不写库）
  apply    — 备份 + 事务 UPDATE（必须恰好 71 行）+ 验收
  verify   — 修正后验收（可重复）
  rollback — 从备份表恢复

不修改：金额、期次、还款日期、source_file_name、source_sheet_name、synced_at、created_at、source_asset_code
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

PRODUCT_ID = 3
SOURCE_FILE = "美好生活3号-还款明细披露信息_20260612.xlsx"
SOURCE_SHEET = "0612已还款"
EXPECTED_MISMATCH = 71

BACKUP_TABLE = "_ops_p3_repay_0612_custody_fix_backup"
LOG_TABLE = "_ops_p3_repay_0612_custody_fix_log"

OPS_OUTPUT_ROOT = Path(os.environ.get("OPS_OUTPUT_DIR", "/data/uploads/ops/product3_repay_0612"))

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
WHERE {SCOPE_WHERE.replace('r.', 'r.')}
ORDER BY r.id
"""


def _params() -> dict:
    return {"pid": PRODUCT_ID, "file": SOURCE_FILE, "sheet": SOURCE_SHEET}


def _engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set")
    return create_engine(url)


def norm_code(v: str | None) -> str:
    if not v:
        return ""
    s = str(v).strip()
    return s[:-2] if s.endswith(".0") else s


def strict_min_multiple(amts: list[float]) -> bool:
    uniq = sorted(set(round(float(a), 2) for a in amts))
    if len(uniq) <= 1:
        return True
    base = min(a for a in uniq if a > 0)
    return all(abs(a / base - round(a / base)) <= 0.01 for a in uniq)


def cmd_check(conn) -> int:
    p = _params()
    row = conn.execute(
        text(f"""
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
    OPS_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    baseline_path = OPS_OUTPUT_ROOT / "strict_fail_baseline_p3.txt"
    if not baseline_path.exists():
        baseline_path.write_text("\n".join(sorted(strict_fail)) + "\n", encoding="utf-8")
        print(f"wrote baseline: {baseline_path}")
    return 0


def cmd_dry_run(conn, out_dir: Path) -> int:
    p = _params()
    rows = conn.execute(text(DRY_RUN_QUERY), p).mappings().all()
    print(f"dry_run_rows={len(rows)} (expect {EXPECTED_MISMATCH})")
    if len(rows) != EXPECTED_MISMATCH:
        print("ERROR: row count mismatch — abort dry-run export", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = out_dir / f"product3_repay_0612_custody_dry_run_{ts}.csv"
    json_path = out_dir / f"product3_repay_0612_custody_dry_run_{ts}.json"

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
    return 0


def cmd_apply(conn) -> int:
    p = _params()
    with conn.begin():
        conn.execute(text(f"DROP TABLE IF EXISTS {BACKUP_TABLE}"))
        conn.execute(
            text(f"""
                CREATE TABLE {BACKUP_TABLE} AS
                SELECT r.*, NOW() AS backed_up_at
                FROM trust_repayment_detail_records r
                WHERE {SCOPE_WHERE}
            """),
            p,
        )
        backup_cnt = conn.execute(text(f"SELECT COUNT(*) FROM {BACKUP_TABLE}")).scalar()
        if int(backup_cnt) != EXPECTED_MISMATCH:
            raise RuntimeError(f"backup count {backup_cnt} != {EXPECTED_MISMATCH}")

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
        if int(dup) > 0:
            raise RuntimeError(f"trust_assets has {dup} duplicate source_asset_code groups")

        result = conn.execute(
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
        if updated != EXPECTED_MISMATCH:
            raise RuntimeError(f"UPDATE rowcount {updated} != {EXPECTED_MISMATCH} — transaction rolled back")

        unchanged = conn.execute(
            text(f"""
                SELECT COUNT(*) FROM {BACKUP_TABLE} b
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

        conn.execute(
            text(f"""
                CREATE TABLE IF NOT EXISTS {LOG_TABLE} (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    operator TEXT,
                    updated_count INT NOT NULL,
                    backup_table TEXT NOT NULL
                )
            """),
        )
        conn.execute(
            text(f"""
                INSERT INTO {LOG_TABLE} (operator, updated_count, backup_table)
                VALUES (:op, :cnt, :tbl)
            """),
            {"op": os.environ.get("USER", "ops"), "cnt": updated, "tbl": BACKUP_TABLE},
        )

    print(f"apply OK: updated {updated} rows, backup={BACKUP_TABLE}")
    return 0


def cmd_verify(conn) -> int:
    p = _params()
    aligned = conn.execute(
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

    mismatch_left = conn.execute(
        text(f"""
            SELECT COUNT(*) FROM trust_repayment_detail_records r
            WHERE {SCOPE_WHERE}
        """),
        p,
    ).scalar()
    print(f"mismatch_rows_remaining={mismatch_left} (expect 0)")

    if int(mismatch_left) == 0 and BACKUP_TABLE:
        still_wrong = conn.execute(
            text(f"""
                SELECT COUNT(*) FROM {BACKUP_TABLE} b
                JOIN trust_repayment_detail_records r ON r.id = b.id
                JOIN trust_assets ta ON ta.id = r.trust_asset_id
                WHERE regexp_replace(COALESCE(ta.source_asset_code, ta.asset_code), '\\.0$', '')
                   <> regexp_replace(COALESCE(r.source_asset_code, r.asset_code), '\\.0$', '')
            """),
        ).scalar()
        print(f"backup_rows_with_wrong_trust_asset_id={still_wrong} (expect 0 if applied)")

    return 0 if int(mismatch_left) == 0 else 1


def cmd_rollback(conn) -> int:
    exists = conn.execute(
        text("""
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_name = :t
            )
        """),
        {"t": BACKUP_TABLE},
    ).scalar()
    if not exists:
        raise SystemExit(f"backup table {BACKUP_TABLE} not found")

    with conn.begin():
        result = conn.execute(
            text(f"""
                UPDATE trust_repayment_detail_records r
                SET trust_asset_id = b.trust_asset_id,
                    asset_code = b.asset_code,
                    custody_asset_code = b.custody_asset_code
                FROM {BACKUP_TABLE} b
                WHERE r.id = b.id
            """),
        )
        print(f"rollback restored {result.rowcount} rows from {BACKUP_TABLE}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["check", "dry-run", "apply", "verify", "rollback"],
    )
    parser.add_argument(
        "--out-dir",
        default=str(OPS_OUTPUT_ROOT),
        help="dry-run CSV/JSON output directory (writable; default /data/uploads/ops/product3_repay_0612)",
    )
    args = parser.parse_args()

    engine = _engine()
    with engine.connect() as conn:
        if args.command == "check":
            return cmd_check(conn)
        if args.command == "dry-run":
            return cmd_dry_run(conn, Path(args.out_dir))
        if args.command == "apply":
            return cmd_apply(conn)
        if args.command == "verify":
            return cmd_verify(conn)
        if args.command == "rollback":
            return cmd_rollback(conn)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
