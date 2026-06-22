"""Excel 导入 V2 — 预检、导入、分页查询."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import ingestion_cleanse as cleanse
from app import ingestion_date_rules
from app.auth import record_ingestion_run, record_sheet_run

RECONCILIATION_TOLERANCE = cleanse.RECONCILIATION_TOLERANCE


def coerce_optional_int(value: str | int | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def build_record_filters(
    *,
    trust_product_id: str | int | None = None,
    data_date: str | None = None,
    asset_code: str | None = None,
    custody_asset_code: str | None = None,
    source_asset_code: str | None = None,
    source_file_name: str | None = None,
    source_sheet_name: str | None = None,
) -> dict[str, Any]:
    """将查询参数中的空字符串规范为 None，避免 Optional[int] 解析失败."""
    return {
        "trust_product_id": coerce_optional_int(trust_product_id),
        "data_date": data_date or None,
        "asset_code": asset_code or None,
        "custody_asset_code": custody_asset_code or None,
        "source_asset_code": source_asset_code or None,
        "source_file_name": source_file_name or None,
        "source_sheet_name": source_sheet_name or None,
    }


REPAYMENT_SHEET_KEYWORD = "已还款"
REPAYMENT_SKIP_SHEET = "回款计划"

REPAYMENT_FILE_KEYWORDS = ("还款明细",)
REPAYMENT_SHEET_NAME_KEYWORDS = ("还款明细", "已还款", "还款披露")
MONITOR_FILE_KEYWORDS = ("资产监控",)
MONITOR_SHEET_NAME_KEYWORDS = ("资产监控", "监控表", "监控快照")
AMBIGUOUS_CONFLICT_REASON = "Sheet类型冲突：名称与表头识别结果不一致"

MONITOR_MARKERS = cleanse.MONITOR_FIXED_COLUMNS + (cleanse.aliased_column_label("remaining_amount"),)

COL_ASSET_CODE = ("资产编号(房源)",)
COL_CUSTODY = ("托管房源编码", "托管房源编号")
COL_PERIOD = ("还款期数",)
COL_AMOUNT = ("当期实际还款金额",)
COL_REPAYMENT_DATE = ("当期还款日期", "还款日期")
COL_DATA_DATE = ("统计日期",)
COL_INITIAL = ("初始受让金额",)
COL_REPAID = ("已还款金额",)
COL_REMAINING = cleanse.COL_ALIASES["remaining_amount"]


def upload_root() -> Path:
    root = Path(os.getenv("INGESTION_UPLOAD_DIR", "/data/uploads"))
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


def _verify_trust_product(conn: Connection, trust_product_id: int) -> dict:
    row = conn.execute(
        text("SELECT id, name FROM trust_products WHERE id = :id"),
        {"id": trust_product_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"trust_product_id {trust_product_id} not found")
    return {"id": int(row.id), "name": row.name}


@dataclass(frozen=True)
class SheetClassification:
    sheet_type: str
    name_type: str | None = None
    header_type: str | None = None


def _text_contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _classify_by_name(file_name: str, sheet_name: str) -> str | None:
    if _text_contains_any(file_name, REPAYMENT_FILE_KEYWORDS):
        return "repayment_detail"
    if _text_contains_any(sheet_name, REPAYMENT_SHEET_NAME_KEYWORDS):
        return "repayment_detail"
    if _text_contains_any(file_name, MONITOR_FILE_KEYWORDS):
        return "asset_monitor"
    if _text_contains_any(sheet_name, MONITOR_SHEET_NAME_KEYWORDS):
        return "asset_monitor"
    return None


def _classify_by_header(sheet_name: str, df: pd.DataFrame) -> str | None:
    if REPAYMENT_SKIP_SHEET in sheet_name:
        return "skip"
    if REPAYMENT_SHEET_KEYWORD in sheet_name:
        return "repayment_detail"
    if cleanse.is_monitor_sheet(df):
        return "asset_monitor"
    return None


def classify_sheet(file_name: str, sheet_name: str, df: pd.DataFrame) -> SheetClassification:
    name_type = _classify_by_name(file_name, sheet_name)
    header_type = _classify_by_header(sheet_name, df)

    if (
        name_type in ("repayment_detail", "asset_monitor")
        and header_type in ("repayment_detail", "asset_monitor")
        and name_type != header_type
    ):
        return SheetClassification("ambiguous_sheet_type", name_type, header_type)

    if name_type in ("repayment_detail", "asset_monitor"):
        return SheetClassification(name_type, name_type, header_type)

    if header_type == "skip":
        return SheetClassification("skip", name_type, header_type)
    if header_type in ("repayment_detail", "asset_monitor"):
        return SheetClassification(header_type, name_type, header_type)

    return SheetClassification("unknown", name_type, header_type)


def _unknown_sheet_reason(df: pd.DataFrame) -> str:
    missing = cleanse.monitor_sheet_missing_columns(df)
    if not missing:
        return "无法识别 Sheet 类型"
    cols = set(df.columns.astype(str))
    monitor_like = (
        any(name in cols for name in cleanse.MONITOR_FIXED_COLUMNS)
        or cleanse.pick_aliased_column(df, "remaining_amount") is not None
    )
    if monitor_like:
        return f"缺少资产监控必要列：{'、'.join(missing)}"
    return "无法识别 Sheet 类型"


def classify_workbook(path: Path) -> str:
    xl = pd.ExcelFile(path)
    types = set()
    for name in xl.sheet_names:
        if REPAYMENT_SKIP_SHEET in name:
            continue
        df = pd.read_excel(path, sheet_name=name, header=0, nrows=5)
        result = classify_sheet(path.name, name, df)
        if result.sheet_type not in ("skip", "unknown", "ambiguous_sheet_type"):
            types.add(result.sheet_type)
    if "repayment_detail" in types and "asset_monitor" in types:
        return "mixed"
    if "repayment_detail" in types:
        return "repayment_detail"
    if "asset_monitor" in types:
        return "asset_monitor"
    return "unknown"


def _load_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, header=0)
    return df.dropna(how="all")


def _upsert_trust_asset(
    conn: Connection,
    trust_product_id: int,
    asset_code: str,
    custody_asset_code: str | None,
    initial_transfer_amount: float,
    source_asset_code: str | None = None,
) -> int:
    source = source_asset_code or asset_code
    existing = None
    if custody_asset_code:
        existing = conn.execute(
            text("""
                SELECT id, asset_code FROM trust_assets
                WHERE trust_product_id = :pid AND custody_asset_code = :custody
                LIMIT 1
            """),
            {"pid": trust_product_id, "custody": custody_asset_code},
        ).fetchone()
    if existing is None and source:
        existing = conn.execute(
            text("""
                SELECT id, asset_code FROM trust_assets
                WHERE trust_product_id = :pid AND source_asset_code = :source
                LIMIT 1
            """),
            {"pid": trust_product_id, "source": source},
        ).fetchone()
    if existing is None:
        existing = conn.execute(
            text("""
                SELECT id, asset_code FROM trust_assets
                WHERE trust_product_id = :pid AND asset_code = :code
                LIMIT 1
            """),
            {"pid": trust_product_id, "code": asset_code},
        ).fetchone()

    if existing:
        conn.execute(
            text("""
                UPDATE trust_assets SET
                    custody_asset_code = COALESCE(:custody, custody_asset_code),
                    source_asset_code = COALESCE(source_asset_code, :source),
                    initial_transfer_amount = CASE
                        WHEN :initial > 0 THEN :initial ELSE initial_transfer_amount END,
                    updated_at = NOW()
                WHERE id = :id
            """),
            {
                "id": existing.id,
                "custody": custody_asset_code,
                "source": source,
                "initial": initial_transfer_amount,
            },
        )
        return int(existing.id)

    row = conn.execute(
        text("""
            INSERT INTO trust_assets (
                trust_product_id, asset_code, custody_asset_code,
                source_asset_code, initial_transfer_amount
            ) VALUES (:pid, :code, :custody, :source, :initial)
            RETURNING id
        """),
        {
            "pid": trust_product_id,
            "code": asset_code,
            "custody": custody_asset_code,
            "source": source,
            "initial": initial_transfer_amount,
        },
    ).fetchone()
    return int(row.id)


def _resolve_asset_fields(
    row: pd.Series, col_asset: str | None, col_custody: str | None
) -> tuple[str | None, str | None, str | None]:
    """Excel 托管房源编码 → custody；资产编号(房源) → source；asset_code 兼容写入 source."""
    custody = cleanse.clean_custody_code(row[col_custody]) if col_custody else None
    source = cleanse.clean_asset_code(row[col_asset]) if col_asset else None
    if not source and custody:
        source = custody
    if not custody and source:
        custody = cleanse.derive_custody_from_source(source)
    asset_code = source
    return asset_code, custody, source


def _repayment_date_for_row(
    row: pd.Series,
    col_date: str | None,
    sheet_fallback: date | None,
) -> date | None:
    if col_date:
        parsed = cleanse.to_date_value(row[col_date])
        if parsed:
            return parsed
    return sheet_fallback


def _batch_repayment_stats(conn: Connection, trust_product_id: int, file_name: str, sheet_name: str) -> tuple[int, float]:
    row = conn.execute(
        text("""
            SELECT COUNT(*) AS cnt, COALESCE(SUM(actual_repayment_amount), 0) AS total
            FROM trust_repayment_detail_records
            WHERE trust_product_id = :pid
              AND source_file_name = :file
              AND source_sheet_name = :sheet
        """),
        {"pid": trust_product_id, "file": file_name, "sheet": sheet_name},
    ).fetchone()
    return int(row.cnt), float(row.total)


def _batch_monitor_count(
    conn: Connection, trust_product_id: int, data_date: date, sheet_name: str
) -> int:
    row = conn.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM trust_asset_monitor_records
            WHERE trust_product_id = :pid AND data_date = :dd AND source_sheet_name = :sheet
        """),
        {"pid": trust_product_id, "dd": data_date, "sheet": sheet_name},
    ).fetchone()
    return int(row.cnt)


def _check_within_sheet_row_duplicates(
    rows: list[dict],
) -> tuple[str, str | None, list[str]]:
    """Sheet 内重复：custody + source + repayment_date + amount (+ period_no)."""
    warnings: list[str] = []
    seen: list[dict] = []
    multi_payment: set[tuple[str, str]] = set()

    for r in rows:
        rd = r["repayment_date"]
        custody = r.get("custody_asset_code") or ""
        source = r.get("source_asset_code") or r["asset_code"]
        pn = r.get("period_no") or ""
        amt = r["actual_repayment_amount"]

        for prev in seen:
            if prev["rd"] != rd or prev["custody"] != custody or prev["source"] != source:
                continue
            if pn and prev["pn"] and pn != prev["pn"]:
                continue
            if pn != prev["pn"]:
                continue
            if cleanse.amounts_equal(prev["amt"], amt):
                if pn:
                    return (
                        "reject",
                        "Sheet 内重复: 托管房源 + 资产分笔 + repayment_date + period_no + 金额",
                        warnings,
                    )
                return "reject", "Sheet 内重复: 托管房源 + 资产分笔 + 同一天 + 同金额", warnings
            label = custody or source
            multi_payment.add((label, str(rd)))

        seen.append({
            "rd": rd, "custody": custody, "source": source, "pn": pn, "amt": amt,
        })

    for label, rd in sorted(multi_payment):
        warnings.append(f"{label} @ {rd}: 合法多笔还款")

    return "ok", None, warnings


def _parse_repayment_rows(
    df: pd.DataFrame,
    sheet_fallback_date: date | None,
) -> tuple[list[dict], list[str]]:
    col_asset = cleanse.pick_column(df, *COL_ASSET_CODE)
    col_custody = cleanse.pick_column(df, *COL_CUSTODY)
    col_period = cleanse.pick_column(df, *COL_PERIOD)
    col_amount = cleanse.pick_column(df, *COL_AMOUNT)
    col_date = cleanse.pick_column(df, *COL_REPAYMENT_DATE)

    if not col_custody and not col_asset:
        return [], ["缺少托管房源编码或资产编号(房源)列"]
    if not col_amount:
        return [], ["缺少当期实际还款金额列"]

    rows: list[dict] = []
    errors: list[str] = []
    for idx, row in df.iterrows():
        asset_code, custody, source = _resolve_asset_fields(row, col_asset, col_custody)
        if not asset_code and not custody:
            continue
        amount = cleanse.to_numeric_value(row[col_amount])
        if amount is None:
            if cleanse.is_excel_error(row[col_amount]):
                errors.append(f"行{idx + 2}: 金额含 Excel 错误值")
            continue
        repayment_date = _repayment_date_for_row(row, col_date, sheet_fallback_date)
        if repayment_date is None:
            errors.append(f"行{idx + 2}: 无法解析 repayment_date")
            continue
        period_no = cleanse.clean_period_no(row[col_period]) if col_period else None
        rows.append({
            "asset_code": asset_code,
            "custody_asset_code": custody,
            "source_asset_code": source,
            "period_no": period_no,
            "actual_repayment_amount": amount,
            "repayment_date": repayment_date,
            "data_date": repayment_date,
        })
    return rows, errors


def _parse_monitor_rows(df: pd.DataFrame) -> tuple[list[dict], list[str], date | None]:
    col_asset = cleanse.pick_column(df, *COL_ASSET_CODE)
    col_custody = cleanse.pick_column(df, *COL_CUSTODY)
    col_data = cleanse.pick_column(df, *COL_DATA_DATE)
    col_initial = cleanse.pick_column(df, *COL_INITIAL)
    col_repaid = cleanse.pick_column(df, *COL_REPAID)
    col_remaining = cleanse.pick_aliased_column(df, "remaining_amount")

    remaining_label = cleanse.aliased_column_label("remaining_amount")
    missing = [c for c, col in [
        ("统计日期", col_data), ("初始受让金额", col_initial),
        ("已还款金额", col_repaid), (remaining_label, col_remaining),
    ] if col is None]
    if missing:
        return [], [f"缺少列: {', '.join(missing)}"], None
    if not col_custody and not col_asset:
        return [], ["缺少托管房源编码或资产编号(房源)列"], None

    rows: list[dict] = []
    errors: list[str] = []
    dates: list[date] = []
    for idx, row in df.iterrows():
        asset_code, custody, source = _resolve_asset_fields(row, col_asset, col_custody)
        if not asset_code and not custody:
            continue
        data_date = cleanse.to_date_value(row[col_data])
        if not data_date:
            errors.append(f"行{idx + 2}: 统计日期无效")
            continue
        dates.append(data_date)
        initial = cleanse.to_numeric_value(row[col_initial])
        repaid = cleanse.to_numeric_value(row[col_repaid])
        remaining = cleanse.to_numeric_value(row[col_remaining])
        if initial is None or repaid is None or remaining is None:
            errors.append(f"行{idx + 2}: 金额字段无效")
            continue
        rows.append({
            "asset_code": asset_code,
            "custody_asset_code": custody,
            "source_asset_code": source,
            "data_date": data_date,
            "initial_transfer_amount": initial,
            "repaid_amount": repaid,
            "remaining_amount": remaining,
        })

    if not dates:
        return [], errors or ["无有效监控行"], None
    from collections import Counter
    batch_date = Counter(dates).most_common(1)[0][0]
    rows = [r for r in rows if r["data_date"] == batch_date]
    return rows, errors, batch_date


def precheck_repayment_sheet(
    conn: Connection,
    trust_product_id: int,
    product_name: str,
    file_name: str,
    sheet_name: str,
    df: pd.DataFrame,
) -> dict[str, Any]:
    parsed = ingestion_date_rules.parse_sheet_repayment_date(sheet_name, product_name)
    sheet_fallback = parsed.parsed_date if parsed.ok else None

    result: dict[str, Any] = {
        "file_name": file_name,
        "sheet_name": sheet_name,
        "sheet_type": "repayment_detail",
        "parsed_date": str(sheet_fallback) if sheet_fallback else None,
        "date_rule_label": parsed.rule_label,
        "date_parse_error": parsed.error,
        "row_count": 0,
        "amount_sum": 0.0,
        "exists": False,
        "importable": False,
        "action": "failed",
        "reason": "",
        "warnings": [],
        "db_row_count": 0,
        "db_amount_sum": 0.0,
    }

    if not parsed.ok:
        result["reason"] = parsed.error or "Sheet 日期解析失败"
        return result

    rows, parse_errors = _parse_repayment_rows(df, sheet_fallback)
    if parse_errors:
        result["warnings"].extend(parse_errors[:20])
    if not rows:
        result["reason"] = "无有效数据行" + (f"; {parse_errors[0]}" if parse_errors else "")
        return result

    amount_sum = sum(r["actual_repayment_amount"] for r in rows)
    result["row_count"] = len(rows)
    result["amount_sum"] = amount_sum

    db_cnt, db_sum = _batch_repayment_stats(conn, trust_product_id, file_name, sheet_name)
    result["db_row_count"] = db_cnt
    result["db_amount_sum"] = db_sum
    result["exists"] = db_cnt > 0

    if db_cnt > 0:
        if db_cnt == len(rows) and cleanse.amounts_equal(db_sum, amount_sum):
            result["action"] = "skip"
            result["importable"] = False
            result["reason"] = "该 Sheet 已存在且数据一致"
            return result
        result["action"] = "reject"
        result["reason"] = "该 Sheet 已存在但数据不一致，需要人工确认"
        return result

    status, msg, dup_warnings = _check_within_sheet_row_duplicates(rows)
    result["warnings"].extend(dup_warnings[:20])
    if status == "reject":
        result["action"] = "reject"
        result["reason"] = msg
        return result

    result["action"] = "import"
    result["importable"] = True
    result["reason"] = "可导入（合法多笔还款）" if dup_warnings else "可导入"
    return result


def precheck_monitor_sheet(
    conn: Connection,
    trust_product_id: int,
    file_name: str,
    sheet_name: str,
    df: pd.DataFrame,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "file_name": file_name,
        "sheet_name": sheet_name,
        "sheet_type": "asset_monitor",
        "parsed_date": None,
        "date_rule_label": None,
        "row_count": 0,
        "amount_sum": None,
        "exists": False,
        "importable": False,
        "action": "failed",
        "reason": "",
        "warnings": [],
        "db_row_count": 0,
    }

    rows, parse_errors, batch_date = _parse_monitor_rows(df)
    if parse_errors:
        result["warnings"].extend(parse_errors[:20])
    if not batch_date or not rows:
        result["reason"] = "统计日期无法解析或无有效行"
        return result

    result["parsed_date"] = str(batch_date)
    result["row_count"] = len(rows)

    db_cnt = _batch_monitor_count(conn, trust_product_id, batch_date, sheet_name)
    result["db_row_count"] = db_cnt
    result["exists"] = db_cnt > 0

    if db_cnt == 0:
        result["action"] = "import"
        result["importable"] = True
        result["reason"] = "可导入"
        return result

    if db_cnt == len(rows):
        result["action"] = "overwrite"
        result["importable"] = True
        result["reason"] = "记录数一致，允许覆盖更新"
        return result

    result["action"] = "reject"
    result["reason"] = f"记录数不一致（DB {db_cnt} vs 文件 {len(rows)}），需要人工确认"
    return result


def recompute_monitor_payment_fields(
    conn: Connection,
    trust_product_id: int,
    data_date: date,
) -> list[str]:
    """重算 last_payment_date / overdue_days；返回数据质量警告."""
    warnings: list[str] = []

    conn.execute(
        text("""
            UPDATE trust_asset_monitor_records m
            SET
                last_payment_date = sub.max_rd,
                max_payment_date = sub.max_rd,
                overdue_days = CASE
                    WHEN sub.max_rd IS NULL THEN NULL
                    ELSE GREATEST(0, m.data_date - sub.max_rd)
                END
            FROM (
                SELECT trust_asset_id, MAX(repayment_date) AS max_rd
                FROM trust_repayment_detail_records
                WHERE trust_product_id = :pid
                GROUP BY trust_asset_id
            ) sub
            WHERE m.trust_product_id = :pid
              AND m.data_date = :dd
              AND m.trust_asset_id = sub.trust_asset_id
        """),
        {"pid": trust_product_id, "dd": data_date},
    )

    null_rows = conn.execute(
        text("""
            SELECT m.asset_code FROM trust_asset_monitor_records m
            WHERE m.trust_product_id = :pid AND m.data_date = :dd
              AND m.last_payment_date IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM trust_repayment_detail_records r
                  WHERE r.trust_product_id = :pid AND r.trust_asset_id = m.trust_asset_id
              )
        """),
        {"pid": trust_product_id, "dd": data_date},
    )
    for r in null_rows:
        warnings.append(f"{r.asset_code}: 缺少还款明细，无法计算最后回款日")

    conn.execute(
        text("""
            UPDATE trust_asset_monitor_records m
            SET last_payment_date = NULL, max_payment_date = NULL, overdue_days = NULL
            WHERE m.trust_product_id = :pid AND m.data_date = :dd
              AND m.last_payment_date IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM trust_repayment_detail_records r
                  WHERE r.trust_product_id = :pid AND r.trust_asset_id = m.trust_asset_id
              )
        """),
        {"pid": trust_product_id, "dd": data_date},
    )
    return warnings


def _import_repayment_sheet(
    conn: Connection,
    trust_product_id: int,
    product_name: str,
    file_name: str,
    sheet_name: str,
    df: pd.DataFrame,
    synced_at: datetime,
) -> tuple[int, int, str]:
    parsed = ingestion_date_rules.parse_sheet_repayment_date(sheet_name, product_name)
    if not parsed.ok or not parsed.parsed_date:
        raise HTTPException(status_code=400, detail=parsed.error or "日期解析失败")

    rows, _ = _parse_repayment_rows(df, parsed.parsed_date)
    if not rows:
        return 0, 0, "无有效行"

    upsert_count = 0
    inserted = 0
    for r in rows:
        asset_id = _upsert_trust_asset(
            conn,
            trust_product_id,
            r["asset_code"],
            r.get("custody_asset_code"),
            0.0,
            r.get("source_asset_code"),
        )
        upsert_count += 1
        conn.execute(
            text("""
                INSERT INTO trust_repayment_detail_records (
                    trust_product_id, trust_asset_id, asset_code,
                    custody_asset_code, source_asset_code,
                    data_date, period_no, actual_repayment_amount, repayment_date,
                    source_file_name, source_sheet_name, synced_at
                ) VALUES (
                    :pid, :aid, :ac, :custody, :source,
                    :dd, :pn, :amt, :rd,
                    :file, :sheet, :synced
                )
            """),
            {
                "pid": trust_product_id,
                "aid": asset_id,
                "ac": r["asset_code"],
                "custody": r.get("custody_asset_code"),
                "source": r.get("source_asset_code"),
                "dd": r["data_date"],
                "pn": r.get("period_no"),
                "amt": r["actual_repayment_amount"],
                "rd": r["repayment_date"],
                "file": file_name,
                "sheet": sheet_name,
                "synced": synced_at,
            },
        )
        inserted += 1
    return inserted, upsert_count, "imported"


def _import_monitor_sheet(
    conn: Connection,
    trust_product_id: int,
    file_name: str,
    sheet_name: str,
    df: pd.DataFrame,
    synced_at: datetime,
) -> tuple[int, int, str, date | None, list[str]]:
    rows, _, batch_date = _parse_monitor_rows(df)
    if not batch_date or not rows:
        return 0, 0, "无有效行", None, []

    conn.execute(
        text("""
            DELETE FROM trust_asset_monitor_records
            WHERE trust_product_id = :pid
              AND data_date = :dd
              AND source_sheet_name = :sheet
        """),
        {"pid": trust_product_id, "dd": batch_date, "sheet": sheet_name},
    )

    upsert_count = 0
    inserted = 0
    for r in rows:
        asset_id = _upsert_trust_asset(
            conn,
            trust_product_id,
            r["asset_code"],
            r.get("custody_asset_code"),
            float(r["initial_transfer_amount"]),
            r.get("source_asset_code"),
        )
        upsert_count += 1
        conn.execute(
            text("""
                INSERT INTO trust_asset_monitor_records (
                    trust_product_id, trust_asset_id, asset_code,
                    custody_asset_code, source_asset_code,
                    data_date, initial_transfer_amount, repaid_amount, remaining_amount,
                    overdue_days, last_payment_date, max_payment_date,
                    source_file_name, source_sheet_name, synced_at
                ) VALUES (
                    :pid, :aid, :ac, :custody, :source,
                    :dd, :initial, :repaid, :remaining,
                    NULL, NULL, NULL,
                    :file, :sheet, :synced
                )
            """),
            {
                "pid": trust_product_id,
                "aid": asset_id,
                "ac": r["asset_code"],
                "custody": r.get("custody_asset_code"),
                "source": r.get("source_asset_code"),
                "dd": batch_date,
                "initial": r["initial_transfer_amount"],
                "repaid": r["repaid_amount"],
                "remaining": r["remaining_amount"],
                "file": file_name,
                "sheet": sheet_name,
                "synced": synced_at,
            },
        )
        inserted += 1

    quality_warnings = recompute_monitor_payment_fields(conn, trust_product_id, batch_date)
    return inserted, upsert_count, "imported", batch_date, quality_warnings


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


def run_preview(
    conn: Connection,
    trust_product_id: int,
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
            if REPAYMENT_SKIP_SHEET in sheet_name:
                continue
            df = _load_sheet(path, sheet_name)
            classification = classify_sheet(file_name, sheet_name, df)
            st = classification.sheet_type
            if st == "ambiguous_sheet_type":
                sheets.append({
                    "file_name": file_name,
                    "sheet_name": sheet_name,
                    "sheet_type": st,
                    "action": "failed",
                    "importable": False,
                    "reason": AMBIGUOUS_CONFLICT_REASON,
                    "name_type": classification.name_type,
                    "header_type": classification.header_type,
                })
                continue
            if st == "skip" or st == "unknown":
                if st == "unknown":
                    sheets.append({
                        "file_name": file_name,
                        "sheet_name": sheet_name,
                        "sheet_type": "unknown",
                        "action": "failed",
                        "importable": False,
                        "reason": _unknown_sheet_reason(df),
                    })
                continue
            if st == "repayment_detail":
                sheets.append(precheck_repayment_sheet(
                    conn, trust_product_id, product_name, file_name, sheet_name, df,
                ))
            elif st == "asset_monitor":
                sheets.append(precheck_monitor_sheet(
                    conn, trust_product_id, file_name, sheet_name, df,
                ))

    payload = {
        "batch_uuid": batch_uuid,
        "trust_product_id": trust_product_id,
        "product_name": product_name,
        "trust_product_name": product_name,
        "files": file_names,
        "sheets": sheets,
    }
    preview_json_path(batch_uuid).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return payload


def run_import(
    conn: Connection,
    batch_uuid: str,
    trust_product_id: int,
    user_id: int,
    confirm_sheet_keys: list[str] | None = None,
) -> dict[str, Any]:
    preview_path = preview_json_path(batch_uuid)
    if not preview_path.exists():
        raise HTTPException(status_code=400, detail="预检结果不存在，请先 preview")

    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    if int(preview["trust_product_id"]) != trust_product_id:
        raise HTTPException(status_code=400, detail="trust_product_id 与预检不一致")

    product_name = preview["product_name"]
    confirm_set = set(confirm_sheet_keys or [])
    synced_at = datetime.now(timezone.utc)

    inserted_monitor = 0
    inserted_repayment = 0
    upsert_assets = 0
    skipped = 0
    failed = 0
    sheet_results: list[dict] = []
    monitor_dates: list[date] = []
    quality_warnings: list[str] = []
    risk_recalc_hint = False

    for sheet in preview["sheets"]:
        action = sheet.get("action")
        key = sheet_key(sheet["file_name"], sheet["sheet_name"])
        file_name = sheet["file_name"]
        sheet_name = sheet["sheet_name"]
        path = batch_dir(batch_uuid) / file_name
        df = _load_sheet(path, sheet_name)

        if action == "skip":
            skipped += 1
            sheet_results.append({**sheet, "final_action": "skipped"})
            continue

        if action == "reject" or action == "failed":
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

        try:
            if sheet["sheet_type"] == "repayment_detail":
                ins, ups, msg = _import_repayment_sheet(
                    conn, trust_product_id, product_name, file_name, sheet_name, df, synced_at,
                )
                inserted_repayment += ins
                upsert_assets += ups
                sheet_results.append({**sheet, "final_action": "imported", "inserted": ins})
            elif sheet["sheet_type"] == "asset_monitor":
                ins, ups, msg, batch_date, warns = _import_monitor_sheet(
                    conn, trust_product_id, file_name, sheet_name, df, synced_at,
                )
                inserted_monitor += ins
                upsert_assets += ups
                quality_warnings.extend(warns)
                if batch_date:
                    monitor_dates.append(batch_date)
                if action == "overwrite":
                    risk_recalc_hint = True
                sheet_results.append({
                    **sheet,
                    "final_action": "overwritten" if action == "overwrite" else "imported",
                    "inserted": ins,
                    "quality_warnings": warns,
                })
            else:
                failed += 1
                sheet_results.append({**sheet, "final_action": "failed"})
        except Exception as exc:
            failed += 1
            sheet_results.append({**sheet, "final_action": "failed", "reason": str(exc)})

    pipeline_data_date = monitor_dates[0] if monitor_dates else None
    source_files = ", ".join(preview.get("files", []))
    error_message = None
    if failed:
        error_message = f"{failed} 个 Sheet 导入失败"

    run_id, created_at = record_ingestion_run(
        conn,
        trust_product_id=trust_product_id,
        data_date=pipeline_data_date,
        trust_plan_alias=None,
        source_file=source_files,
        created_by=user_id,
        inserted_monitor_count=inserted_monitor,
        inserted_repayment_count=inserted_repayment,
        upsert_asset_count=upsert_assets,
        skipped_sheet_count=skipped,
        failed_sheet_count=failed,
        error_message=error_message,
        trust_product_name=product_name,
    )

    for sr in sheet_results:
        record_sheet_run(
            conn,
            pipeline_run_id=run_id,
            source_file_name=sr["file_name"],
            source_sheet_name=sr["sheet_name"],
            sheet_type=sr.get("sheet_type", "unknown"),
            data_date=sr.get("parsed_date"),
            row_count=sr.get("row_count", 0),
            amount_sum=sr.get("amount_sum"),
            action=sr.get("final_action", sr.get("action", "failed")),
            message=sr.get("reason"),
            trust_product_id=trust_product_id,
            trust_product_name=product_name,
        )

    conn.commit()

    result = {
        "run_id": run_id,
        "created_at": created_at,
        "batch_uuid": batch_uuid,
        "trust_product_id": trust_product_id,
        "trust_product_name": product_name,
        "inserted_monitor_count": inserted_monitor,
        "inserted_repayment_count": inserted_repayment,
        "upsert_asset_count": upsert_assets,
        "skipped_sheet_count": skipped,
        "failed_sheet_count": failed,
        "sheet_results": sheet_results,
        "quality_warnings": quality_warnings,
    }
    if risk_recalc_hint:
        result["risk_recalc_hint"] = "监控快照已覆盖，请手动重新计算风险评分（POST /risk/score/recalculate）"
    return result


def fetch_paginated_records(
    conn: Connection,
    table: str,
    page: int,
    page_size: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    allowed = {
        "repayment": "trust_repayment_detail_records",
        "monitor": "trust_asset_monitor_records",
    }
    table_name = allowed.get(table)
    if not table_name:
        raise HTTPException(status_code=400, detail="invalid table")

    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    offset = (page - 1) * page_size

    where_parts = ["1=1"]
    params: dict[str, Any] = {"limit": page_size, "offset": offset}

    for key in (
        "trust_product_id", "data_date", "asset_code",
        "custody_asset_code", "source_asset_code",
        "source_file_name", "source_sheet_name",
    ):
        val = filters.get(key)
        if val is not None and val != "":
            where_parts.append(f"r.{key} = :{key}")
            params[key] = int(val) if key == "trust_product_id" else val

    where_sql = " AND ".join(where_parts)
    count_row = conn.execute(
        text(f"""
            SELECT COUNT(*) AS cnt
            FROM {table_name} r
            JOIN trust_products tp ON tp.id = r.trust_product_id
            WHERE {where_sql}
        """),
        params,
    ).fetchone()
    total = int(count_row.cnt)

    rows = conn.execute(
        text(f"""
            SELECT r.*, tp.name AS trust_product_name
            FROM {table_name} r
            JOIN trust_products tp ON tp.id = r.trust_product_id
            WHERE {where_sql}
            ORDER BY r.data_date DESC,
                     r.custody_asset_code ASC NULLS LAST,
                     r.source_asset_code ASC NULLS LAST,
                     r.asset_code ASC
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
            elif isinstance(v, (int, float)) and v is not None and k.endswith("amount"):
                item[k] = float(v)
        items.append(item)

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": items,
    }
