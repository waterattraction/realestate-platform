"""Excel 字段清洗."""

from __future__ import annotations

import math
import re

import pandas as pd

EXCEL_ERROR_PATTERN = re.compile(r"^#(NAME\?|REF!|VALUE!|N/A|DIV/0!|NULL!|NUM!)$", re.I)
CUSTODY_FROM_SOURCE_PATTERN = re.compile(r"^(\d{12})-\d{3}$")

RECONCILIATION_TOLERANCE = 0.01

# 语义字段 → Excel 列名别名（通用，不按产品写死）
COL_ALIASES: dict[str, tuple[str, ...]] = {
    "remaining_amount": ("剩余还款金额", "剩余应还款余额"),
    "last_renovation_payment_date": ("最后一期装修款付款时间",),
}

MONITOR_FIXED_COLUMNS: tuple[str, ...] = (
    "统计日期",
    "初始受让金额",
    "已还款金额",
)


def is_excel_error(value) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    return bool(EXCEL_ERROR_PATTERN.match(str(value).strip()))


def clean_custody_code(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, float) and value == int(value):
        text_val = str(int(value))
    else:
        text_val = str(value)
    text_val = text_val.replace("\t", "").strip()
    return text_val or None


def clean_asset_code(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text_val = str(value).strip()
    return text_val or None


def derive_custody_from_source(source_asset_code: str | None) -> str | None:
    """从资产分笔号推导托管房源号，如 101127075900-001 → 101127075900."""
    if not source_asset_code:
        return None
    match = CUSTODY_FROM_SOURCE_PATTERN.match(source_asset_code.strip())
    return match.group(1) if match else None


def clean_period_no(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    text_val = str(value).strip()
    return text_val or None


def to_date_value(value) -> date | None:
    from datetime import date

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if is_excel_error(value):
        return None
    try:
        return pd.Timestamp(value).date()
    except (ValueError, TypeError):
        return None


def to_numeric_value(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if is_excel_error(value):
        return None
    try:
        num = float(value)
        if math.isnan(num) or math.isinf(num):
            return None
        return num
    except (TypeError, ValueError):
        return None


def amounts_equal(a: float, b: float, tolerance: float = RECONCILIATION_TOLERANCE) -> bool:
    return abs(a - b) <= tolerance


def pick_column(df: pd.DataFrame, *candidates: str) -> str | None:
    for name in candidates:
        if name in df.columns:
            return name
    return None


def pick_aliased_column(df: pd.DataFrame, field_key: str) -> str | None:
    return pick_column(df, *COL_ALIASES.get(field_key, ()))


def aliased_column_label(field_key: str) -> str:
    names = COL_ALIASES.get(field_key, ())
    return " / ".join(names) if names else field_key


def monitor_sheet_missing_columns(df: pd.DataFrame) -> list[str]:
    cols = set(df.columns.astype(str))
    missing: list[str] = []
    for name in MONITOR_FIXED_COLUMNS:
        if name not in cols:
            missing.append(name)
    if pick_aliased_column(df, "remaining_amount") is None:
        missing.append(aliased_column_label("remaining_amount"))
    return missing


def is_monitor_sheet(df: pd.DataFrame) -> bool:
    return not monitor_sheet_missing_columns(df)
