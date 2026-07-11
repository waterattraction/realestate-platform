#!/usr/bin/env python3
"""0703 监控快照：回填 last_renovation_payment_date（P0）。

从 upload volume 读取已导入的 0703 监控 Excel，按
trust_product_id + data_date + source_file_name + source_sheet_name + 资产编码
匹配 UPDATE trust_asset_monitor_records.last_renovation_payment_date。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "backend") not in sys.path:
    sys.path.insert(0, str(_REPO / "backend"))

from app.assetinfo_upload import _load_sheet, _parse_monitor_rows, upload_root
from app.db import get_engine

DATA_DATE = "2026-07-03"

UPDATE_SQL = text("""
    UPDATE trust_asset_monitor_records
    SET last_renovation_payment_date = :d
    WHERE trust_product_id = :pid
      AND data_date = :dd
      AND source_file_name = :file
      AND source_sheet_name = :sheet
      AND asset_code = :ac
      AND COALESCE(custody_asset_code, '') = COALESCE(:custody, '')
      AND COALESCE(source_asset_code, '') = COALESCE(:source, '')
""")


def _find_upload_file(file_name: str) -> Path | None:
    root = upload_root()
    matches = list(root.rglob(file_name))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill last_renovation_payment_date for 0703 monitor")
    parser.add_argument("--dry-run", action="store_true", help="Parse and match only; do not UPDATE")
    args = parser.parse_args()

    engine = get_engine()
    errors: list[str] = []
    rows_matched = 0
    rows_with_date = 0
    rows_updated = 0

    with engine.begin() as conn:
        batches = conn.execute(
            text("""
                SELECT DISTINCT trust_product_id, source_file_name, source_sheet_name
                FROM trust_asset_monitor_records
                WHERE data_date = :dd
                ORDER BY trust_product_id, source_file_name, source_sheet_name
            """),
            {"dd": DATA_DATE},
        ).mappings().all()

        if not batches:
            print(f"No monitor records for data_date={DATA_DATE}")
            return 1

        for batch in batches:
            pid = int(batch["trust_product_id"])
            file_name = str(batch["source_file_name"])
            sheet_name = str(batch["source_sheet_name"])
            path = _find_upload_file(file_name)
            if path is None:
                errors.append(f"product={pid} upload file not found: {file_name}")
                continue

            df = _load_sheet(path, sheet_name)
            parsed = _parse_monitor_rows(
                df,
                file_name=file_name,
                sheet_name=sheet_name,
            )
            if parsed.errors:
                errors.extend(f"product={pid} parse: {e}" for e in parsed.errors[:5])
            if not parsed.rows:
                errors.append(f"product={pid} no parsed rows from {file_name}")
                continue

            for row in parsed.rows:
                date_val = row.get("last_renovation_payment_date")
                params = {
                    "d": date_val,
                    "pid": pid,
                    "dd": DATA_DATE,
                    "file": file_name,
                    "sheet": sheet_name,
                    "ac": row["asset_code"],
                    "custody": row.get("custody_asset_code"),
                    "source": row.get("source_asset_code"),
                }
                if args.dry_run:
                    hit = conn.execute(
                        text("""
                            SELECT id FROM trust_asset_monitor_records
                            WHERE trust_product_id = :pid
                              AND data_date = :dd
                              AND source_file_name = :file
                              AND source_sheet_name = :sheet
                              AND asset_code = :ac
                              AND COALESCE(custody_asset_code, '') = COALESCE(:custody, '')
                              AND COALESCE(source_asset_code, '') = COALESCE(:source, '')
                        """),
                        params,
                    ).first()
                    if hit:
                        rows_matched += 1
                        if date_val is not None:
                            rows_with_date += 1
                    else:
                        errors.append(
                            f"product={pid} no DB row for asset_code={row['asset_code']} "
                            f"custody={row.get('custody_asset_code')}"
                        )
                else:
                    result = conn.execute(UPDATE_SQL, params)
                    if result.rowcount == 0:
                        errors.append(
                            f"product={pid} UPDATE 0 rows for asset_code={row['asset_code']} "
                            f"custody={row.get('custody_asset_code')}"
                        )
                    else:
                        rows_updated += result.rowcount
                        rows_matched += result.rowcount
                        if date_val is not None:
                            rows_with_date += result.rowcount

        filled = conn.execute(
            text("""
                SELECT COUNT(*) AS cnt
                FROM trust_asset_monitor_records
                WHERE data_date = :dd
                  AND last_renovation_payment_date IS NOT NULL
            """),
            {"dd": DATA_DATE},
        ).scalar()

    mode = "dry-run" if args.dry_run else "apply"
    print(
        f"[{mode}] batches={len(batches)} matched={rows_matched} "
        f"with_date={rows_with_date} updated={rows_updated} db_filled={filled}"
    )
    if errors:
        for err in errors[:20]:
            print("ERROR:", err)
        if len(errors) > 20:
            print(f"... and {len(errors) - 20} more errors")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
