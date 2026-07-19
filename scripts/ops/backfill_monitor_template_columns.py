#!/usr/bin/env python3
"""监控表模版扩展列一次性回填（按 source_file_name + source_sheet_name）。

从 /data/uploads 找回历史上传 Excel，解析模版扩展列，仅 UPDATE 当前为 NULL 的字段。
不改金额 / 逾期 / 风险等计算字段。

用法（容器内或本机带 DATABASE_URL）：
  python scripts/ops/backfill_monitor_template_columns.py --dry-run
  python scripts/ops/backfill_monitor_template_columns.py --apply
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "backend") not in sys.path:
    sys.path.insert(0, str(_REPO / "backend"))
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app.assetinfo_upload import (  # noqa: E402
    MONITOR_OPTIONAL_FIELDS,
    _load_sheet,
    _parse_monitor_rows,
    upload_root,
)
from app.db import get_engine  # noqa: E402

BACKFILL_FIELDS: tuple[str, ...] = (
    *MONITOR_OPTIONAL_FIELDS,
    "last_renovation_payment_date",
)

OUTPUT_DIR = Path("/data/uploads/ops/backfill_monitor_template_columns")


def _find_upload_file(file_name: str) -> Path | None:
    root = upload_root()
    matches = list(root.rglob(file_name))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def _norm_code(value) -> str:
    if value is None:
        return ""
    text_val = str(value).strip()
    if text_val.endswith(".0") and text_val[:-2].isdigit():
        text_val = text_val[:-2]
    return text_val


def _custody_key(row: dict) -> str:
    return _norm_code(row.get("custody_asset_code") or row.get("asset_code") or "")


def _build_update_sql() -> text:
    sets = []
    for field in BACKFILL_FIELDS:
        sets.append(f"{field} = COALESCE({field}, :{field})")
    return text(f"""
        UPDATE trust_asset_monitor_records
        SET {", ".join(sets)}
        WHERE id = :id
          AND (
            {" OR ".join(f"{f} IS NULL" for f in BACKFILL_FIELDS)}
          )
    """)


def _baseline(conn) -> dict:
    row = conn.execute(
        text(f"""
            SELECT
              COUNT(*) AS total,
              {", ".join(f"COUNT({f}) AS {f}" for f in BACKFILL_FIELDS)}
            FROM trust_asset_monitor_records
        """)
    ).mappings().one()
    return dict(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill monitor template columns from uploads")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    engine = get_engine()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = OUTPUT_DIR / f"{'dry_run' if args.dry_run else 'apply'}_{ts}.csv"
    summary_path = OUTPUT_DIR / f"{'dry_run' if args.dry_run else 'apply'}_{ts}_summary.json"

    errors: list[str] = []
    unmatched = 0
    matched = 0
    would_update = 0
    updated = 0
    scopes_ok = 0
    scopes_fail = 0
    report_rows: list[dict] = []

    update_sql = _build_update_sql()

    with engine.begin() as conn:
        before = _baseline(conn)
        products = {
            int(r.id): str(r.name)
            for r in conn.execute(text("SELECT id, name FROM trust_products"))
        }
        scopes = conn.execute(
            text("""
                SELECT trust_product_id, source_file_name, source_sheet_name,
                       COUNT(*) AS cnt, MIN(data_date) AS data_date
                FROM trust_asset_monitor_records
                GROUP BY 1, 2, 3
                ORDER BY 1, 2, 3
            """)
        ).mappings().all()

        for scope in scopes:
            pid = int(scope["trust_product_id"])
            file_name = str(scope["source_file_name"])
            sheet_name = str(scope["source_sheet_name"])
            product_name = products.get(pid, "")
            path = _find_upload_file(file_name)
            if path is None:
                errors.append(f"product={pid} file missing: {file_name}")
                scopes_fail += 1
                continue

            try:
                df = _load_sheet(path, sheet_name)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"product={pid} load fail {file_name}::{sheet_name}: {exc}")
                scopes_fail += 1
                continue

            parsed = _parse_monitor_rows(
                df,
                file_name=file_name,
                sheet_name=sheet_name,
                product_name=product_name,
            )
            if not parsed.rows:
                errors.append(
                    f"product={pid} no parsed rows {file_name}::{sheet_name} "
                    f"errors={parsed.errors[:3]}"
                )
                scopes_fail += 1
                continue

            db_rows = conn.execute(
                text("""
                    SELECT id, custody_asset_code, asset_code, source_asset_code, data_date,
                           asset_pool_code, renovation_vendor, asset_status, community_name,
                           city, collection_contract_code, custody_agreement_sign_date,
                           collection_contract_years, owner_code, withholding_ratio,
                           actual_monthly_rent, last_renovation_payment_date
                    FROM trust_asset_monitor_records
                    WHERE trust_product_id = :pid
                      AND source_file_name = :file
                      AND source_sheet_name = :sheet
                """),
                {"pid": pid, "file": file_name, "sheet": sheet_name},
            ).mappings().all()
            by_custody: dict[str, list] = {}
            for db_row in db_rows:
                key = _custody_key(db_row)
                by_custody.setdefault(key, []).append(db_row)

            scope_matched = 0
            for excel_row in parsed.rows:
                key = _custody_key(excel_row)
                candidates = by_custody.get(key) or []
                if not candidates:
                    unmatched += 1
                    if unmatched <= 50:
                        errors.append(
                            f"unmatched product={pid} custody={key} file={file_name}"
                        )
                    continue
                # 同托管号多行时按 data_date 再筛
                excel_date = excel_row.get("data_date") or parsed.batch_date
                chosen = None
                for cand in candidates:
                    if excel_date and cand["data_date"] and str(cand["data_date"])[:10] == str(excel_date)[:10]:
                        chosen = cand
                        break
                if chosen is None:
                    chosen = candidates[0]

                matched += 1
                scope_matched += 1
                patch = {f: excel_row.get(f) for f in BACKFILL_FIELDS}
                need = any(chosen.get(f) is None and patch.get(f) is not None for f in BACKFILL_FIELDS)
                if need:
                    would_update += 1
                    report_rows.append({
                        "id": chosen["id"],
                        "trust_product_id": pid,
                        "source_file_name": file_name,
                        "source_sheet_name": sheet_name,
                        "custody_asset_code": key,
                        "upload_path": str(path),
                        **{f"new_{f}": patch.get(f) for f in BACKFILL_FIELDS},
                    })
                    if args.apply:
                        params = {"id": chosen["id"], **patch}
                        result = conn.execute(update_sql, params)
                        updated += result.rowcount

            if scope_matched:
                scopes_ok += 1
            else:
                scopes_fail += 1
                errors.append(f"product={pid} zero matches {file_name}::{sheet_name}")

        after = _baseline(conn) if args.apply else before

    with report_path.open("w", encoding="utf-8", newline="") as fh:
        if report_rows:
            writer = csv.DictWriter(fh, fieldnames=list(report_rows[0].keys()))
            writer.writeheader()
            writer.writerows(report_rows)
        else:
            fh.write("no_rows\n")

    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "scopes_total": len(scopes),
        "scopes_ok": scopes_ok,
        "scopes_fail": scopes_fail,
        "matched": matched,
        "unmatched": unmatched,
        "would_update": would_update,
        "updated": updated,
        "before": before,
        "after": after,
        "errors_head": errors[:40],
        "error_count": len(errors),
        "report_csv": str(report_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    if args.apply and updated == 0 and would_update > 0:
        return 1
    if scopes_ok == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
