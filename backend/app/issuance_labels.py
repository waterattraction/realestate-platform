"""发行资产明细 — 字段中文标签与单元格格式化（SSOT）."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app import issuance_cleanse as ic

DISPLAY_TZ = ZoneInfo("Asia/Shanghai")

# 无 Excel 列 / 系统字段（数据字典 + 管理约定）
_SYSTEM_FIELD_LABELS: dict[str, str] = {
    "id": "记录ID",
    "trust_product_id": "产品ID",
    "trust_product_name": "信托产品",
    "from_trust_product_id": "转出产品ID",
    "from_trust_product_name": "转出信托产品",
    "planned_trust_product_id": "拟转入产品ID",
    "planned_trust_product_name": "拟转入信托产品",
    "migration_type": "迁移类型",
    "trust_asset_id": "底层资产ID",
    "issue_date": "发行日期",
    "business_asset_key": "发行资产标识",
    "issuance_weight": "发行权重",
    "migration_reason": "迁移原因",
    "source_file_name": "文件名",
    "source_sheet_name": "工作表名",
    "source_row_number": "行号",
    "created_at": "创建时间",
    "updated_at": "更新时间",
}

# 覆盖 COL_ALIASES 首别名（保留 Excel 原文或数据字典简称）
_FIELD_LABEL_OVERRIDES: dict[str, str] = {
    "custody_asset_code": "托管房源号",
    "receivable_contract_amount": "应收账款合同金额",
    "debtor_name": "债务人",
    "min_institution_transferable_amount": "MIN金融机构可转让",
    "remaining_unpaid_amount_beike_not_withheld": "贝壳未代扣剩余",
    "rent_withheld_amount_before_pooling": "封包前已代扣租金",
    "withholding_periods_at_pooling": "封包时代扣期数",
    "initial_expected_withholding_cycle": "预计代扣周期",
    "calculated_rent_withholding_per_period": "每期代扣金额",
    "first_rent_withholding_date": "首次租金代扣日",
    "rent_withholding_ratio": "租金代扣比例",
    "expected_last_rent_payment_date_initial": "预计最后一期租金支付日",
    "expected_receivable_due_date": "预计应收账款到期日",
    "withheld_repaid_amount": "已代扣已回款",
}


def _build_field_labels() -> dict[str, str]:
    labels = dict(_SYSTEM_FIELD_LABELS)
    for field, aliases in ic.COL_ALIASES.items():
        if field not in labels and aliases:
            labels[field] = aliases[0]
    labels.update(_FIELD_LABEL_OVERRIDES)
    return labels


FIELD_LABELS: dict[str, str] = _build_field_labels()

COLUMN_ORDER: tuple[str, ...] = (
    "trust_product_name",
    "issue_date",
    "custody_asset_code",
    "business_asset_key",
    "receivable_contract_amount",
    "receivable_transfer_amount",
    "min_institution_transferable_amount",
    "from_trust_product_name",
    "planned_trust_product_name",
    "migration_type",
    "contract_name",
    "debtor_name",
    "property_address",
    "city",
    "contractor_name",
    "brand",
    "product_style",
    "property_status",
    "original_creditor",
    "asset_transfer_discount_rate",
    "remaining_unpaid_amount_beike_not_withheld",
    "rental_price",
    "total_rent_withholding_amount",
    "rent_withheld_amount_before_pooling",
    "withholding_periods_at_pooling",
    "initial_expected_withholding_cycle",
    "renovation_payment_method",
    "rent_withholding_ratio",
    "calculated_rent_withholding_per_period",
    "agreed_repayment_periods",
    "installment_payable_amount",
    "withheld_unpaid_amount",
    "withheld_repaid_amount",
    "transferred_receipt_total",
    "rent_withholding_received_total",
    "first_rent_withholding_date",
    "signing_date",
    "rental_contract_end_date",
    "expected_last_rent_payment_date_initial",
    "expected_receivable_due_date",
    "migration_reason",
    "issuance_weight",
    "trust_asset_id",
    "from_trust_product_id",
    "planned_trust_product_id",
    "source_file_name",
    "source_sheet_name",
    "source_row_number",
    "created_at",
    "updated_at",
    "id",
    "trust_product_id",
)

MONEY_COLUMNS = frozenset({
    "receivable_contract_amount",
    "receivable_transfer_amount",
    "min_institution_transferable_amount",
    "remaining_unpaid_amount_beike_not_withheld",
    "rental_price",
    "total_rent_withholding_amount",
    "rent_withheld_amount_before_pooling",
    "calculated_rent_withholding_per_period",
    "installment_payable_amount",
    "withheld_unpaid_amount",
    "withheld_repaid_amount",
    "transferred_receipt_total",
    "rent_withholding_received_total",
})

RATE_COLUMNS = frozenset({
    "rent_withholding_ratio",
    "asset_transfer_discount_rate",
})

DATE_COLUMNS = frozenset({
    "issue_date",
    "first_rent_withholding_date",
    "signing_date",
    "rental_contract_end_date",
    "expected_last_rent_payment_date_initial",
    "expected_receivable_due_date",
})

TIMESTAMP_COLUMNS = frozenset({"created_at", "updated_at"})

NUMERIC_COLUMNS = frozenset({
    "id",
    "trust_product_id",
    "from_trust_product_id",
    "planned_trust_product_id",
    "trust_asset_id",
    "withholding_periods_at_pooling",
    "agreed_repayment_periods",
    "source_row_number",
    "issuance_weight",
}).union(MONEY_COLUMNS, RATE_COLUMNS)


def field_label(key: str) -> str:
    return FIELD_LABELS.get(key, key)


def migration_type_label(value: str | None) -> str:
    return ic.migration_type_label(value)


def format_money(value) -> str:
    return f"¥{float(value):,.2f}"


def format_rate(value) -> str:
    rate = float(value)
    if abs(rate) <= 1:
        return f"{rate * 100:.2f}%"
    return f"{rate:.2f}%"


def _format_timestamp(value) -> str:
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(DISPLAY_TZ).strftime("%Y-%m-%d %H:%M")
    text = str(value).strip()
    if not text:
        return "—"
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(DISPLAY_TZ).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text


def _format_date(value) -> str:
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text[:10] if text else "—"


def format_cell(key: str, value) -> str:
    if value is None or value == "":
        return "—"
    if key in TIMESTAMP_COLUMNS:
        return _format_timestamp(value)
    if key in DATE_COLUMNS:
        return _format_date(value)
    if key == "migration_type":
        return migration_type_label(str(value))
    if key in MONEY_COLUMNS:
        try:
            return format_money(value)
        except (TypeError, ValueError):
            return str(value)
    if key in RATE_COLUMNS:
        try:
            return format_rate(value)
        except (TypeError, ValueError):
            return str(value)
    return str(value)
