"""还款披露 / 资产监控 Excel 模版列契约（与 excel文件/*模版.xlsx 对齐）."""

from __future__ import annotations

from typing import Any

# 还款明细披露信息模版 · Sheet「还款明细」
REPAYMENT_DETAIL_TEMPLATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("asset_pool_code", "资产包编号"),
    ("current_payer", "当前还款方"),
    ("custody_asset_code", "托管房源编码"),
    ("planned_repayment_amount", "当期计划还款金额"),
    ("initial_renovation_amount", "初始受让装修金额"),
    ("cumulative_repaid_amount", "累计已还款金额"),
    ("remaining_balance", "剩余应还款余额"),
    ("actual_repayment_amount", "当期实际还款金额"),
    ("overdue_days", "当期逾期天数"),  # 导出时取自监控，不从还款 Excel 导入
)

# 还款明细披露信息模版 · Sheet「回款计划」
REPAYMENT_PLAN_TEMPLATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("asset_pool_code", "资产包编号"),
    ("source_asset_code", "资产编号(房源)"),
    ("renovation_vendor", "装修服务商"),
    ("data_date", "统计日期"),
    ("initial_transfer_amount", "初始受让金额"),
    ("repaid_amount", "已还款金额"),
    ("remaining_amount", "剩余还款金额"),
    ("community_name", "小区名称"),
    ("city", "城市"),
    ("current_bill_date", "当期账单日"),
    ("repayment_amount_detail", "回款金额明细"),
    ("planned_monthly_repayment_amount", "后续计划每月回款金额"),
    ("final_planned_repayment_amount", "最后一期计划回款金额"),
)

# 资产监控表模版
MONITOR_TEMPLATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("asset_pool_code", "资产包编号"),
    ("source_asset_code", "资产编号(房源)"),
    ("renovation_vendor", "装修服务商"),
    ("data_date", "统计日期"),
    ("initial_transfer_amount", "初始受让金额"),
    ("repaid_amount", "已还款金额"),
    ("remaining_amount", "剩余还款金额"),
    ("asset_status", "资产状态"),
    ("last_renovation_payment_date", "最后一期装修款付款时间"),
    ("community_name", "小区名称"),
    ("city", "城市"),
    ("collection_contract_code", "收房合同编码"),
    ("custody_agreement_sign_date", "托管协议签署日期"),
    ("collection_contract_years", "收房合同签约年数"),
    ("owner_code", "业主代码"),
    ("withholding_ratio", "代扣比例"),
    ("actual_monthly_rent", "实际出房月租金"),
)

# 回款计划独有列（监控模版无）
REPAYMENT_PLAN_ONLY_COLUMNS: tuple[str, ...] = (
    "当期账单日",
    "回款金额明细",
    "后续计划每月回款金额",
    "最后一期计划回款金额",
)


def template_headers(columns: tuple[tuple[str, str], ...]) -> list[str]:
    return [label for _, label in columns]


def template_field_keys(columns: tuple[tuple[str, str], ...]) -> list[str]:
    return [key for key, _ in columns]


def row_values_for_template(
    item: dict[str, Any],
    columns: tuple[tuple[str, str], ...],
    *,
    format_cell,
) -> list[Any]:
    return [format_cell(key, item.get(key)) for key, _ in columns]
