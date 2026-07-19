#!/usr/bin/env python3
"""还款明细披露扩展列一次性回填（按 source_file_name + source_sheet_name）。

从 /data/uploads 找回历史上传 Excel，解析扩展列，仅 UPDATE 当前为 NULL 的字段。
不改 actual_repayment_amount / repayment_date / trust_asset_id 等。

用法：
  python scripts/ops/backfill_repayment_template_columns.py --dry-run
  python scripts/ops/backfill_repayment_template_columns.py --apply
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from sqlalchemy import text

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "backend") not in sys.path:
    sys.path.insert(0, str(_REPO / "backend"))
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app import assetinfo_date_rules  # noqa: E402
from app.assetinfo_upload import (  # noqa: E402
    REPAYMENT_OPTIONAL_FIELDS,
    _load_sheet,
    _parse_repayment_rows,
    upload_root,
)
from app.db import get_engine  # noqa: E402

BACKFILL_FIELDS: tuple[str, ...] = (*REPAYMENT_OPTIONAL_FIELDS,)
# period_no：仅当库为空且 Excel 有值时补
OPTIONAL_PERIOD = "period_no"

OUTPUT_DIR = Path("/data/uploads/ops/backfill_repayment_template_columns")


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
    if text_val.endswith(".0") and text_val[:-2].replace("-", "").isdigit():
        # keep hyphenated source codes; only strip .0 on pure numeric
        if text_val[:-2].isdigit():
            text_val = text_val[:-2]
    return text_val


def _norm_amount(value) -> str:
    if value is None:
        return ""
    try:
        d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return format(d, "f")
    except Exception:  # noqa: BLE001
        return str(value)


def _norm_date(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text_val = str(value).strip()
    return text_val[:10] if text_val else ""


def _row_key(row: dict) -> tuple[str, str, str, str, str]:
    return (
        _norm_code(row.get("custody_asset_code")),
        _norm_code(row.get("source_asset_code")),
        _norm_date(row.get("repayment_date")),
        _norm_amount(row.get("actual_repayment_amount")),
        _norm_code(row.get("period_no")) or "",
    )


def _build_update_sql() -> text:
    sets = [f"{field} = COALESCE({field}, :{field})" for field in BACKFILL_FIELDS]
    sets.append(f"{OPTIONAL_PERIOD} = COALESCE({OPTIONAL_PERIOD}, :{OPTIONAL_PERIOD})")
    null_checks = " OR ".join(
        [f"{f} IS NULL" for f in BACKFILL_FIELDS] + [f"{OPTIONAL_PERIOD} IS NULL"]
    )
    return text(f"""
        UPDATE trust_repayment_detail_records
        SET {", ".join(sets)}
        WHERE id = :id
          AND ({null_checks})
    """)


def _baseline(conn) -> dict:
    cols = ", ".join(
        [f"COUNT({f}) AS {f}" for f in BACKFILL_FIELDS] + [f"COUNT({OPTIONAL_PERIOD}) AS {OPTIONAL_PERIOD}"]
    )
    row = conn.execute(
        text(f"""
            SELECT COUNT(*) AS total, {cols}
            FROM trust_repayment_detail_records
        """)
    ).mappings().one()
    return dict(row)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill repayment template columns from uploads")
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
                SELECT trust_product_id, source_file_name, source_sheet_name, COUNT(*) AS cnt
                FROM trust_repayment_detail_records
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

            parsed_date = assetinfo_date_rules.parse_sheet_repayment_date(sheet_name, product_name)
            fallback = parsed_date.parsed_date if parsed_date.ok else None
            rows, parse_errors = _parse_repayment_rows(df, fallback)
            if parse_errors and not rows:
                errors.append(
                    f"product={pid} parse fail {file_name}::{sheet_name}: {parse_errors[:2]}"
                )
                scopes_fail += 1
                continue
            if not rows:
                errors.append(f"product={pid} no rows {file_name}::{sheet_name}")
                scopes_fail += 1
                continue

            db_rows = conn.execute(
                text("""
                    SELECT id, custody_asset_code, source_asset_code, repayment_date,
                           actual_repayment_amount, period_no,
                           asset_pool_code, current_payer, planned_repayment_amount,
                           initial_renovation_amount, cumulative_repaid_amount,
                           remaining_balance
                    FROM trust_repayment_detail_records
                    WHERE trust_product_id = :pid
                      AND source_file_name = :file
                      AND source_sheet_name = :sheet
                """),
                {"pid": pid, "file": file_name, "sheet": sheet_name},
            ).mappings().all()

            by_key: dict[tuple, list] = {}
            by_source_key: dict[tuple, list] = {}
            for db_row in db_rows:
                by_key.setdefault(_row_key(db_row), []).append(db_row)
                src_key = (
                    _norm_code(db_row.get("source_asset_code")),
                    _norm_date(db_row.get("repayment_date")),
                    _norm_amount(db_row.get("actual_repayment_amount")),
                    _norm_code(db_row.get("period_no")) or "",
                )
                by_source_key.setdefault(src_key, []).append(db_row)

            scope_matched = 0
            used_ids: set[int] = set()
            for excel_row in rows:
                key = _row_key(excel_row)
                candidates = [
                    c for c in (by_key.get(key) or [])
                    if int(c["id"]) not in used_ids
                ]
                if not candidates:
                    # DB period 为空、Excel 有期数时
                    key2 = (key[0], key[1], key[2], key[3], "")
                    candidates = [
                        c for c in (by_key.get(key2) or [])
                        if int(c["id"]) not in used_ids
                    ]
                if not candidates:
                    # 托管号历史错挂修复后：仅用 source + 日期 + 金额 + 期数
                    src_key = (
                        _norm_code(excel_row.get("source_asset_code")),
                        _norm_date(excel_row.get("repayment_date")),
                        _norm_amount(excel_row.get("actual_repayment_amount")),
                        _norm_code(excel_row.get("period_no")) or "",
                    )
                    candidates = [
                        c for c in (by_source_key.get(src_key) or [])
                        if int(c["id"]) not in used_ids
                    ]
                    if not candidates and src_key[3]:
                        src_key2 = (src_key[0], src_key[1], src_key[2], "")
                        candidates = [
                            c for c in (by_source_key.get(src_key2) or [])
                            if int(c["id"]) not in used_ids
                        ]
                if not candidates:
                    unmatched += 1
                    if unmatched <= 40:
                        errors.append(
                            f"unmatched product={pid} key={key} file={file_name} sheet={sheet_name}"
                        )
                    continue

                chosen = candidates[0]
                used_ids.add(int(chosen["id"]))
                matched += 1
                scope_matched += 1

                patch = {f: excel_row.get(f) for f in BACKFILL_FIELDS}
                patch[OPTIONAL_PERIOD] = excel_row.get(OPTIONAL_PERIOD)
                need = any(
                    chosen.get(f) is None and patch.get(f) is not None
                    for f in (*BACKFILL_FIELDS, OPTIONAL_PERIOD)
                )
                if not need:
                    continue
                would_update += 1
                report_rows.append({
                    "id": chosen["id"],
                    "trust_product_id": pid,
                    "source_file_name": file_name,
                    "source_sheet_name": sheet_name,
                    "match_key": "|".join(key),
                    "upload_path": str(path),
                    **{f"new_{f}": patch.get(f) for f in (*BACKFILL_FIELDS, OPTIONAL_PERIOD)},
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
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    if scopes_ok == 0:
        return 1
    if args.apply and updated == 0 and would_update > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
