"""导入预检页 — 共用中文标签（发行 / 资产情况）."""

from __future__ import annotations

import json

IMPORT_ACTION_LABELS: dict[str, str] = {
    "import": "导入",
    "overwrite": "覆盖",
    "needs_confirm": "待确认",
    "failed": "失败",
    "skip": "跳过",
    "reject": "拒绝",
    "imported": "已导入",
    "overwritten": "已覆盖",
    "not_selected": "未选中",
}

SHEET_TYPE_LABELS: dict[str, str] = {
    "asset_monitor": "资产监控",
    "repayment_detail": "还款明细",
    "repayment_plan": "回款计划",
    "issuance_asset": "发行资产明细",
    "ambiguous_sheet_type": "Sheet类型冲突",
    "unknown": "无法识别",
}

PREVIEW_BTN_SELECT_IMPORT = "全选可导入"
PREVIEW_BTN_EXCLUDE_CONFIRM = "仅导入（排除待确认）"


def preview_script_helpers() -> str:
    """嵌入 upload 页 <script>：枚举值 → 中文."""
    action_json = json.dumps(IMPORT_ACTION_LABELS, ensure_ascii=False)
    type_json = json.dumps(SHEET_TYPE_LABELS, ensure_ascii=False)
    return f"""
    const IMPORT_ACTION_LABELS = {action_json};
    const SHEET_TYPE_LABELS = {type_json};
    function importActionLabel(v) {{
        if (!v || v === '—') return v;
        return IMPORT_ACTION_LABELS[v] || v;
    }}
    function sheetTypeLabel(v) {{
        if (!v || v === '—') return v;
        return SHEET_TYPE_LABELS[v] || v;
    }}
    function previewStatusClass(st) {{
        if (st === 'failed' || st === 'reject') return 'err';
        if (st === 'needs_confirm') return 'warn';
        return 'ok';
    }}
    """
