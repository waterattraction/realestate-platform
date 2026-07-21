"""还款披露 / 资产监控 Excel 模版列契约（与 excel文件/*模版.xlsx 对齐）."""

from __future__ import annotations

from typing import Any

# 还款明细披露信息模版 · Sheet「还款明细」
# 资产包编号已 DROP；资产编号(房源) 展示/导出 = asset_code（主编号，左 12）
REPAYMENT_DETAIL_TEMPLATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("trust_product_name", "信托产品"),
    ("current_payer", "当前还款方"),
    ("asset_code", "资产编号(房源)"),
    ("planned_repayment_amount", "当期计划还款金额"),
    ("initial_renovation_amount", "初始受让装修金额"),
    ("cumulative_repaid_amount", "累计已还款金额"),
    ("remaining_balance", "剩余应还款余额"),
    ("actual_repayment_amount", "当期实际还款金额"),
)

# 还款明细披露信息模版 · Sheet「回款计划」
# 资产编号(房源) = asset_code（主编号，左 12）
REPAYMENT_PLAN_TEMPLATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("trust_product_name", "信托产品"),
    ("asset_code", "资产编号(房源)"),
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

# 资产监控表模版（导入 / 资产监控导出）
MONITOR_TEMPLATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("asset_code", "资产编号(房源)"),
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

# 资产监控披露：在资产状态后增加逾期天数；资产状态由披露层按 M 级覆写
DISCLOSURE_MONITOR_TEMPLATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("asset_code", "资产编号(房源)"),
    ("renovation_vendor", "装修服务商"),
    ("data_date", "统计日期"),
    ("initial_transfer_amount", "初始受让金额"),
    ("repaid_amount", "已还款金额"),
    ("remaining_amount", "剩余还款金额"),
    ("asset_status", "资产状态"),
    ("overdue_days", "逾期天数"),
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
