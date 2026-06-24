"""信托产品发行资产明细 — 预检、导入、查询."""

from __future__ import annotations

import json
import os
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import ingestion_cleanse as cleanse
from app import issuance_cleanse as ic
from app import query_utils

AMBIGUOUS_CONFLICT_REASON = "Sheet类型冲突：名称与表头识别结果不一致"
ISSUANCE_FILE_KEYWORDS = ("发行资产", "已发行", "入池", "基础资产清单", "房源明细")
ISSUANCE_SHEET_KEYWORDS = ("发行", "入池", "合同", "资产明细")


def upload_root() -> Path:
    root = Path(os.getenv("INGESTION_UPLOAD_DIR", "/data/uploads")) / "issuance"
    root.mkdir(parents=True, exist_ok=True)
    return root


def batch_dir(batch_uuid: str) -> Path:
    path = upload_root() / batch_uuid
    path.mkdir(parents=True, exist_ok=True)
    return path


def preview_json_path(batch_uuid: str) -> Path:
    return batch_dir(batch_uuid) / "preview.json"


def sheet_key(file_name: str, sheet_name: str) -> str:
    return f"{file_name}::{sheet_name}"


def _load_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet_name, header=0)


def _verify_trust_product(conn: Connection, trust_product_id: int) -> dict:
    row = conn.execute(
        text("SELECT id, name FROM trust_products WHERE id = :id"),
        {"id": trust_product_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"trust_product_id {trust_product_id} not found")
    return {"id": int(row.id), "name": row.name}


def _parse_issue_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    parsed = query_utils.parse_optional_date(value)
    if not parsed:
        raise HTTPException(status_code=400, detail="issue_date 无效")
    return date.fromisoformat(parsed[:10])


def _text_contains_any(text_val: str, keywords: tuple[str, ...]) -> bool:
    return any(k in text_val for k in keywords)


def classify_issuance_sheet(file_name: str, sheet_name: str, df: pd.DataFrame) -> str:
    """返回 issuance_asset | ambiguous_sheet_type | unknown | skip."""
    header_issuance = ic.is_issuance_sheet(df)
    header_monitor = ic.is_monitor_like_sheet(df)
    header_repayment = ic.is_repayment_like_sheet(df)

    if header_issuance and (header_monitor or header_repayment):
        return "ambiguous_sheet_type"

    name_hint = (
        _text_contains_any(file_name, ISSUANCE_FILE_KEYWORDS)
        or _text_contains_any(sheet_name, ISSUANCE_SHEET_KEYWORDS)
    )
    if header_monitor and not header_issuance:
        return "unknown"
    if header_repayment and not header_issuance:
        return "unknown"

    if header_issuance:
        return "issuance_asset"
    if name_hint:
        return "unknown"
    return "unknown"


def _lookup_trust_product_by_name(conn: Connection, name: str | None) -> tuple[int | None, str | None]:
    if not name or not str(name).strip():
        return None, None
    text_name = str(name).strip()
    row = conn.execute(
        text("SELECT id, name FROM trust_products WHERE name = :name LIMIT 1"),
        {"name": text_name},
    ).fetchone()
    if row:
        return int(row.id), row.name
    return None, text_name


def _parse_row(
    row: pd.Series,
    *,
    trust_product_id: int,
    trust_product_name: str,
    issue_date: date,
    file_name: str,
    sheet_name: str,
    source_row_number: int,
    conn: Connection,
    col_map: dict[str, str | None],
) -> tuple[dict | None, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    custody_raw = row[col_map["custody_asset_code"]] if col_map["custody_asset_code"] else None
    custody = cleanse.clean_custody_code(custody_raw)
    if not custody:
        errors.append(f"行{source_row_number}: 缺少托管房源号")
        return None, errors, warnings

    contract_amt, contract_err = ic.to_optional_amount(
        row[col_map["receivable_contract_amount"]], required=True,
    )
    if contract_err:
        errors.append(f"行{source_row_number}: 应收账款合同金额{contract_err}")
        return None, errors, warnings

    transfer_amt, transfer_err = ic.to_optional_amount(
        row[col_map["receivable_transfer_amount"]], required=True,
    )
    if transfer_err:
        errors.append(f"行{source_row_number}: 应收账款转让价款{transfer_err}")
        return None, errors, warnings

    biz_key = ic.build_business_asset_key(trust_product_id, issue_date, custody)

    from_col = col_map.get("from_trust_product_name")
    from_raw = row[from_col] if from_col else None
    from_name = str(from_raw).strip() if from_raw is not None and not pd.isna(from_raw) else None
    if from_name == "":
        from_name = None
    from_pid, from_pname = _lookup_trust_product_by_name(conn, from_name)
    if from_name and from_pid is None:
        warnings.append(f"行{source_row_number}: 转出信托产品「{from_name}」未匹配到 trust_products")

    mig_col = col_map.get("migration_type")
    mig_col_present = mig_col is not None
    mig_excel_val: str | None = None
    if mig_col_present:
        mig_raw = row[mig_col]
        if mig_raw is None or (isinstance(mig_raw, float) and pd.isna(mig_raw)):
            mig_excel_val = ""
        else:
            mig_excel_val = str(mig_raw).strip()
    migration_type, mig_warnings = ic.resolve_migration_type(
        excel_column_present=mig_col_present,
        excel_value=mig_excel_val,
        from_trust_product_id=from_pid,
        source_row_number=source_row_number,
    )
    warnings.extend(mig_warnings)

    def opt_amount(field: str) -> float | None:
        col = col_map.get(field)
        if not col:
            return None
        val = row[col]
        if cleanse.is_excel_error(val):
            warnings.append(f"行{source_row_number}: {field} 含 Excel 错误值，已置空")
            return None
        return cleanse.to_numeric_value(val)

    def opt_rate(field: str) -> float | None:
        col = col_map.get(field)
        if not col:
            return None
        val = row[col]
        if cleanse.is_excel_error(val):
            warnings.append(f"行{source_row_number}: {field} 含 Excel 错误值，已置空")
            return None
        return ic.to_rate_value(val)

    def opt_date(field: str) -> date | None:
        col = col_map.get(field)
        if not col:
            return None
        val = row[col]
        if cleanse.is_excel_error(val):
            warnings.append(f"行{source_row_number}: {field} 含 Excel 错误值，已置空")
            return None
        return ic.to_optional_date(val)

    def opt_str(field: str) -> str | None:
        col = col_map.get(field)
        if not col:
            return None
        val = row[col]
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        text_val = str(val).strip()
        return text_val or None

    periods_col = col_map.get("withholding_periods_at_pooling")
    periods = None
    if periods_col:
        periods = ic.to_int_value(row[periods_col])

    parsed = {
        "trust_product_id": trust_product_id,
        "trust_product_name": trust_product_name,
        "from_trust_product_id": from_pid,
        "from_trust_product_name": from_pname,
        "migration_type": migration_type,
        "trust_asset_id": None,
        "issue_date": issue_date,
        "business_asset_key": biz_key,
        "custody_asset_code": custody,
        "issuance_weight": None,
        "migration_reason": None,
        "contract_name": opt_str("contract_name"),
        "debtor_name": opt_str("debtor_name"),
        "property_address": opt_str("property_address"),
        "city": opt_str("city"),
        "contractor_name": opt_str("contractor_name"),
        "receivable_contract_amount": contract_amt,
        "asset_transfer_discount_rate": opt_rate("asset_transfer_discount_rate"),
        "receivable_transfer_amount": transfer_amt,
        "min_institution_transferable_amount": opt_amount("min_institution_transferable_amount"),
        "remaining_unpaid_amount_beike_not_withheld": opt_amount(
            "remaining_unpaid_amount_beike_not_withheld"
        ),
        "rental_price": opt_amount("rental_price"),
        "total_rent_withholding_amount": opt_amount("total_rent_withholding_amount"),
        "rent_withheld_amount_before_pooling": opt_amount("rent_withheld_amount_before_pooling"),
        "withholding_periods_at_pooling": periods,
        "initial_expected_withholding_cycle": opt_str("initial_expected_withholding_cycle"),
        "renovation_payment_method": opt_str("renovation_payment_method"),
        "rent_withholding_ratio": opt_rate("rent_withholding_ratio"),
        "calculated_rent_withholding_per_period": opt_amount(
            "calculated_rent_withholding_per_period"
        ),
        "first_rent_withholding_date": opt_date("first_rent_withholding_date"),
        "signing_date": opt_date("signing_date"),
        "rental_contract_end_date": opt_date("rental_contract_end_date"),
        "source_file_name": file_name,
        "source_sheet_name": sheet_name,
        "source_row_number": source_row_number,
    }
    return parsed, errors, warnings


def parse_issuance_sheet(
    conn: Connection,
    df: pd.DataFrame,
    *,
    trust_product_id: int,
    trust_product_name: str,
    issue_date: date,
    file_name: str,
    sheet_name: str,
) -> tuple[list[dict], list[str], list[str]]:
    col_map = {key: ic.pick_column(df, key) for key in ic.COL_ALIASES}
    rows: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = []
    for idx, row in df.iterrows():
        parsed, row_errors, row_warnings = _parse_row(
            row,
            trust_product_id=trust_product_id,
            trust_product_name=trust_product_name,
            issue_date=issue_date,
            file_name=file_name,
            sheet_name=sheet_name,
            source_row_number=int(idx) + 2,
            conn=conn,
            col_map=col_map,
        )
        errors.extend(row_errors)
        warnings.extend(row_warnings)
        if parsed:
            rows.append(parsed)
    return rows, errors, warnings


def _scope_stats(
    conn: Connection,
    trust_product_id: int,
    issue_date: date,
    file_name: str,
    sheet_name: str,
) -> tuple[int, float]:
    row = conn.execute(
        text("""
            SELECT COUNT(*) AS cnt,
                   COALESCE(SUM(receivable_transfer_amount), 0) AS amount_sum
            FROM trust_product_issuance_asset_records
            WHERE trust_product_id = :pid
              AND issue_date = :issue_date
              AND source_file_name = :file
              AND source_sheet_name = :sheet
        """),
        {
            "pid": trust_product_id,
            "issue_date": issue_date,
            "file": file_name,
            "sheet": sheet_name,
        },
    ).fetchone()
    return int(row.cnt), float(row.amount_sum)


def _cross_file_conflicts(
    conn: Connection,
    trust_product_id: int,
    issue_date: date,
    file_name: str,
    sheet_name: str,
    rows: list[dict],
) -> tuple[int, int, list[dict]]:
    if not rows:
        return 0, 0, []
    keys = list({r["business_asset_key"] for r in rows})
    existing = conn.execute(
        text("""
            SELECT business_asset_key, custody_asset_code,
                   source_file_name, source_sheet_name,
                   receivable_contract_amount, receivable_transfer_amount
            FROM trust_product_issuance_asset_records
            WHERE trust_product_id = :pid
              AND issue_date = :issue_date
              AND NOT (source_file_name = :file AND source_sheet_name = :sheet)
              AND business_asset_key = ANY(:keys)
        """),
        {
            "pid": trust_product_id,
            "issue_date": issue_date,
            "file": file_name,
            "sheet": sheet_name,
            "keys": keys,
        },
    )
    by_key: dict[str, list] = {}
    for r in existing:
        by_key.setdefault(r.business_asset_key, []).append(r)

    incoming_by_key = {r["business_asset_key"]: r for r in rows}
    duplicate_keys: set[str] = set()
    conflict_keys: set[str] = set()
    samples: list[dict] = []

    for key in keys:
        if key not in by_key:
            continue
        duplicate_keys.add(key)
        inc = incoming_by_key[key]
        for ex in by_key[key]:
            amount_conflict = (
                not cleanse.amounts_equal(
                    float(ex.receivable_contract_amount), inc["receivable_contract_amount"]
                )
                or not cleanse.amounts_equal(
                    float(ex.receivable_transfer_amount), inc["receivable_transfer_amount"]
                )
            )
            if amount_conflict:
                conflict_keys.add(key)
            if len(samples) < 20:
                samples.append({
                    "business_asset_key": key,
                    "custody_asset_code": inc["custody_asset_code"],
                    "current_file": file_name,
                    "current_sheet": sheet_name,
                    "current_contract_amount": inc["receivable_contract_amount"],
                    "current_transfer_amount": inc["receivable_transfer_amount"],
                    "existing_file": ex.source_file_name,
                    "existing_sheet": ex.source_sheet_name,
                    "existing_contract_amount": float(ex.receivable_contract_amount),
                    "existing_transfer_amount": float(ex.receivable_transfer_amount),
                    "amount_conflict": amount_conflict,
                })

    return len(duplicate_keys), len(conflict_keys), samples


def _has_other_sources(
    conn: Connection,
    trust_product_id: int,
    issue_date: date,
    file_name: str,
    sheet_name: str,
) -> bool:
    row = conn.execute(
        text("""
            SELECT EXISTS (
                SELECT 1 FROM trust_product_issuance_asset_records
                WHERE trust_product_id = :pid
                  AND issue_date = :issue_date
                  AND (source_file_name != :file OR source_sheet_name != :sheet)
            ) AS ex
        """),
        {
            "pid": trust_product_id,
            "issue_date": issue_date,
            "file": file_name,
            "sheet": sheet_name,
        },
    ).fetchone()
    return bool(row.ex)


def _within_sheet_checks(rows: list[dict]) -> tuple[int, int, list[str]]:
    warnings: list[str] = []
    key_counts = Counter(r["business_asset_key"] for r in rows)
    within_key_dupes = sum(1 for k, c in key_counts.items() if c > 1)
    if within_key_dupes:
        warnings.append(
            f"同一 Sheet 中存在 {within_key_dupes} 个发行资产标识多行记录，"
            "请确认是否为多笔资产。"
        )

    fp_counts = Counter(ic.exact_duplicate_fingerprint(r) for r in rows)
    exact_dupes = sum(1 for _, c in fp_counts.items() if c > 1)
    if exact_dupes:
        warnings.append(
            f"同一 Sheet 中存在 {exact_dupes} 组完全重复业务行，请确认后导入。"
        )
    return within_key_dupes, exact_dupes, warnings


def precheck_issuance_sheet(
    conn: Connection,
    trust_product_id: int,
    product_name: str,
    issue_date: date,
    file_name: str,
    sheet_name: str,
    df: pd.DataFrame,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "file_name": file_name,
        "sheet_name": sheet_name,
        "sheet_type": "issuance_asset",
        "issue_date": str(issue_date),
        "row_count": 0,
        "amount_sum": 0.0,
        "existing_scope_count": 0,
        "existing_scope_amount_sum": 0.0,
        "cross_file_duplicate_count": 0,
        "cross_file_conflict_count": 0,
        "within_sheet_duplicate_count": 0,
        "warning_count": 0,
        "error_count": 0,
        "action": "failed",
        "reason": "",
        "warnings": [],
        "errors": [],
        "conflict_samples": [],
        "importable": False,
    }

    if not trust_product_id:
        result["reason"] = "未选择信托产品"
        return result
    if not file_name:
        result["reason"] = "缺少来源文件名"
        return result
    if not sheet_name:
        result["reason"] = "缺少 Sheet 名"
        return result

    sheet_type = classify_issuance_sheet(file_name, sheet_name, df)
    if sheet_type == "ambiguous_sheet_type":
        result["sheet_type"] = sheet_type
        result["reason"] = AMBIGUOUS_CONFLICT_REASON
        return result
    if sheet_type != "issuance_asset":
        missing = ic.issuance_sheet_missing_core(df)
        result["reason"] = (
            "无法识别为发行资产明细 Sheet"
            + (f"；缺少：{'、'.join(missing)}" if missing else "")
        )
        return result

    rows, parse_errors, parse_warnings = parse_issuance_sheet(
        conn, df,
        trust_product_id=trust_product_id,
        trust_product_name=product_name,
        issue_date=issue_date,
        file_name=file_name,
        sheet_name=sheet_name,
    )
    result["errors"].extend(parse_errors)
    result["warnings"].extend(parse_warnings)
    result["error_count"] = len(parse_errors)
    result["warning_count"] = len(parse_warnings)

    if parse_errors:
        result["reason"] = parse_errors[0]
        return result
    if not rows:
        result["reason"] = "无有效数据行"
        return result

    within_key_dupes, exact_dupes, ws_warnings = _within_sheet_checks(rows)
    result["within_sheet_duplicate_count"] = within_key_dupes
    result["warnings"].extend(ws_warnings)
    result["warning_count"] = len(result["warnings"])

    amount_sum = sum(r["receivable_transfer_amount"] for r in rows)
    result["row_count"] = len(rows)
    result["amount_sum"] = amount_sum

    scope_cnt, scope_sum = _scope_stats(
        conn, trust_product_id, issue_date, file_name, sheet_name,
    )
    result["existing_scope_count"] = scope_cnt
    result["existing_scope_amount_sum"] = scope_sum

    dup_cnt, conflict_cnt, samples = _cross_file_conflicts(
        conn, trust_product_id, issue_date, file_name, sheet_name, rows,
    )
    result["cross_file_duplicate_count"] = dup_cnt
    result["cross_file_conflict_count"] = conflict_cnt
    result["conflict_samples"] = samples

    action = "import"
    reasons: list[str] = []

    if scope_cnt > 0:
        action = "overwrite"
        reasons.append(
            f"将覆盖当前来源 {file_name} / {sheet_name} 的 {scope_cnt} 行旧数据"
        )

    if dup_cnt > 0 or conflict_cnt > 0 or exact_dupes > 0:
        action = "needs_confirm"
        if dup_cnt:
            reasons.append(f"跨文件相同 business_asset_key {dup_cnt} 个")
        if conflict_cnt:
            reasons.append(f"跨文件金额冲突 {conflict_cnt} 个")
        if exact_dupes:
            reasons.append(f"Sheet 内完全重复行 {exact_dupes} 组")

    if _has_other_sources(conn, trust_product_id, issue_date, file_name, sheet_name):
        if dup_cnt == 0:
            result["warnings"].append(
                "该产品该发行日已有其他来源发行数据，本次资产不重叠，将作为新增来源导入。"
            )
            result["warning_count"] = len(result["warnings"])

    result["action"] = action
    result["importable"] = action in ("import", "overwrite", "needs_confirm")
    result["reason"] = "<br>".join(reasons) if reasons else "可导入"
    return result


def delete_scope(
    conn: Connection,
    trust_product_id: int,
    issue_date: date,
    file_name: str,
    sheet_name: str,
) -> int:
    result = conn.execute(
        text("""
            DELETE FROM trust_product_issuance_asset_records
            WHERE trust_product_id = :pid
              AND issue_date = :issue_date
              AND source_file_name = :file
              AND source_sheet_name = :sheet
        """),
        {
            "pid": trust_product_id,
            "issue_date": issue_date,
            "file": file_name,
            "sheet": sheet_name,
        },
    )
    return int(result.rowcount or 0)


def import_issuance_sheet(
    conn: Connection,
    trust_product_id: int,
    product_name: str,
    issue_date: date,
    file_name: str,
    sheet_name: str,
    df: pd.DataFrame,
) -> tuple[int, int]:
    rows, errors, _ = parse_issuance_sheet(
        conn, df,
        trust_product_id=trust_product_id,
        trust_product_name=product_name,
        issue_date=issue_date,
        file_name=file_name,
        sheet_name=sheet_name,
    )
    if errors:
        raise HTTPException(status_code=400, detail=errors[0])
    if not rows:
        raise HTTPException(status_code=400, detail="无有效数据行")

    deleted = delete_scope(conn, trust_product_id, issue_date, file_name, sheet_name)

    insert_sql = text("""
        INSERT INTO trust_product_issuance_asset_records (
            trust_product_id, trust_product_name,
            from_trust_product_id, from_trust_product_name, migration_type,
            trust_asset_id, issue_date, business_asset_key, custody_asset_code,
            issuance_weight, migration_reason,
            contract_name, debtor_name, property_address, city, contractor_name,
            receivable_contract_amount, asset_transfer_discount_rate,
            receivable_transfer_amount, min_institution_transferable_amount,
            remaining_unpaid_amount_beike_not_withheld, rental_price,
            total_rent_withholding_amount, rent_withheld_amount_before_pooling,
            withholding_periods_at_pooling, initial_expected_withholding_cycle,
            renovation_payment_method, rent_withholding_ratio,
            calculated_rent_withholding_per_period,
            first_rent_withholding_date, signing_date, rental_contract_end_date,
            source_file_name, source_sheet_name, source_row_number
        ) VALUES (
            :trust_product_id, :trust_product_name,
            :from_trust_product_id, :from_trust_product_name, :migration_type,
            :trust_asset_id, :issue_date, :business_asset_key, :custody_asset_code,
            :issuance_weight, :migration_reason,
            :contract_name, :debtor_name, :property_address, :city, :contractor_name,
            :receivable_contract_amount, :asset_transfer_discount_rate,
            :receivable_transfer_amount, :min_institution_transferable_amount,
            :remaining_unpaid_amount_beike_not_withheld, :rental_price,
            :total_rent_withholding_amount, :rent_withheld_amount_before_pooling,
            :withholding_periods_at_pooling, :initial_expected_withholding_cycle,
            :renovation_payment_method, :rent_withholding_ratio,
            :calculated_rent_withholding_per_period,
            :first_rent_withholding_date, :signing_date, :rental_contract_end_date,
            :source_file_name, :source_sheet_name, :source_row_number
        )
    """)
    for row in rows:
        params = dict(row)
        params["issue_date"] = issue_date
        conn.execute(insert_sql, params)
    conn.commit()
    return len(rows), deleted


def record_import_run(
    conn: Connection,
    *,
    trust_product_id: int,
    trust_product_name: str,
    issue_date: date,
    source_file: str,
    created_by: int,
    inserted_row_count: int,
    deleted_row_count: int,
    skipped_sheet_count: int,
    failed_sheet_count: int,
    error_message: str | None,
    sheet_results: list[dict],
) -> int:
    row = conn.execute(
        text("""
            INSERT INTO issuance_import_runs (
                trust_product_id, trust_product_name, issue_date, source_file,
                created_by, inserted_row_count, deleted_row_count,
                skipped_sheet_count, failed_sheet_count, error_message
            ) VALUES (
                :trust_product_id, :trust_product_name, :issue_date, :source_file,
                :created_by, :inserted_row_count, :deleted_row_count,
                :skipped_sheet_count, :failed_sheet_count, :error_message
            )
            RETURNING id
        """),
        {
            "trust_product_id": trust_product_id,
            "trust_product_name": trust_product_name,
            "issue_date": issue_date,
            "source_file": source_file,
            "created_by": created_by,
            "inserted_row_count": inserted_row_count,
            "deleted_row_count": deleted_row_count,
            "skipped_sheet_count": skipped_sheet_count,
            "failed_sheet_count": failed_sheet_count,
            "error_message": error_message,
        },
    ).fetchone()
    run_id = int(row.id)
    for sr in sheet_results:
        conn.execute(
            text("""
                INSERT INTO issuance_import_sheet_runs (
                    import_run_id, trust_product_id, trust_product_name, issue_date,
                    source_file_name, source_sheet_name, sheet_type,
                    row_count, amount_sum, action, message
                ) VALUES (
                    :import_run_id, :trust_product_id, :trust_product_name, :issue_date,
                    :source_file_name, :source_sheet_name, :sheet_type,
                    :row_count, :amount_sum, :action, :message
                )
            """),
            {
                "import_run_id": run_id,
                "trust_product_id": trust_product_id,
                "trust_product_name": trust_product_name,
                "issue_date": issue_date,
                "source_file_name": sr.get("file_name"),
                "source_sheet_name": sr.get("sheet_name"),
                "sheet_type": sr.get("sheet_type", "issuance_asset"),
                "row_count": sr.get("row_count", 0),
                "amount_sum": sr.get("amount_sum"),
                "action": sr.get("final_action") or sr.get("action"),
                "message": sr.get("reason"),
            },
        )
    conn.commit()
    return run_id


async def save_batch_files(batch_uuid: str, files: list[UploadFile]) -> list[str]:
    saved: list[str] = []
    dest = batch_dir(batch_uuid)
    for uf in files:
        if not uf.filename or not uf.filename.lower().endswith((".xlsx", ".xls")):
            raise HTTPException(status_code=400, detail=f"不支持的文件: {uf.filename}")
        safe_name = Path(uf.filename).name
        path = dest / safe_name
        content = await uf.read()
        path.write_bytes(content)
        saved.append(safe_name)
    return saved


def enrich_preview_sheet(sheet: dict, batch_uuid: str) -> dict:
    action = sheet.get("action", "failed")
    return {
        **sheet,
        "file_id": batch_uuid,
        "batch_uuid": batch_uuid,
        "sheet_key": sheet_key(sheet["file_name"], sheet["sheet_name"]),
        "type": sheet.get("sheet_type"),
        "rows": sheet.get("row_count", 0),
        "amount": sheet.get("amount_sum"),
        "status": action,
        "selectable": action in ("import", "overwrite", "needs_confirm"),
    }


def run_preview(
    conn: Connection,
    trust_product_id: int,
    issue_date: date,
    batch_uuid: str,
    file_names: list[str],
) -> dict[str, Any]:
    product = _verify_trust_product(conn, trust_product_id)
    product_name = product["name"]
    sheets: list[dict] = []

    for file_name in file_names:
        path = batch_dir(batch_uuid) / file_name
        if not path.exists():
            raise HTTPException(status_code=400, detail=f"文件不存在: {file_name}")
        xl = pd.ExcelFile(path)
        for sheet_name in xl.sheet_names:
            df = _load_sheet(path, sheet_name)
            if df.empty:
                continue
            st = classify_issuance_sheet(file_name, sheet_name, df)
            if st == "ambiguous_sheet_type":
                sheets.append({
                    "file_name": file_name,
                    "sheet_name": sheet_name,
                    "sheet_type": st,
                    "action": "failed",
                    "importable": False,
                    "reason": AMBIGUOUS_CONFLICT_REASON,
                })
                continue
            if st != "issuance_asset":
                sheets.append({
                    "file_name": file_name,
                    "sheet_name": sheet_name,
                    "sheet_type": "unknown",
                    "action": "failed",
                    "importable": False,
                    "reason": "无法识别为发行资产明细 Sheet",
                })
                continue
            sheets.append(precheck_issuance_sheet(
                conn, trust_product_id, product_name, issue_date,
                file_name, sheet_name, df,
            ))

    payload = {
        "file_id": batch_uuid,
        "batch_uuid": batch_uuid,
        "trust_product_id": trust_product_id,
        "trust_product_name": product_name,
        "issue_date": str(issue_date),
        "files": file_names,
        "sheets": [enrich_preview_sheet(s, batch_uuid) for s in sheets],
    }
    preview_json_path(batch_uuid).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return payload


def _resolve_selected_sheet_keys(
    preview: dict,
    selected_sheet_keys: list[str] | None,
) -> set[str]:
    if not selected_sheet_keys:
        return {
            sheet_key(s["file_name"], s["sheet_name"])
            for s in preview.get("sheets", [])
            if s.get("importable")
        }
    return {k.strip() for k in selected_sheet_keys if k and str(k).strip()}


def run_import(
    conn: Connection,
    batch_uuid: str,
    trust_product_id: int,
    issue_date: date,
    user_id: int,
    selected_sheet_keys: list[str] | None = None,
    confirm_sheet_keys: list[str] | None = None,
) -> dict[str, Any]:
    preview_path = preview_json_path(batch_uuid)
    if not preview_path.exists():
        raise HTTPException(status_code=400, detail="预检结果不存在，请先 preview")

    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    if int(preview["trust_product_id"]) != trust_product_id:
        raise HTTPException(status_code=400, detail="trust_product_id 与预检不一致")
    preview_issue = _parse_issue_date(preview["issue_date"])
    if preview_issue != issue_date:
        raise HTTPException(status_code=400, detail="issue_date 与预检不一致")

    product_name = preview["trust_product_name"]
    selected = _resolve_selected_sheet_keys(preview, selected_sheet_keys)
    confirm_set = set(confirm_sheet_keys or [])

    if not selected:
        raise HTTPException(status_code=400, detail="必须选择至少一个 Sheet")

    inserted_total = 0
    deleted_total = 0
    skipped = 0
    failed = 0
    sheet_results: list[dict] = []

    for sheet in preview["sheets"]:
        action = sheet.get("action")
        key = sheet_key(sheet["file_name"], sheet["sheet_name"])
        file_name = sheet["file_name"]
        sheet_name = sheet["sheet_name"]

        if key not in selected:
            skipped += 1
            sheet_results.append({**sheet, "final_action": "not_selected"})
            continue

        if action == "failed":
            failed += 1
            sheet_results.append({**sheet, "final_action": "failed"})
            continue

        if action == "needs_confirm" and key not in confirm_set:
            failed += 1
            sheet_results.append({
                **sheet,
                "final_action": "failed",
                "reason": "未确认人工导入",
            })
            continue

        path = batch_dir(batch_uuid) / file_name
        df = _load_sheet(path, sheet_name)
        try:
            ins, deleted = import_issuance_sheet(
                conn, trust_product_id, product_name, issue_date,
                file_name, sheet_name, df,
            )
            inserted_total += ins
            deleted_total += deleted
            final = "overwritten" if action == "overwrite" else "imported"
            sheet_results.append({**sheet, "final_action": final, "inserted": ins, "deleted": deleted})
        except Exception as exc:
            failed += 1
            sheet_results.append({**sheet, "final_action": "failed", "reason": str(exc)})

    source_file = ",".join(preview.get("files") or [])
    record_import_run(
        conn,
        trust_product_id=trust_product_id,
        trust_product_name=product_name,
        issue_date=issue_date,
        source_file=source_file,
        created_by=user_id,
        inserted_row_count=inserted_total,
        deleted_row_count=deleted_total,
        skipped_sheet_count=skipped,
        failed_sheet_count=failed,
        error_message=None if failed == 0 else f"{failed} sheet(s) failed",
        sheet_results=sheet_results,
    )

    return {
        "batch_uuid": batch_uuid,
        "trust_product_id": trust_product_id,
        "issue_date": str(issue_date),
        "inserted": inserted_total,
        "deleted": deleted_total,
        "skipped": skipped,
        "failed": failed,
        "sheets": sheet_results,
    }


def build_record_filters(
    *,
    trust_product_id: str | int | None = None,
    trust_product_name: str | None = None,
    from_trust_product_id: str | int | None = None,
    from_trust_product_name: str | None = None,
    issue_date: str | None = None,
    custody_asset_code: str | None = None,
    business_asset_key: str | None = None,
    city: str | None = None,
    source_file_name: str | None = None,
    source_sheet_name: str | None = None,
    migration_type: str | None = None,
) -> dict[str, Any]:
    cleaned_migration = query_utils.clean_optional_str(migration_type)
    if cleaned_migration and cleaned_migration not in ic.MIGRATION_TYPES:
        cleaned_migration = None
    return {
        "trust_product_id": query_utils.parse_optional_int(trust_product_id),
        "trust_product_name": query_utils.clean_optional_str(trust_product_name),
        "from_trust_product_id": query_utils.parse_optional_int(from_trust_product_id),
        "from_trust_product_name": query_utils.clean_optional_str(from_trust_product_name),
        "issue_date": query_utils.parse_optional_date(issue_date),
        "custody_asset_code": query_utils.clean_optional_str(custody_asset_code),
        "business_asset_key": query_utils.clean_optional_str(business_asset_key),
        "city": query_utils.clean_optional_str(city),
        "source_file_name": query_utils.clean_optional_str(source_file_name),
        "source_sheet_name": query_utils.clean_optional_str(source_sheet_name),
        "migration_type": cleaned_migration,
    }


ISSUANCE_COLUMN_ORDER = (
    "id",
    "trust_product_id",
    "trust_product_name",
    "from_trust_product_id",
    "from_trust_product_name",
    "migration_type",
    "issue_date",
    "business_asset_key",
    "custody_asset_code",
    "receivable_contract_amount",
    "receivable_transfer_amount",
    "contract_name",
    "debtor_name",
    "property_address",
    "city",
    "source_file_name",
    "source_sheet_name",
    "source_row_number",
    "created_at",
    "updated_at",
)

ISSUANCE_NUMERIC_COLUMNS = frozenset({
    "id",
    "trust_product_id",
    "from_trust_product_id",
    "receivable_contract_amount",
    "receivable_transfer_amount",
    "min_institution_transferable_amount",
    "remaining_unpaid_amount_beike_not_withheld",
    "rental_price",
    "total_rent_withholding_amount",
    "rent_withheld_amount_before_pooling",
    "calculated_rent_withholding_per_period",
    "asset_transfer_discount_rate",
    "rent_withholding_ratio",
    "issuance_weight",
})

ISSUANCE_DATE_COLUMNS = frozenset({
    "issue_date",
    "first_rent_withholding_date",
    "signing_date",
    "rental_contract_end_date",
})


def fetch_paginated_records(
    conn: Connection,
    page: int,
    page_size: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    offset = (page - 1) * page_size

    where_parts = ["1=1"]
    params: dict[str, Any] = {"limit": page_size, "offset": offset}

    exact_keys = {
        "trust_product_id": "int",
        "from_trust_product_id": "int",
        "issue_date": "date",
        "trust_product_name": "str",
        "from_trust_product_name": "str",
        "custody_asset_code": "str",
        "business_asset_key": "str",
        "city": "str",
        "source_file_name": "str",
        "source_sheet_name": "str",
        "migration_type": "str",
    }
    for key, kind in exact_keys.items():
        val = filters.get(key)
        if val is not None and val != "":
            where_parts.append(f"r.{key} = :{key}")
            params[key] = val

    where_sql = " AND ".join(where_parts)
    count_row = conn.execute(
        text(f"""
            SELECT COUNT(*) AS cnt
            FROM trust_product_issuance_asset_records r
            WHERE {where_sql}
        """),
        params,
    ).fetchone()
    total = int(count_row.cnt)

    rows = conn.execute(
        text(f"""
            SELECT r.*
            FROM trust_product_issuance_asset_records r
            WHERE {where_sql}
            ORDER BY r.issue_date DESC, r.custody_asset_code ASC, r.id ASC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )

    items = []
    for row in rows:
        item = dict(row._mapping)
        for k, v in item.items():
            if hasattr(v, "isoformat"):
                item[k] = str(v)
            elif isinstance(v, float) or (
                hasattr(v, "__float__") and k in ISSUANCE_NUMERIC_COLUMNS
            ):
                try:
                    item[k] = float(v)
                except (TypeError, ValueError):
                    pass
        items.append(item)

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": items,
    }
