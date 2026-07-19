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
    "asset_pool_code": ("资产包编号",),
    "current_payer": ("当前还款方",),
    "planned_repayment_amount": ("当期计划还款金额",),
    "initial_renovation_amount": ("初始受让装修金额",),
    "cumulative_repaid_amount": ("累计已还款金额",),
    "remaining_balance": ("剩余应还款余额",),
    "renovation_vendor": ("装修服务商",),
    "asset_status": ("资产状态",),
    "community_name": ("小区名称",),
    "city": ("城市", "所属城市", "所属区域"),
    "collection_contract_code": ("收房合同编码",),
    "custody_agreement_sign_date": ("托管协议签署日期",),
    "collection_contract_years": ("收房合同签约年数",),
    "owner_code": ("业主代码",),
    "withholding_ratio": ("代扣比例",),
    "actual_monthly_rent": ("实际出房月租金",),
    "current_bill_date": ("当期账单日",),
    "repayment_amount_detail": ("回款金额明细",),
    "planned_monthly_repayment_amount": ("后续计划每月回款金额",),
    "final_planned_repayment_amount": ("最后一期计划回款金额",),
}

MONITOR_FIXED_COLUMNS: tuple[str, ...] = (
    "统计日期",
    "初始受让金额",
    "已还款金额",
)

REPAYMENT_PLAN_SHEET_KEYWORD = "回款计划"


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


def to_rate_value(value) -> float | None:
    num = to_numeric_value(value)
    if num is None:
        return None
    if num > 1 and num <= 100:
        return num / 100.0
    return num


def to_optional_str(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if is_excel_error(value):
        return None
    if isinstance(value, float) and value == int(value):
        text_val = str(int(value))
    elif isinstance(value, int):
        text_val = str(value)
    else:
        text_val = str(value).strip()
    return text_val or None


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


def is_repayment_plan_sheet(sheet_name: str) -> bool:
    return REPAYMENT_PLAN_SHEET_KEYWORD in str(sheet_name or "")
