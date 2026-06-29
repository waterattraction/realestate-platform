"""发行资产明细 Excel 字段清洗与列映射."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app import assetinfo_cleanse as cleanse

COL_ALIASES: dict[str, tuple[str, ...]] = {
    "custody_asset_code": (
        "房源编码",
        "房源编号",
        "托管房源编码",
        "托管房源号",
    ),
    "receivable_contract_amount": (
        "实际成交价（应收账款合同金额）",
        "应收账款合同金额",
    ),
    "receivable_transfer_amount": ("应收账款转让价款",),
    "asset_transfer_discount_rate": (
        "资产转让折扣率(%)",
        "资产转让折扣率（数值）(%)",
        "资产转让折扣率(数值)(%)",
        "资产转让折扣率",
    ),
    "min_institution_transferable_amount": (
        "MIN金融机构可转让",
        "MIN金额机构可转让最终",
    ),
    "remaining_unpaid_amount_beike_not_withheld": ("剩余未还款金额--贝壳未代扣",),
    "rental_price": ("出房价格",),
    "total_rent_withholding_amount": ("总租金代扣金额", "租金代扣金额"),
    "rent_withheld_amount_before_pooling": ("已租金代扣金额合计-封包前",),
    "withholding_periods_at_pooling": ("代扣支付期数-封包日（计算）",),
    "initial_expected_withholding_cycle": ("预计代扣支付周期-最初",),
    "renovation_payment_method": ("装修付款形式",),
    "rent_withholding_ratio": ("租金代扣比例(%)", "租金代扣比例"),
    "calculated_rent_withholding_per_period": ("每期租金代扣金额（计算）",),
    "first_rent_withholding_date": ("首次付款日期", "首次租金代扣日期"),
    "signing_date": ("签约日期",),
    "rental_contract_end_date": ("出房合同结束日",),
    "contract_name": ("合同名称",),
    "debtor_name": ("债务人姓名（业主名称）", "债务人姓名", "业主名称"),
    "property_address": ("房源地址",),
    "city": ("所属城市", "所属区域", "城市"),
    "contractor_name": ("施工方名称",),
    "from_trust_product_name": (
        "当前信托计划（已发行）",
        "原信托计划",
        "转出信托计划",
        "当前信托计划",
        "拟转入计划（未发行）",
    ),
    "migration_type": (
        "迁移类型",
        "资产迁移类型",
        "migration_type",
    ),
}

MIGRATION_TYPES: tuple[str, ...] = (
    "new_issuance",
    "rollover",
    "repackage",
    "transfer",
    "replenishment",
)

MIGRATION_TYPE_LABELS: dict[str, str] = {
    "new_issuance": "新发行",
    "rollover": "续发",
    "repackage": "重新封包",
    "transfer": "转让",
    "replenishment": "补录",
}

_MIGRATION_TYPE_ALIASES: dict[str, str] = {
    "": "new_issuance",
    "新发行": "new_issuance",
    "续发": "rollover",
    "展期": "rollover",
    "滚续": "rollover",
    "重新封包": "repackage",
    "重新入池": "repackage",
    "转让": "transfer",
    "产品迁移": "transfer",
    "new_issuance": "new_issuance",
    "rollover": "rollover",
    "repackage": "repackage",
    "transfer": "transfer",
}

ISSUANCE_CORE_FIELDS = (
    "custody_asset_code",
    "receivable_contract_amount",
    "receivable_transfer_amount",
)

ISSUANCE_CONFIDENCE_FIELDS = (
    "total_rent_withholding_amount",
    "min_institution_transferable_amount",
    "asset_transfer_discount_rate",
    "from_trust_product_name",
)


def pick_column(df: pd.DataFrame, field_key: str) -> str | None:
    return cleanse.pick_column(df, *COL_ALIASES.get(field_key, ()))


def issuance_sheet_missing_core(df: pd.DataFrame) -> list[str]:
    missing = []
    for key in ISSUANCE_CORE_FIELDS:
        if pick_column(df, key) is None:
            labels = " / ".join(COL_ALIASES.get(key, (key,)))
            missing.append(labels)
    return missing


def is_issuance_sheet(df: pd.DataFrame) -> bool:
    return not issuance_sheet_missing_core(df)


def is_monitor_like_sheet(df: pd.DataFrame) -> bool:
    return cleanse.is_monitor_sheet(df)


def is_repayment_like_sheet(df: pd.DataFrame) -> bool:
    return cleanse.pick_column(df, "当期实际还款金额", "已还款金额") is not None


def to_rate_value(value) -> float | None:
    num = cleanse.to_numeric_value(value)
    if num is None:
        return None
    if num > 1 and num <= 100:
        return num / 100.0
    return num


def to_int_value(value) -> int | None:
    num = cleanse.to_numeric_value(value)
    if num is None:
        return None
    return int(num)


def to_optional_amount(value, *, required: bool) -> tuple[float | None, str | None]:
    if cleanse.is_excel_error(value):
        return None, "Excel 错误值" if required else None
    num = cleanse.to_numeric_value(value)
    if num is None:
        if required:
            return None, "金额无效"
        return None, None
    return num, None


def to_optional_date(value) -> date | None:
    return cleanse.to_date_value(value)


def exact_duplicate_fingerprint(row: dict) -> tuple:
    return (
        row["business_asset_key"],
        row["receivable_contract_amount"],
        row["receivable_transfer_amount"],
        row.get("signing_date"),
        row.get("first_rent_withholding_date"),
        row.get("rental_contract_end_date"),
    )


def build_business_asset_key(
    trust_product_id: int, issue_date: date, custody_asset_code: str
) -> str:
    return f"{trust_product_id}:{issue_date.isoformat()}:{custody_asset_code}"


CITY_VALUES: frozenset[str] = frozenset({"北京", "上海"})

_CITY_EXCEL_ALIASES: dict[str, str] = {
    "上海": "上海",
    "上海市": "上海",
    "北京": "北京",
    "北京市": "北京",
    "京北": "北京",
    "京南": "北京",
}

BEIJING_ADDRESS_KEYWORDS: tuple[str, ...] = (
    "北京",
    "北京市",
    "海淀",
    "朝阳",
    "丰台",
    "西城",
    "东城",
    "石景山",
    "通州",
    "昌平",
    "大兴",
    "顺义",
    "房山",
    "门头沟",
)

SHANGHAI_ADDRESS_KEYWORDS: tuple[str, ...] = (
    "上海",
    "上海市",
    "徐汇",
    "静安",
    "浦东",
    "闵行",
    "长宁",
    "普陀",
    "杨浦",
    "虹口",
    "黄浦",
    "宝山",
    "松江",
    "嘉定",
    "青浦",
)


def _map_city_excel_raw(raw: str) -> str | None:
    text_val = raw.strip()
    if not text_val:
        return None
    if text_val in _CITY_EXCEL_ALIASES:
        return _CITY_EXCEL_ALIASES[text_val]
    if text_val in CITY_VALUES:
        return text_val
    return None


def infer_city_from_address(property_address: str | None) -> str | None:
    if not property_address:
        return None
    addr = str(property_address).strip()
    if not addr:
        return None
    for keyword in SHANGHAI_ADDRESS_KEYWORDS:
        if keyword in addr:
            return "上海"
    for keyword in BEIJING_ADDRESS_KEYWORDS:
        if keyword in addr:
            return "北京"
    return None


def resolve_city(
    *,
    excel_column_present: bool,
    excel_value: str | None,
    property_address: str | None,
    source_row_number: int,
) -> tuple[str | None, list[str]]:
    """城市：优先 Excel 所属城市/所属区域，其次房源地址推断."""
    warnings: list[str] = []
    raw = (excel_value or "").strip() if excel_column_present else ""

    if excel_column_present and raw:
        mapped = _map_city_excel_raw(raw)
        if mapped:
            return mapped, warnings

    inferred = infer_city_from_address(property_address)
    if inferred:
        return inferred, warnings

    if excel_column_present and raw:
        warnings.append(
            f"行{source_row_number}: 无法识别城市「{raw}」"
        )
    elif property_address:
        warnings.append(f"行{source_row_number}: 无法从地址识别城市")
    return None, warnings


def city_distribution(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        city = row.get("city")
        if not city:
            continue
        counts[city] = counts.get(city, 0) + 1
    return counts


def city_blank_count(rows: list[dict]) -> int:
    return sum(1 for row in rows if not row.get("city"))


def asset_transfer_discount_rate_present_count(rows: list[dict]) -> int:
    return sum(1 for row in rows if row.get("asset_transfer_discount_rate") is not None)


def asset_transfer_discount_rate_blank_count(rows: list[dict]) -> int:
    return sum(1 for row in rows if row.get("asset_transfer_discount_rate") is None)


def find_unmapped_discount_rate_columns(
    df: pd.DataFrame, mapped_col: str | None,
) -> list[str]:
    """Excel 中疑似折扣率列但未纳入 COL_ALIASES 映射."""
    suspicious: list[str] = []
    for col in df.columns:
        col_str = str(col).strip()
        if mapped_col and col_str == mapped_col:
            continue
        if "资产转让折扣率" in col_str:
            suspicious.append(col_str)
            continue
        if "折扣率" in col_str and "%" in col_str:
            suspicious.append(col_str)
    return suspicious


def tokenize_from_trust_product_raw(raw: str) -> list[str]:
    """拆分 Excel 转出产品单元格（支持逗号、顿号分隔）."""
    text_val = str(raw).strip()
    if not text_val:
        return []
    normalized = text_val.replace("，", ",").replace("、", ",").replace(";", ",")
    return [part.strip() for part in normalized.split(",") if part.strip()]


def from_trust_product_distribution(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        name = row.get("from_trust_product_name")
        if not name or not row.get("from_trust_product_id"):
            continue
        counts[name] = counts.get(name, 0) + 1
    return counts


def from_trust_product_matched_count(rows: list[dict]) -> int:
    return sum(1 for row in rows if row.get("from_trust_product_id"))


def from_trust_product_unmatched_count(rows: list[dict]) -> int:
    return sum(
        1 for row in rows
        if row.get("from_trust_product_excel_raw") and not row.get("from_trust_product_id")
    )


def migration_type_label(value: str | None) -> str:
    if not value:
        return "—"
    return MIGRATION_TYPE_LABELS.get(value, value)


def _map_migration_type_raw(raw: str) -> str | None:
    text_val = raw.strip()
    if not text_val:
        return "new_issuance"
    if text_val in _MIGRATION_TYPE_ALIASES:
        return _MIGRATION_TYPE_ALIASES[text_val]
    lowered = text_val.lower()
    if lowered in MIGRATION_TYPES:
        return lowered
    return None


def resolve_migration_type(
    *,
    excel_column_present: bool,
    excel_value: str | None,
    from_trust_product_id: int | None,
    source_row_number: int,
) -> tuple[str, list[str]]:
    """根据 Excel 列或 from_trust_product_id 推断 migration_type."""
    warnings: list[str] = []
    if excel_column_present:
        raw = (excel_value or "").strip()
        mapped = _map_migration_type_raw(raw)
        if mapped:
            return mapped, warnings
        warnings.append(
            f"行{source_row_number}: 迁移类型「{raw}」无法识别，已按 transfer 处理"
        )
        return "transfer", warnings
    if from_trust_product_id is None:
        return "new_issuance", warnings
    return "transfer", warnings
