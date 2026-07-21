"""Overdue workbench HTML — dumb render from get_detail() DTO only."""

import json
import re
from datetime import date, datetime, timezone
from html import escape
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

_DISPLAY_TZ = ZoneInfo("Asia/Shanghai")

from app.field_labels import (
    ASSET_CODE_LABEL,
    CUSTODY_ASSET_CODE_LABEL,
    SOURCE_ASSET_CODE_LABEL,
)
from app.html.formatters import (
    fmt_check_result,
    fmt_delinquency_badge,
    fmt_money,
    fmt_risk_badge,
)
from app.issuance_labels import format_rate, migration_type_label
from app.overdue.ui_constants import (
    DELINQUENCY_BUCKET_COLORS,
    FOLLOWUP_CASE_CATEGORIES,
    FOLLOWUP_STATUS_LABELS,
    INTERNAL_STATUS_DEFAULT,
    INTERNAL_STATUS_OPTIONS,
    TRUST_MARKER_DEFAULT,
    TRUST_MARKER_OPTIONS,
    TRUST_MARKER_VISUAL,
)
from app.service.checks_service import RECONCILIATION_BASIS_LABEL
from app.ui_css import (
    BTN_CSS,
    PAGE_CHROME_CSS,
    STANDARD_HEADER_CSS,
    TABLE_SCROLL_CSS,
    WORKBENCH_BODY_CSS,
)

_TIMELINE_PREVIEW = 3
_REPAYMENT_PREVIEW = 3
_PANEL_PREVIEW_ROWS = 3

_BUCKET_FILTER_OPTIONS = [
    ("ES", "ES"),
    ("M0", "M0"),
    ("M0_5", "M0.5"),
    ("M1", "M1"),
    ("M1_PLUS", "M1+"),
    ("M0_PLUS", "M0+"),
]


def _filter_bar_product_ids(dto: dict) -> list[int] | None:
    """左侧清单产品范围：None=全部；list=已选。"""
    filters = dto.get("filters") or {}
    if "list_product_ids" in filters:
        return filters.get("list_product_ids")
    if filters.get("list_product_scope_explicit"):
        single = filters.get("list_product_id")
        return [int(single)] if single is not None else None
    pid = dto.get("trust_product_id")
    return [int(pid)] if pid is not None else None


def _product_filter_label(products: list[dict], selected_ids: list[int] | None) -> str:
    if not selected_ids:
        return "全部产品"
    name_by_id = {int(p["id"]): str(p["name"]) for p in products}
    names = [name_by_id.get(pid, str(pid)) for pid in selected_ids]
    if len(names) == 1:
        return names[0]
    return f"已选{len(names)}产品"


def _append_list_product_qs(parts: list[str], filters: dict) -> None:
    """写入清单产品筛选；显式「全部」用 list_product_id=。"""
    if not filters.get("list_product_scope_explicit"):
        return
    ids = filters.get("list_product_ids")
    if ids is None:
        parts.append("list_product_id=")
        return
    if len(ids) == 1:
        parts.append(f"list_product_id={ids[0]}")
        return
    for pid in ids:
        parts.append(f"list_product_ids={int(pid)}")


def _filter_buckets(filters: dict) -> list[str] | None:
    buckets = filters.get("delinquency_buckets")
    if buckets is None and filters.get("delinquency_bucket"):
        return [str(filters["delinquency_bucket"])]
    return list(buckets) if buckets else None


def _append_str_list_qs(parts: list[str], param: str, values: list[str] | None) -> None:
    if not values:
        return
    for value in values:
        parts.append(f"{param}={quote(str(value))}")


def _append_sidebar_filter_qs(parts: list[str], filters: dict) -> None:
    buckets = _filter_buckets(filters)
    if buckets:
        _append_str_list_qs(parts, "delinquency_buckets", buckets)
    else:
        # 显式「全部等级」
        parts.append("delinquency_bucket=")
    markers = filters.get("trust_markers") or (
        [filters["trust_marker"]] if filters.get("trust_marker") else None
    )
    statuses = filters.get("followup_statuses") or (
        [filters["followup_status"]] if filters.get("followup_status") else None
    )
    cities = filters.get("cities") or (
        [filters["city"]] if filters.get("city") else None
    )
    _append_str_list_qs(parts, "trust_markers", markers)
    _append_str_list_qs(parts, "followup_statuses", statuses)
    _append_str_list_qs(parts, "cities", cities)


def _asset_list_item_href(
    item: dict,
    *,
    filters: dict,
    bucket: str,
    data_date: str | None,
) -> str:
    del bucket  # 等级以 filters 多选为准
    ac = item.get("asset_code") or ""
    pid = item.get("trust_product_id")
    parts = [f"trust_product_id={pid}", f"asset_code={quote(str(ac))}"]
    _append_sidebar_filter_qs(parts, filters)
    if data_date:
        parts.append(f"data_date={quote(str(data_date))}")
    _append_list_product_qs(parts, filters)
    return f"/overdue/workbench?{'&'.join(parts)}"


def _portfolio_href_from_workbench(dto: dict) -> str:
    """返回组合管理：按当前工作台筛选 + 当前资产现算（不使用 return_to）。"""
    filters = dto.get("filters") or {}
    asset = dto.get("asset") or {}
    summary = asset.get("summary") or {}
    pairs: list[tuple[str, str]] = []

    product_ids = filters.get("list_product_ids")
    if product_ids:
        for pid in product_ids:
            pairs.append(("trust_product_ids", str(int(pid))))

    for b in filters.get("delinquency_buckets") or (
        [filters["delinquency_bucket"]] if filters.get("delinquency_bucket") else []
    ):
        pairs.append(("delinquency_buckets", str(b)))

    for m in filters.get("trust_markers") or (
        [filters["trust_marker"]] if filters.get("trust_marker") else []
    ):
        pairs.append(("trust_markers", str(m)))

    for s in filters.get("followup_statuses") or (
        [filters["followup_status"]] if filters.get("followup_status") else []
    ):
        pairs.append(("internal_statuses", str(s)))

    for c in filters.get("cities") or (
        [filters["city"]] if filters.get("city") else []
    ):
        pairs.append(("cities", str(c)))

    asset_code = dto.get("asset_code")
    asset_bucket = summary.get("delinquency_bucket")
    if asset_bucket:
        pairs.append(("portfolio_tab", str(asset_bucket)))
    if asset_code:
        pairs.append(("focus_asset", str(asset_code)))

    qs = urlencode(pairs)
    return f"/overdue?{qs}" if qs else "/overdue"


def _is_selected_asset_item(
    item_product_id,
    item_asset_code,
    *,
    selected_product_id: int | None,
    selected_asset_code: str | None,
) -> bool:
    if not selected_asset_code or not selected_product_id:
        return False
    return (
        str(item_asset_code) == str(selected_asset_code)
        and int(item_product_id) == int(selected_product_id)
    )


def _make_workbench_qs(dto: dict):
    """Build workbench query-string helper from page/detail DTO."""
    trust_product_id = dto.get("trust_product_id")
    current_asset_code = dto.get("asset_code")
    filters = dto.get("filters") or {}
    asset = dto.get("asset") or {}
    selected_trust_asset_id = asset.get("selected_trust_asset_id")

    def workbench_qs(
        trust_asset_id: int | None = None, asset_code: str | None = None
    ) -> str:
        parts: list[str] = []
        if trust_product_id is not None:
            parts.append(f"trust_product_id={trust_product_id}")
        ac = asset_code if asset_code is not None else current_asset_code
        if ac:
            parts.append(f"asset_code={quote(str(ac))}")
        _append_sidebar_filter_qs(parts, filters)
        if dto.get("data_date"):
            parts.append(f"data_date={quote(str(dto['data_date']))}")
        tid = trust_asset_id if trust_asset_id is not None else selected_trust_asset_id
        if tid is not None:
            parts.append(f"trust_asset_id={tid}")
        _append_list_product_qs(parts, filters)
        return "?" + "&".join(parts) if parts else ""

    return workbench_qs


def _compute_followup_pane_state(
    asset: dict,
    *,
    new_followup: bool = False,
    new_followup_case: bool = False,
    followup_expanded: bool = False,
    followup_entry_id: int | None = None,
    followup_case_id: int | None = None,
) -> tuple[str, bool, bool]:
    """Return (initial_followup_pane, force_new_case, scroll_followup)."""
    followup_entries_for_pane = asset.get("followup_entries") or []
    followup_cases_for_pane = asset.get("followup_cases") or []
    initial_followup_pane = ""
    if followup_entry_id and any(
        int(e["id"]) == followup_entry_id for e in followup_entries_for_pane
    ):
        initial_followup_pane = f"followup-pane-entry-{followup_entry_id}"
    elif new_followup_case:
        initial_followup_pane = "followup-pane-new"
    elif new_followup and followup_cases_for_pane:
        initial_followup_pane = (
            f"followup-pane-new-{int(followup_cases_for_pane[0]['id'])}"
        )
    elif followup_case_id and not new_followup:
        case_entries = [
            e
            for e in followup_entries_for_pane
            if int(e.get("case_id") or 0) == int(followup_case_id)
        ]
        if case_entries:
            initial_followup_pane = f"followup-pane-entry-{int(case_entries[0]['id'])}"
        else:
            initial_followup_pane = f"followup-pane-new-{int(followup_case_id)}"
    elif followup_entries_for_pane and not new_followup:
        latest = max(
            followup_entries_for_pane,
            key=lambda e: (str(e.get("created_at") or ""), int(e.get("id") or 0)),
        )
        initial_followup_pane = f"followup-pane-entry-{int(latest['id'])}"
    elif followup_cases_for_pane and not new_followup:
        initial_followup_pane = (
            f"followup-pane-new-{int(followup_cases_for_pane[0]['id'])}"
        )
    force_new_case = bool(new_followup_case) or (
        bool(new_followup) and not followup_cases_for_pane
    )
    scroll_followup = bool(new_followup or new_followup_case or followup_expanded)
    return initial_followup_pane, force_new_case, scroll_followup


def _build_workbench_detail_meta(
    dto: dict,
    *,
    initial_followup_pane: str,
    scroll_followup: bool,
) -> dict:
    trust_product_id = dto.get("trust_product_id")
    current_asset_code = dto.get("asset_code")
    asset = dto.get("asset") or {}
    workbench_qs = _make_workbench_qs(dto)
    queue_patch = dto.get("queue_patch") or {}
    if not queue_patch and current_asset_code:
        summary = asset.get("summary") or {}
        queue_patch = {
            "trust_product_id": trust_product_id,
            "asset_code": current_asset_code,
            "internal_status": summary.get("internal_status"),
            "followup_count": len(asset.get("followup_entries") or []),
        }
    status_html = _render_queue_internal_status(queue_patch.get("internal_status"))
    identity_id = dto.get("identity_id")
    json_qs = workbench_qs()
    return {
        "trust_product_id": trust_product_id,
        "asset_code": current_asset_code,
        "identity_id": identity_id,
        "data_date": dto.get("data_date"),
        "followup_pane": initial_followup_pane,
        "scroll_followup": scroll_followup,
        "json_href": f"/overdue/workbench/detail{json_qs}",
        "asset_workbench_href": (
            f"/asset-workbench/{identity_id}" if identity_id else ""
        ),
        "queue_patch": {
            "trust_product_id": queue_patch.get("trust_product_id"),
            "asset_code": queue_patch.get("asset_code"),
            "internal_status": queue_patch.get("internal_status"),
            "followup_count": queue_patch.get("followup_count"),
            "internal_status_html": status_html,
        },
    }


def render_workbench_detail_main(
    dto: dict,
    *,
    new_followup: bool = False,
    new_followup_case: bool = False,
    followup_expanded: bool = False,
    settlement_expanded: bool = False,
    followup_entry_id: int | None = None,
    followup_case_id: int | None = None,
) -> str:
    """Render ``<main id="workbench-detail">`` (detail grid + follow-up bar)."""
    trust_product_id = dto.get("trust_product_id")
    current_asset_code = dto.get("asset_code")
    filters = dto.get("filters") or {}
    buckets = _filter_buckets(filters)
    delinquency_bucket = buckets[0] if buckets else ""
    asset = dto.get("asset") or {}
    workbench_qs = _make_workbench_qs(dto)

    product_hidden = (
        f'<input type="hidden" name="trust_product_id" value="{trust_product_id}">'
        if trust_product_id is not None
        else ""
    )
    asset_hidden = (
        f'<input type="hidden" name="asset_code" value="{escape(str(current_asset_code))}">'
        if current_asset_code
        else ""
    )
    bucket_hidden = (
        f'<input type="hidden" name="delinquency_bucket" value="{escape(delinquency_bucket)}">'
        if delinquency_bucket
        else ""
    )

    detail_html = _render_panels(dto, asset, workbench_qs)
    open_followup = bool(new_followup or new_followup_case or followup_expanded)
    # 互斥：结算与跟进不同时展开；若两者都请求，优先跟进
    open_settlement = bool(settlement_expanded) and not open_followup
    initial_followup_pane, force_new_case, scroll_followup = _compute_followup_pane_state(
        asset,
        new_followup=new_followup,
        new_followup_case=new_followup_case,
        followup_expanded=open_followup,
        followup_entry_id=followup_entry_id,
        followup_case_id=followup_case_id,
    )
    write_mode = "collapsed"
    if open_settlement:
        write_mode = "settlement"
    elif open_followup:
        write_mode = "followup"
    write_bar = ""
    if asset.get("selected_split") or asset.get("monitor", {}).get("splits"):
        write_bar = _panel_followup_write(
            product_hidden,
            asset_hidden,
            bucket_hidden,
            workbench_qs,
            dto,
            write_mode=write_mode,
            initial_pane=initial_followup_pane or "followup-pane-new",
            selected_case_id=followup_case_id,
            force_new_case=force_new_case,
        )

    meta = _build_workbench_detail_meta(
        dto,
        initial_followup_pane=initial_followup_pane,
        scroll_followup=scroll_followup,
    )
    meta_json = escape(json.dumps(meta, ensure_ascii=False, default=str), quote=True)
    scroll_flag = "1" if scroll_followup else "0"
    scroll_settlement = "1" if write_mode == "settlement" else "0"
    return (
        f'<main id="workbench-detail" class="detail-main"'
        f' data-scroll-followup="{scroll_flag}"'
        f' data-scroll-settlement="{scroll_settlement}"'
        f' data-followup-pane="{escape(initial_followup_pane)}"'
        f' data-wb-meta="{meta_json}">'
        f"{detail_html}{write_bar}</main>"
    )


def build_workbench_fragment_payload(
    dto: dict,
    *,
    new_followup: bool = False,
    new_followup_case: bool = False,
    followup_expanded: bool = False,
    settlement_expanded: bool = False,
    followup_entry_id: int | None = None,
    followup_case_id: int | None = None,
) -> dict:
    """HTML fragment + meta for partial workbench refresh."""
    asset = dto.get("asset") or {}
    open_followup = bool(new_followup or new_followup_case or followup_expanded)
    initial_followup_pane, _force, scroll_followup = _compute_followup_pane_state(
        asset,
        new_followup=new_followup,
        new_followup_case=new_followup_case,
        followup_expanded=open_followup,
        followup_entry_id=followup_entry_id,
        followup_case_id=followup_case_id,
    )
    html = render_workbench_detail_main(
        dto,
        new_followup=new_followup,
        new_followup_case=new_followup_case,
        followup_expanded=followup_expanded,
        settlement_expanded=settlement_expanded,
        followup_entry_id=followup_entry_id,
        followup_case_id=followup_case_id,
    )
    meta = _build_workbench_detail_meta(
        dto,
        initial_followup_pane=initial_followup_pane,
        scroll_followup=scroll_followup,
    )
    return {"html": html, "meta": meta}


def render_overdue_workbench_html(
    dto: dict,
    *,
    new_followup: bool = False,
    new_followup_case: bool = False,
    followup_expanded: bool = False,
    settlement_expanded: bool = False,
    followup_entry_id: int | None = None,
    followup_case_id: int | None = None,
) -> str:
    if dto.get("legacy_error"):
        return _render_legacy_error_page(dto)

    trust_product_id = dto.get("trust_product_id")
    current_asset_code = dto.get("asset_code")
    workbench_qs = _make_workbench_qs(dto)

    sidebar_html = _render_sidebar(dto, trust_product_id, current_asset_code, workbench_qs)
    detail_main = render_workbench_detail_main(
        dto,
        new_followup=new_followup,
        new_followup_case=new_followup_case,
        followup_expanded=followup_expanded,
        settlement_expanded=settlement_expanded,
        followup_entry_id=followup_entry_id,
        followup_case_id=followup_case_id,
    )
    json_qs = workbench_qs()
    identity_id = dto.get("identity_id")
    header_actions = _render_header_actions(
        trust_product_id, json_qs, identity_id, dto=dto
    )
    selection_notice = _render_selection_notice(dto.get("selection_notice"))
    data_date_display = escape(str(dto.get("data_date") or ""))
    data_date_span = (
        f' <span class="header-data-date">· 数据日期 {data_date_display}</span>'
        if data_date_display else ""
    )
    _pane, _force, scroll_followup = _compute_followup_pane_state(
        dto.get("asset") or {},
        new_followup=new_followup,
        new_followup_case=new_followup_case,
        followup_expanded=bool(new_followup or new_followup_case or followup_expanded),
        followup_entry_id=followup_entry_id,
        followup_case_id=followup_case_id,
    )
    scroll_flag = "1" if scroll_followup else "0"
    scroll_settlement = (
        "1"
        if settlement_expanded
        and not (new_followup or new_followup_case or followup_expanded)
        else "0"
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>资产管理工作台 · 房地产资产证券化平台</title>
    {_WORKBENCH_CSS}
</head>
<body class="workbench-page" data-scroll-followup="{scroll_flag}" data-scroll-settlement="{scroll_settlement}" data-followup-pane="{escape(_pane)}">
<div class="page-wrap">
<div class="container">
    <div class="breadcrumb">
        <a href="/">首页</a> / <a href="/overdue">逾期管理</a> / 资产管理工作台
    </div>
    <header class="page-header">
        <div class="header-row">
            <h1>资产管理工作台</h1>
            {header_actions}
        </div>
        <p class="header-sub muted">按资产主编号统一管理监控、还款、跟进与风险。{data_date_span}</p>
        {selection_notice}
    </header>
    <div class="workbench">
        <aside class="sidebar panel">
            {sidebar_html}
        </aside>
        {detail_main}
    </div>
</div>
</div>
{_ATTACHMENT_LIGHTBOX_HTML}
{_WORKBENCH_SCRIPTS}
</body>
</html>"""


def _render_legacy_error_page(dto: dict) -> str:
    err = dto.get("legacy_error") or {}
    message = escape(str(err.get("message") or "无法打开工作台"))
    candidates = err.get("candidates") or []
    links = ""
    for cand in candidates:
        url = escape(str(cand.get("url") or ""))
        code = escape(str(cand.get("asset_code") or ""))
        links += f'<li><a href="{url}">{ASSET_CODE_LABEL} {code}</a></li>'
    list_html = f"<ul>{links}</ul>" if links else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>资产管理工作台 · 无法解析</title>
    {_WORKBENCH_CSS}
</head>
<body>
<div class="page-wrap"><div class="container">
    <div class="breadcrumb">
        <a href="/">首页</a> / <a href="/overdue">逾期管理</a> / 资产管理工作台
    </div>
    <header class="page-header">
        <h1>资产管理工作台</h1>
        <p class="header-sub muted">按资产主编号统一管理监控、还款、跟进与风险。</p>
    </header>
    <div class="panel" style="padding:1.25rem">
        <p class="warn-text">{message}</p>
        {list_html}
        <p style="margin-top:1rem"><a href="/overdue/workbench">返回资产清单</a></p>
    </div>
</div></div>
</body>
</html>"""


_SIDEBAR_COUNT_UNITS = {
    "trust-product": "产品",
    "delinquency-bucket": "等级",
    "trust-marker": "标记",
    "internal-status": "状态",
    "city": "城市",
}


def _sidebar_ms_trigger_label(
    selected: list[str] | None,
    *,
    all_label: str,
    label_map: dict[str, str] | None = None,
    unit: str = "项",
) -> str:
    if not selected:
        return all_label
    labels = [(label_map or {}).get(v, v) for v in selected]
    if len(labels) == 1:
        return labels[0]
    return f"已选{len(labels)}{unit}"


def _render_sidebar_str_multiselect(
    *,
    key: str,
    param_name: str,
    title: str,
    options: list[tuple[str, str]],
    selected: list[str] | None,
    all_label: str,
) -> str:
    all_mode = selected is None
    trigger = escape(
        _sidebar_ms_trigger_label(
            selected,
            all_label=all_label,
            label_map=dict(options),
            unit=_SIDEBAR_COUNT_UNITS.get(key, "项"),
        )
    )
    opts_html = (
        f'<label class="multiselect-option multiselect-all">'
        f'<input type="checkbox" class="ms-all"{" checked" if all_mode else ""}> 全部</label>'
    )
    selected_set = set(selected or [])
    for value, text in options:
        checked = (not all_mode) and value in selected_set
        opts_html += (
            f'<label class="multiselect-option">'
            f'<input type="checkbox" class="ms-option" name="{escape(param_name)}" '
            f'value="{escape(value)}"{" checked" if checked else ""}> '
            f"{escape(text)}</label>"
        )
    return (
        f'<span class="sf-item sf-multiselect" data-multiselect="{escape(key)}" title="{escape(title)}">'
        f'<button type="button" class="sf-display sf-multiselect-trigger" '
        f'aria-haspopup="listbox">{trigger}</button>'
        f'<div class="sf-multiselect-panel" role="listbox" hidden>{opts_html}</div>'
        f"</span>"
    )


def _render_sidebar_product_multiselect(
    products: list[dict], selected_ids: list[int] | None
) -> str:
    """工作台侧栏产品多选（与资产组合同交互）。"""
    all_mode = selected_ids is None
    trigger = escape(_product_filter_label(products, selected_ids))
    options = (
        f'<label class="multiselect-option multiselect-all">'
        f'<input type="checkbox" class="ms-all tp-all"{" checked" if all_mode else ""}> 全部</label>'
    )
    for product in products:
        pid = int(product["id"])
        checked = (not all_mode) and selected_ids is not None and pid in selected_ids
        options += (
            f'<label class="multiselect-option">'
            f'<input type="checkbox" class="ms-option tp-product" name="list_product_ids" '
            f'value="{pid}"{" checked" if checked else ""}> '
            f'{escape(str(product["name"]))}</label>'
        )
    return (
        f'<span class="sf-item sf-multiselect" data-multiselect="trust-product" title="选择信托产品">'
        f'<button type="button" class="sf-display sf-multiselect-trigger" '
        f'aria-haspopup="listbox">{trigger}</button>'
        f'<div class="sf-multiselect-panel" role="listbox" hidden>{options}</div>'
        f"</span>"
    )


def _render_sidebar_filter(dto: dict) -> str:
    """Compact inline-edit filter row rendered inside the sidebar below the panel-hd."""
    filters = dto.get("filters") or {}
    selected_ids = _filter_bar_product_ids(dto)
    data_date = dto.get("data_date") or ""
    products = dto.get("products") or []
    current_asset = dto.get("asset_code")
    detail_pid = dto.get("trust_product_id")
    city_options = dto.get("issuance_city_options") or []

    buckets_sel = _filter_buckets(filters)
    markers_sel = filters.get("trust_markers") or (
        [filters["trust_marker"]] if filters.get("trust_marker") else None
    )
    statuses_sel = filters.get("followup_statuses") or (
        [filters["followup_status"]] if filters.get("followup_status") else None
    )
    cities_sel = filters.get("cities") or (
        [filters["city"]] if filters.get("city") else None
    )

    bucket_filter = _render_sidebar_str_multiselect(
        key="delinquency-bucket",
        param_name="delinquency_buckets",
        title="选择等级",
        options=list(_BUCKET_FILTER_OPTIONS),
        selected=buckets_sel,
        all_label="全部等级",
    )
    marker_filter = _render_sidebar_str_multiselect(
        key="trust-marker",
        param_name="trust_markers",
        title="选择信托标记",
        options=[(m, m) for m in TRUST_MARKER_OPTIONS],
        selected=markers_sel,
        all_label="全部标记",
    )
    status_filter = _render_sidebar_str_multiselect(
        key="internal-status",
        param_name="followup_statuses",
        title="选择内部状态",
        options=[(s, s) for s in INTERNAL_STATUS_OPTIONS],
        selected=statuses_sel,
        all_label="全部状态",
    )
    city_filter = _render_sidebar_str_multiselect(
        key="city",
        param_name="cities",
        title="选择城市",
        options=[(c, c) for c in city_options],
        selected=cities_sel,
        all_label="全部城市",
    )

    detail_fields = ""
    if current_asset and detail_pid is not None:
        detail_fields = (
            f'<input type="hidden" name="trust_product_id" value="{detail_pid}">'
            f'<input type="hidden" name="asset_code" value="{escape(str(current_asset))}">'
        )
    date_hidden = (
        f'<input type="hidden" name="data_date" value="{escape(str(data_date))}">'
        if data_date
        else ""
    )
    return (
        f'<form class="sidebar-filter" method="get" action="/overdue/workbench" id="sf-form">'
        + _render_sidebar_product_multiselect(products, selected_ids)
        + '<span class="sf-sep">·</span>'
        + bucket_filter
        + '<span class="sf-sep">·</span>'
        + marker_filter
        + '<span class="sf-sep">·</span>'
        + status_filter
        + '<span class="sf-sep">·</span>'
        + city_filter
        + date_hidden
        + detail_fields
        + "</form>"
    )


def _render_filter_bar(dto: dict, workbench_qs) -> str:
    del workbench_qs
    filters = dto.get("filters") or {}
    active_buckets = set(_filter_buckets(filters) or [])
    selected_ids = _filter_bar_product_ids(dto)
    data_date = dto.get("data_date") or ""
    products = dto.get("products") or []
    current_asset = dto.get("asset_code")
    detail_pid = dto.get("trust_product_id")

    bucket_opts = '<option value="">全部等级</option>'
    for val, label in _BUCKET_FILTER_OPTIONS:
        sel = " selected" if val in active_buckets and len(active_buckets) == 1 else ""
        bucket_opts += f'<option value="{val}"{sel}>{escape(label)}</option>'

    detail_fields = ""
    if current_asset and detail_pid is not None:
        detail_fields = (
            f'<input type="hidden" name="trust_product_id" value="{detail_pid}">'
            f'<input type="hidden" name="asset_code" value="{escape(str(current_asset))}">'
        )

    date_hidden = ""
    if data_date:
        date_hidden = f'<input type="hidden" name="data_date" value="{escape(str(data_date))}">'

    return f"""<form class="filter-form workbench-filter" method="get" action="/overdue/workbench" id="wb-filter-form">
        {_render_sidebar_product_multiselect(products, selected_ids)}
        <label>M 级
            <select name="delinquency_bucket">{bucket_opts}</select>
        </label>
        <span class="filter-readonly-date">
            <span class="filter-readonly-lbl">数据日期</span>
            <span class="filter-date-val">{escape(str(data_date) or "—")}</span>
        </span>
        {date_hidden}
        {detail_fields}
        <button type="submit" class="btn btn-compact">应用筛选</button>
    </form>"""


def _render_selection_notice(notice: dict | None) -> str:
    if not notice or not notice.get("message"):
        return ""
    return (
        f'<p class="selection-notice muted tiny">{escape(str(notice["message"]))}</p>'
    )


def _render_header_actions(
    trust_product_id: int | None,
    json_qs: str,
    identity_id: int | None = None,
    *,
    dto: dict | None = None,
) -> str:
    _ = trust_product_id
    back_href = _portfolio_href_from_workbench(dto or {})
    extra_links = f'<a class="header-tool-link" href="/overdue/workbench/detail{json_qs}">JSON</a>'
    if identity_id:
        extra_links += (
            f'<a class="header-tool-link" href="/asset-workbench/{identity_id}">'
            f"Asset Workbench</a>"
        )
    return f"""<div class="header-actions">
        <div class="header-tool-links">{extra_links}</div>
        <div class="header-action-btns">
            <a class="btn btn-ghost" href="{escape(back_href)}">返回列表</a>
            <button type="button" class="btn btn-ghost" onclick="location.reload()">刷新数据</button>
        </div>
    </div>"""


def _overdue_label(summary: dict) -> str:
    bucket = summary.get("delinquency_bucket")
    od = summary.get("overdue_days")
    if bucket == "ES":
        return "提前结清"
    if od is not None:
        return f"逾期 {od} 天"
    return "—"


def _fmt_source_asset_code(value) -> str:
    if value is None or str(value).strip() == "":
        return "—"
    return str(value)


def _parse_dt_to_beijing(value) -> datetime | None:
    """将 DB/序列化时间统一转到北京时间（Asia/Shanghai）。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text or text == "—":
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        # timestamptz 经驱动通常带时区；无时区按 UTC（与当前 PG/容器一致）解释
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_DISPLAY_TZ)


def _fmt_date_only(value) -> str:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    dt = _parse_dt_to_beijing(value)
    if dt is not None:
        return dt.strftime("%Y-%m-%d")
    text = str(value or "").strip()
    if not text or text == "—":
        return "—"
    return text[:10]


def _fmt_beijing_datetime(value) -> str:
    """展示用时间：北京时间 YYYY-MM-DD HH:MM。"""
    dt = _parse_dt_to_beijing(value)
    if dt is not None:
        return dt.strftime("%Y-%m-%d %H:%M")
    text = str(value or "").strip()
    if not text or text == "—":
        return "—"
    return text[:16].replace("T", " ")


def _summary_tip_body(*lines: str) -> str:
    return "<br>".join(escape(l) for l in lines if l is not None and str(l).strip())


def _summary_chip(inner_html: str, tip_lines: list[str], *, extra_class: str = "") -> str:
    tips = [str(l) for l in tip_lines if l is not None and str(l).strip()]
    body = _summary_tip_body(*tips) if tips else "—"
    cls = "summary-chip has-tip"
    if extra_class:
        cls += f" {extra_class}"
    return (
        f'<span class="{cls}">'
        f'{inner_html}<span class="tip-panel" role="tooltip">{body}</span></span>'
    )


def _summary_sep() -> str:
    return '<span class="summary-sep" aria-hidden="true">·</span>'


def _render_editable_mark_chip(
    display_text: str,
    field: str,
    pid,
    ac_raw,
    data_date,
    options_html: str,
    tip_lines: list[str],
) -> str:
    inner = f"""<span class="mark-inline-group">
        <span class="mark-display">{escape(display_text)}</span>
        <select class="mark-select summary-select mark-edit-hidden" data-field="{field}"
                data-product="{pid}" data-asset-code="{escape(str(ac_raw))}" data-date="{escape(str(data_date))}">
            {options_html}
        </select>
    </span>"""
    return _summary_chip(inner, tip_lines, extra_class="summary-chip-editable")


def _render_summary_trust_marker(pid, ac_raw, data_date, marker: str) -> str:
    """资产组合同款：色点徽章 + 点击改选。"""
    current = marker if marker in TRUST_MARKER_OPTIONS else TRUST_MARKER_DEFAULT
    if marker == "未标记":
        current = TRUST_MARKER_DEFAULT
    tone, short = TRUST_MARKER_VISUAL.get(current, ("none", current))
    menu_items = ""
    for opt in TRUST_MARKER_OPTIONS:
        opt_tone, _opt_short = TRUST_MARKER_VISUAL.get(opt, ("none", opt))
        active = " is-active" if opt == current else ""
        menu_items += (
            f'<button type="button" class="trust-marker-option{active}" '
            f'data-value="{escape(opt)}" role="option" '
            f'aria-selected="{"true" if opt == current else "false"}">'
            f'<span class="trust-marker-dot tone-{opt_tone}" aria-hidden="true"></span>'
            f"<span>{escape(opt)}</span>"
            f"</button>"
        )
    return f"""<span class="summary-chip summary-chip-mark">
        <div class="trust-marker-cell" data-field="trust_marker"
             data-trust-product-id="{pid or ''}"
             data-asset-code="{escape(str(ac_raw or ''))}"
             data-data-date="{escape(str(data_date or ''))}"
             data-value="{escape(current)}">
            <button type="button" class="trust-marker-badge tone-{tone}"
                    title="信托标记：{escape(current)}"
                    aria-label="信托标记：{escape(current)}，点击修改"
                    aria-haspopup="listbox" aria-expanded="false">
                <span class="trust-marker-dot tone-{tone}" aria-hidden="true"></span>
                <span class="trust-marker-label">{escape(short)}</span>
            </button>
            <div class="trust-marker-menu" role="listbox" hidden>{menu_items}</div>
        </div>
    </span>"""


def _render_summary_internal_status(status: str) -> str:
    """资产组合同款：绿灯 / 橙计数 / 黄绿渐变「本周结算」+ 悬停 +。"""
    status = str(status or INTERNAL_STATUS_DEFAULT)
    problem_match = re.fullmatch(r"待跟进\((\d+)\)", status)
    settled_match = re.fullmatch(r"本周结算\((\d+)\)", status)
    if problem_match:
        n = problem_match.group(1)
        status_html = (
            f'<button type="button" class="internal-status-link summary-status-open" '
            f'title="待跟进({escape(n)})" aria-label="待跟进 {escape(n)} 件，打开跟进">'
            f'<span class="status-count">{escape(n)}</span></button>'
        )
    elif settled_match:
        m = settled_match.group(1)
        status_html = (
            f'<button type="button" class="internal-status-link summary-status-open" '
            f'title="本周结算({escape(m)})" aria-label="本周结算 {escape(m)} 件，打开跟进">'
            f'<span class="status-count status-count--settled">{escape(m)}</span></button>'
        )
    elif status.startswith("待跟进"):
        status_html = (
            '<button type="button" class="internal-status-link summary-status-open" '
            'title="待跟进" aria-label="待跟进，打开跟进">'
            '<span class="status-count">·</span></button>'
        )
    elif status.startswith("本周结算"):
        status_html = (
            '<button type="button" class="internal-status-link summary-status-open" '
            'title="本周结算" aria-label="本周结算，打开跟进">'
            '<span class="status-count status-count--settled">·</span></button>'
        )
    else:
        status_html = (
            '<button type="button" class="internal-status-link summary-status-open" '
            'title="正常" aria-label="正常，打开跟进">'
            '<span class="status-dot" aria-hidden="true"></span></button>'
        )
    return f"""<span class="summary-chip summary-chip-status">
        <div class="internal-status-cell">
            {status_html}
            <button type="button" class="internal-status-add summary-new-case-btn"
                    title="新增跟进事项" aria-label="新增跟进事项">+</button>
        </div>
    </span>"""


def _render_summary_card(dto: dict, asset: dict) -> str:
    """Summary Card — 4 scan lines with hover detail chips."""
    summary = asset.get("summary") or {}
    checks = asset.get("checks")
    trust_mark = asset.get("trust_mark") or {}
    followup_case = asset.get("followup_case") or {}
    timeline = asset.get("timeline") or []
    repayment = asset.get("repayment") or {}
    ops = asset.get("ops") or {}
    monitor = asset.get("monitor") or {}
    splits = monitor.get("splits") or []

    asset_code_raw = asset.get("asset_code") or dto.get("asset_code") or "—"
    asset_code = escape(str(asset_code_raw))
    custodies = asset.get("custody_asset_codes") or dto.get("custody_asset_codes") or []
    custody_str = "、".join(str(c) for c in custodies) if custodies else "—"

    bucket = summary.get("delinquency_bucket")
    remaining = summary.get("remaining_amount")
    repaid = summary.get("repaid_amount")
    initial = summary.get("initial_transfer_amount")
    overdue_days = summary.get("overdue_days")

    if bucket == "ES":
        overdue_str = "提前结清"
        od_style = ""
    elif overdue_days is not None:
        overdue_str = f"{overdue_days}天"
        od_color = DELINQUENCY_BUCKET_COLORS.get(bucket or "", "#94a3b8")
        od_style = f" color:{od_color}; font-weight:600;"
    else:
        overdue_str = "—"
        od_style = ""

    pid = dto.get("trust_product_id")
    ac_raw = asset_code_raw if asset_code_raw != "—" else ""
    data_date = dto.get("data_date") or ""
    data_date_str = escape(str(data_date or "—"))
    current_marker = trust_mark.get("trust_marker") or TRUST_MARKER_DEFAULT
    current_internal = (
        trust_mark.get("internal_status")
        or summary.get("internal_status")
        or INTERNAL_STATUS_DEFAULT
    )
    followup_count = len([e for e in timeline if e.get("event_type") == "followup"])
    product_name = summary.get("trust_product_name") or "—"
    risk_score = summary.get("risk_score")

    asset_tip = [
        f"{CUSTODY_ASSET_CODE_LABEL}：{custody_str}",
        f"信托产品：{product_name}",
    ]

    m_tip = [f"逾期阶段：{bucket or '—'}"]
    if risk_score is not None:
        m_tip.append(f"风险分：{risk_score}")

    od_tip = []
    if bucket == "ES":
        od_tip.append("资产已提前结清")
    elif overdue_days is not None:
        od_tip.append(f"汇总逾期：{overdue_days} 天")
        for s in splits:
            sod = s.get("overdue_days")
            if sod is not None:
                od_tip.append(
                    f"{s.get('custody_asset_code') or '—'}：{sod} 天"
                )

    initial_tip: list[str] = [
        f"监控初始受让 {fmt_money(initial)}",
        f"{fmt_money(initial)} − {fmt_money(repaid)} = {fmt_money(remaining)}",
    ]
    for s in splits[:3]:
        split_initial = s.get("initial_transfer_amount")
        if split_initial is not None:
            initial_tip.append(
                f"{s.get('custody_asset_code') or '—'}：{fmt_money(split_initial)}"
            )

    repayment_items = repayment.get("items") or []
    recent_repay = repayment.get("recent_repayment_date")
    recent_repay_str = _fmt_date_only(recent_repay)
    repaid_tip: list[str] = [f"还款明细 {len(repayment_items)} 条"]
    for item in repayment_items[:3]:
        repaid_tip.append(
            f"{_fmt_date_only(item.get('repayment_date'))} · {fmt_money(item.get('actual_repayment_amount'))}"
        )

    remain_tip = [
        f"{fmt_money(initial)} − {fmt_money(repaid)} = {fmt_money(remaining)}",
        "（监控初始 − 已还 = 剩余）",
    ]

    if checks:
        bal = checks["balance_equation"]
        cross = checks["cross_sheet_repayment"]
        bal_passed = bal["passed"]
        cross_passed = cross["passed"]
        bal_label = "余额✓" if bal_passed else "余额⚠"
        cross_label = "还款✓" if cross_passed else "还款⚠"
        bal_cls = "check-ok" if bal_passed else "check-bad"
        cross_cls = "check-ok" if cross_passed else "check-bad"
        bal_tip = [
            f"剩余 {fmt_money(bal['left_amount'])} vs 初始−已还 {fmt_money(bal['right_amount'])}",
            f"差额 {fmt_money(bal['diff_amount'])}",
            f"核对基准：{RECONCILIATION_BASIS_LABEL}",
        ]
        cross_tip = [
            f"监控已还 {fmt_money(cross['left_amount'])} vs 还款明细 {fmt_money(cross['right_amount'])}",
            f"差额 {fmt_money(cross['diff_amount'])}",
            f"核对基准：{RECONCILIATION_BASIS_LABEL}",
        ]
    else:
        bal_label = cross_label = "—"
        bal_cls = cross_cls = ""
        bal_tip = cross_tip = []

    count_tip = [f"跟进记录 {followup_count} 条"]
    for ev in timeline:
        if ev.get("event_type") != "followup":
            continue
        count_tip.append(
            f"{_fmt_date_only(ev.get('occurred_at'))} · {ev.get('title') or '—'}"
        )
        if len(count_tip) >= 4:
            break

    actions = ops.get("recommended_actions") or []
    first_action = actions[0].get("label") if actions else None
    sla = ops.get("sla") or {}

    line4_tip: list[str] = ["── 监控 ──", f"数据日期：{data_date or '—'}"]
    for s in splits:
        sod = s.get("overdue_days")
        line4_tip.append(
            f"{s.get('custody_asset_code') or '—'} · "
            f"逾期 {sod if sod is not None else '—'}天 · "
            f"{s.get('delinquency_bucket') or '—'}"
        )
    if not splits:
        line4_tip.append("暂无监控分笔")

    line4_tip.append("── 还款 ──")
    if repayment_items:
        for item in repayment_items[:3]:
            line4_tip.append(
                f"{_fmt_date_only(item.get('repayment_date'))} · {fmt_money(item.get('actual_repayment_amount'))}"
            )
    else:
        line4_tip.append("暂无还款明细")

    line4_tip.append("── Ops ──")
    ops_detail_count = 0
    if ops.get("bucket") or ops.get("risk_level"):
        line4_tip.append(
            f"逾期阶段 {ops.get('bucket') or '—'} · 风险 {ops.get('risk_level') or '—'}"
        )
        ops_detail_count += 1
    if sla.get("due_date"):
        sla_state = "已超期" if sla.get("is_breached") else "正常"
        line4_tip.append(f"SLA 截止 {_fmt_date_only(sla.get('due_date'))}（{sla_state}）")
        ops_detail_count += 1
    for action in actions[:5]:
        line4_tip.append(str(action.get("label") or action.get("action_type") or "—"))
        ops_detail_count += 1
    if ops_detail_count == 0:
        line4_tip.append("暂无 Ops 建议")

    anomaly_cls = " card-summary-anomaly" if summary.get("has_check_anomaly") else ""
    ops_short = escape(str(first_action)) if first_action else "暂无建议"
    sla_badge = ""
    if sla.get("is_breached"):
        sla_badge = ' <span class="badge fail-badge tiny-badge">SLA超期</span>'
    elif sla.get("due_date"):
        sla_badge = ' <span class="badge ok-badge tiny-badge">SLA正常</span>'

    od_inner = (
        f'<span style="{od_style}">{escape(overdue_str)}</span>'
        if od_style
        else escape(overdue_str)
    )

    line1 = (
        f"{_summary_chip(asset_code, asset_tip)}"
        f"{_summary_sep()}"
        f"{_summary_chip(fmt_delinquency_badge(bucket), m_tip)}"
        f"{_summary_sep()}"
        f"{_summary_chip(od_inner, od_tip or ['—'])}"
        f"{_summary_sep()}"
        f"{_render_summary_trust_marker(pid, ac_raw, data_date, current_marker)}"
    )

    initial_display = fmt_money(initial) if initial is not None else "—"
    remain_inner = f'剩余 <span class="summary-em">{fmt_money(remaining)}</span>'
    line2 = (
        f"{_summary_chip(f'初始受让 {initial_display}', initial_tip or ['—'])}"
        f"{_summary_sep()}"
        f"{_summary_chip(f'已还 {fmt_money(repaid)}', repaid_tip)}"
        f"{_summary_sep()}"
        f'{_summary_chip(remain_inner, remain_tip, extra_class="summary-chip-em")}'
    )

    if checks:
        bal_inner = f'<span class="{bal_cls}">{escape(bal_label)}</span>'
        cross_inner = f'<span class="{cross_cls}">{escape(cross_label)}</span>'
        line3 = (
            f"{_render_summary_internal_status(str(current_internal))}"
            f"{_summary_sep()}"
            f"{_summary_chip(f'{followup_count}条', count_tip)}"
            f"{_summary_sep()}"
            f"{_summary_chip(bal_inner, bal_tip)}"
            f"{_summary_sep()}"
            f"{_summary_chip(cross_inner, cross_tip)}"
        )
    else:
        line3 = (
            f"{_render_summary_internal_status(str(current_internal))}"
            f"{_summary_sep()}"
            f"{_summary_chip(f'{followup_count}条', count_tip)}"
            f"{_summary_sep()}余额 —{_summary_sep()}还款 —"
        )

    line4_inner = (
        f"监控 {data_date_str}{_summary_sep()}"
        f"末次还款 {recent_repay_str}{_summary_sep()}"
        f"建议：{ops_short}{sla_badge}"
    )
    line4 = _summary_chip(line4_inner, line4_tip, extra_class="summary-chip-line")

    return f"""<div class="card-summary card-summary-v2{anomaly_cls}">
        <div class="summary-line">{line1}</div>
        <div class="summary-line summary-line-money">{line2}</div>
        <div class="summary-line summary-line-checks">{line3}</div>
        <div class="summary-line summary-line-monitor">{line4}</div>
    </div>"""


def _render_hero_asset_card(dto: dict, asset: dict) -> str:
    """Legacy wrapper: Summary + Check in sequence (not used by detail-grid path)."""
    return _render_summary_card(dto, asset) + "\n" + _render_check_card(asset.get("checks"))


def _render_check_card(checks: dict | None) -> str:
    """Compact Check Card — shows balance equation and cross-sheet repayment results."""
    if not checks:
        return '<div class="card-check"><span class="muted tiny">金额核对：—</span></div>'
    bal = checks["balance_equation"]
    cross = checks["cross_sheet_repayment"]
    code_mismatch = checks.get("code_mismatch")
    has_anomaly = not (
        bal["passed"]
        and cross["passed"]
        and (code_mismatch is None or code_mismatch.get("passed", True))
    )
    alert_cls = " card-check-alert" if has_anomaly else ""
    bal_tip = f"剩余 {fmt_money(bal['left_amount'])} vs 初始−已还 {fmt_money(bal['right_amount'])}"
    cross_tip = (
        f"监控已还 {fmt_money(cross['left_amount'])} vs 还款明细 "
        f"{fmt_money(cross['right_amount'])}"
    )

    def check_row(label: str, passed: bool, tip: str, diff) -> str:
        res_cls = "check-pass" if passed else "check-fail"
        return (
            f'<div class="check-row" title="{escape(tip)}">'
            f'<span class="check-label">{escape(label)}</span>'
            f'<span class="check-result {res_cls}">{fmt_check_result(passed)}</span>'
            f'<span class="check-diff">差额 {fmt_money(diff)}</span>'
            f"</div>"
        )

    code_row = ""
    if code_mismatch is not None:
        code_tip = (
            f"还款明细 {code_mismatch['row_count']} 笔主编号与底层资产不一致，"
            f"涉及 {fmt_money(code_mismatch['amount_sum'])}"
        )
        code_row = check_row(
            "编码一致",
            code_mismatch.get("passed", True),
            code_tip,
            code_mismatch.get("amount_sum", 0),
        )

    return f"""<div class="card-check{alert_cls}">
        <div class="card-check-title">资产金额核对</div>
        {check_row("余额等式", bal["passed"], bal_tip, bal["diff_amount"])}
        {check_row("跨表已还", cross["passed"], cross_tip, cross["diff_amount"])}
        {code_row}
        <p class="check-basis muted tiny">核对基准：{escape(RECONCILIATION_BASIS_LABEL)}</p>
    </div>"""


def _asset_list_signature(asset_list: dict, filters: dict) -> str:
    """清单状态签名：筛选条件 + 数据日期 + 页首资产（页位置代理）。

    签名一致 = 同一筛选、同一数据页 → 恢复点击前滚动位置；
    签名变化（改筛选 / 翻页 / 换数据日）→ 对当前资产居中定位。
    """
    items = asset_list.get("items") or []
    first_key = (
        f"{items[0].get('trust_product_id')}:{items[0].get('asset_code')}"
        if items
        else ""
    )
    payload = {
        "pids": filters.get("list_product_ids"),
        "buckets": filters.get("delinquency_buckets"),
        "markers": filters.get("trust_markers"),
        "statuses": filters.get("followup_statuses"),
        "cities": filters.get("cities"),
        "dd": asset_list.get("data_date"),
        "first": first_key,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _render_sidebar(
    dto: dict,
    trust_product_id: int | None,
    current_asset_code: str | None,
    workbench_qs,
) -> str:
    asset_list = dto.get("asset_list") or {}
    filters = dto.get("filters") or {}
    asset_list_html = _render_asset_list(
        asset_list,
        trust_product_id,
        current_asset_code,
        filters,
    )
    list_count = len(asset_list.get("items") or [])
    # 清单查询有上限 100：满额时显示 100+
    list_count_label = "100+" if list_count >= 100 else str(list_count)
    sidebar_filter = _render_sidebar_filter(dto)
    list_sig = escape(_asset_list_signature(asset_list, filters), quote=True)
    return f"""
        <div class="sidebar-section">
            <div class="panel-hd">资产清单 <span class="muted tiny">· {list_count_label}</span></div>
            {sidebar_filter}
            <div class="queue-body compact-queue" id="asset-queue" data-list-sig="{list_sig}">{asset_list_html}</div>
            <script>
            (function(){{
                var queue = document.getElementById('asset-queue');
                if (!queue) return;
                var sig = queue.getAttribute('data-list-sig') || '';
                var active = queue.querySelector('.queue-item.active');

                function centerActive() {{
                    if (!active) return;
                    var top = active.offsetTop - queue.offsetTop;
                    queue.scrollTop = top - (queue.clientHeight - active.offsetHeight) / 2;
                }}

                function isActiveVisible() {{
                    if (!active) return true;
                    var qr = queue.getBoundingClientRect();
                    var ar = active.getBoundingClientRect();
                    return ar.top >= qr.top && ar.bottom <= qr.bottom;
                }}

                var saved = null;
                try {{
                    saved = JSON.parse(sessionStorage.getItem('_queueState') || 'null');
                }} catch (e) {{ saved = null; }}
                sessionStorage.removeItem('_queueState');
                sessionStorage.removeItem('_queueScroll');

                requestAnimationFrame(function() {{
                    if (saved && saved.sig === sig && typeof saved.top === 'number') {{
                        // 同筛选、同数据页：恢复点击前位置，选中项保持原位
                        queue.scrollTop = saved.top;
                        // 恢复后若选中项仍不可见（极端情况），退回居中
                        if (!isActiveVisible()) centerActive();
                        return;
                    }}
                    // 翻页 / 改筛选 / 首次进入：选中项居中
                    if (active) centerActive();
                }});

                // 点击清单项前保存当前状态（签名 + 滚动位置）
                queue.addEventListener('mousedown', function(e) {{
                    if (e.target.closest('.queue-item')) {{
                        try {{
                            sessionStorage.setItem('_queueState', JSON.stringify({{
                                sig: sig,
                                top: queue.scrollTop
                            }}));
                        }} catch (err) {{ /* ignore quota errors */ }}
                    }}
                }});
            }})();
            </script>
        </div>
    """


def _render_queue_internal_status(status: str | None) -> str:
    """清单行内状态：与组合管理同款视觉（绿灯 / 橙计数 / 黄绿「本周结算」）。"""
    status = str(status or INTERNAL_STATUS_DEFAULT)
    problem_match = re.fullmatch(r"待跟进\((\d+)\)", status)
    settled_match = re.fullmatch(r"本周结算\((\d+)\)", status)
    if problem_match:
        n = problem_match.group(1)
        return (
            f'<span class="internal-status-cell queue-status" title="待跟进({escape(n)})">'
            f'<span class="status-count">{escape(n)}</span></span>'
        )
    if settled_match:
        m = settled_match.group(1)
        return (
            f'<span class="internal-status-cell queue-status" title="本周结算({escape(m)})">'
            f'<span class="status-count status-count--settled">{escape(m)}</span></span>'
        )
    if status.startswith("待跟进"):
        return (
            '<span class="internal-status-cell queue-status" title="待跟进">'
            '<span class="status-count">·</span></span>'
        )
    if status.startswith("本周结算"):
        return (
            '<span class="internal-status-cell queue-status" title="本周结算">'
            '<span class="status-count status-count--settled">·</span></span>'
        )
    return (
        '<span class="internal-status-cell queue-status" title="正常">'
        '<span class="status-dot" aria-hidden="true"></span></span>'
    )


def _render_asset_list(
    asset_list: dict,
    trust_product_id: int | None,
    current_asset_code: str | None,
    filters: dict,
) -> str:
    items = asset_list.get("items") or []
    if not items:
        return '<div class="empty">暂无符合条件的资产</div>'
    bucket = (_filter_buckets(filters) or [""])[0]
    data_date = asset_list.get("data_date")
    html = ""
    for it in items:
        ac = it.get("asset_code") or ""
        pid = it.get("trust_product_id") or trust_product_id
        active = (
            "active"
            if _is_selected_asset_item(
                pid,
                ac,
                selected_product_id=trust_product_id,
                selected_asset_code=current_asset_code,
            )
            else ""
        )
        href = _asset_list_item_href(
            it,
            filters=filters,
            bucket=bucket,
            data_date=data_date,
        )
        bucket_html = _fmt_queue_bucket_days(
            it.get("delinquency_bucket"), it.get("overdue_days")
        )
        product_name = escape(str(it.get("trust_product_name") or ""))
        list_ids = filters.get("list_product_ids")
        show_product = product_name and (list_ids is None or len(list_ids) != 1)
        product_line = f"<span>{product_name}</span>" if show_product else ""
        status_html = _render_queue_internal_status(it.get("internal_status"))
        html += f"""
        <a class="queue-item compact {active}" id="asset-{escape(str(pid))}-{escape(str(ac))}" href="{href}">
            <div class="queue-line1">{escape(str(ac))}</div>
            <div class="queue-line2">
                {product_line}
                {bucket_html}
                {status_html}
            </div>
        </a>
        """
    return html


def _fmt_queue_bucket_days(bucket: str | None, overdue_days) -> str:
    """清单行：`M0.5 8天`（短标签 + 天数）。"""
    from app.overdue.buckets import DELINQUENCY_BUCKET_COLORS, DELINQUENCY_BUCKET_LABELS

    short = DELINQUENCY_BUCKET_LABELS.get(bucket or "", bucket or "—")
    color = DELINQUENCY_BUCKET_COLORS.get(bucket or "", "#94a3b8")
    badge = (
        f'<span class="badge" style="background: {color}22; color: {color}; '
        f'border-color: {color}55;">{escape(str(short))}</span>'
    )
    days_html = f"{escape(str(overdue_days))}天" if overdue_days is not None else "—"
    return f'<span class="queue-bucket-days">{badge} {days_html}</span>'


def _last_followup_html(summary: dict) -> str:
    at = summary.get("last_follow_up_at")
    owner = summary.get("last_follow_up_owner")
    if not at and not owner:
        return '<div class="asset-card-followup muted tiny">最近跟进：—</div>'
    at_esc = escape(_fmt_beijing_datetime(at) if at else "—")
    owner_esc = escape(str(owner or "—"))
    return f'<div class="asset-card-followup muted tiny">最近跟进：{at_esc} · {owner_esc}</div>'


def _render_asset_info_card(dto: dict, workbench_qs) -> str:
    asset = dto.get("asset")
    if not asset:
        if dto.get("asset_code"):
            return '<div class="panel-hd">资产信息</div><div class="empty">该资产暂无监控快照</div>'
        return '<div class="panel-hd">资产信息</div><div class="empty">请从资产清单选择资产。</div>'

    summary = asset.get("summary") or {}
    asset_code = escape(str(asset.get("asset_code") or "—"))
    custodies = asset.get("custody_asset_codes") or []
    custody_html = "<br>".join(escape(str(c)) for c in custodies) if custodies else "—"
    data_date = escape(str(dto.get("data_date") or "—"))
    primary = escape(str(asset.get("primary_custody_asset_code") or "—"))
    followup_line = _last_followup_html(summary)
    multi_hint = ""
    if len(custodies) > 1 and asset.get("primary_custody_asset_code"):
        multi_hint = (
            f'<p class="muted tiny">默认托管号（跟进/标记）：{primary}</p>'
        )

    splits = asset.get("monitor", {}).get("splits") or []
    selected_id = asset.get("selected_trust_asset_id")
    split_list = ""
    if len(splits) > 1:
        split_list = f'<div class="split-list">{_render_split_list(splits, selected_id, workbench_qs)}</div>'

    return f"""
    <div class="panel-hd">资产信息</div>
    <div class="asset-card">
        <p><span class="lbl">{ASSET_CODE_LABEL}</span><strong>{asset_code}</strong></p>
        <p><span class="lbl">{CUSTODY_ASSET_CODE_LABEL}</span>{custody_html}</p>
        <p><span class="lbl">监控快照</span>{data_date}</p>
        {followup_line}
        {multi_hint}
    </div>
    {split_list}
    """


def _render_split_list(queue: list, selected_id: int | None, workbench_qs) -> str:
    items = ""
    for item in queue:
        active = "active" if item["trust_asset_id"] == selected_id else ""
        recon_flag = "" if item["checks"]["cross_sheet_repayment"]["passed"] else " ⚠"
        custody = escape(str(item.get("custody_asset_code") or "—"))
        od_label = (
            f"提前结清 {item.get('last_payment_date') or '—'}"
            if item.get("delinquency_bucket") == "ES"
            else f"逾期 {item['overdue_days']}天"
        )
        badge = (
            fmt_risk_badge(item.get("risk_level"))
            if item.get("risk_level")
            else fmt_delinquency_badge(item.get("delinquency_bucket"))
        )
        score = item["risk_score"] if item.get("risk_score") is not None else "—"
        follow_label = "已跟进" if item.get("has_follow_up") else "未跟进"
        items += f"""
        <a class="queue-item compact split-item {active}"
           href="/overdue/workbench{workbench_qs(item['trust_asset_id'])}">
            <div class="queue-line1">
                <span class="queue-code" title="{CUSTODY_ASSET_CODE_LABEL}">{custody}{recon_flag}</span>
                {badge}
            </div>
            <div class="queue-line2">
                <span>{od_label}</span>
                <span>评分 {score}</span>
                <span>{follow_label}</span>
            </div>
        </a>
        """
    return items


def _render_panels(dto: dict, asset: dict, workbench_qs) -> str:
    """Right-column detail-grid: summary | issuance, repay | timeline, ops."""
    if not asset or not (asset.get("selected_split") or asset.get("monitor", {}).get("splits")):
        if dto.get("asset_code"):
            return '<div class="empty">该资产主编号暂无监控分笔数据</div>'
        return '<div class="empty">请从资产清单选择资产。</div>'
    return f"""<div class="detail-grid">
        <div class="grid-summary">{_render_summary_card(dto, asset)}</div>
        <div class="grid-issuance">{_panel_issuance(asset.get("issuance_records") or [])}</div>
        <div class="grid-repay">{_panel_repayment(asset.get("repayment") or {})}</div>
        <div class="grid-timeline">{_panel_timeline(
            asset.get("timeline") or [],
            asset.get("followup_case"),
            asset.get("summary") or {},
            asset.get("trust_mark") or {},
            asset.get("followup_entries") or [],
            asset.get("followup_cases") or [],
        )}</div>
        <div class="grid-ops">{_panel_ops(asset.get("ops"), asset.get("summary") or {}, asset.get("spatial_hint"))}</div>
    </div>"""


def _panel_issuance(records: list) -> str:
    count = len(records)
    if not records:
        inner = '<p class="empty">暂无发行明细 · <a href="/issuance/records">发行记录</a></p>'
    else:
        # Group by custody_asset_code (preserving insertion order = custody_code order)
        groups: dict[str, list] = {}
        for rec in records:
            key = rec.get("custody_asset_code") or "—"
            groups.setdefault(key, []).append(rec)

        group_blocks = ""
        for custody_code, recs in groups.items():
            rec_cards = ""
            for rec in recs:
                issue = escape(str(rec.get("issue_date") or "—"))
                product = escape(str(rec.get("trust_product_name") or ""))
                city = escape(str(rec.get("city") or ""))
                addr = escape(str(rec.get("property_address") or ""))
                debtor = escape(str(rec.get("debtor_name") or "—"))
                contract = escape(str(rec.get("contract_name") or "—"))
                signing = rec.get("signing_date")
                rental_end = rec.get("rental_contract_end_date")

                location_parts = []
                if city:
                    location_parts.append(f"城市：{city}")
                if addr:
                    location_parts.append(f"地址：{addr}")
                location_line = " · ".join(location_parts) if location_parts else "—"

                date_parts = []
                if signing:
                    date_parts.append(f"签约日 {escape(str(signing))}")
                if rental_end:
                    date_parts.append(f"租约到期 {escape(str(rental_end))}")
                date_line = " · ".join(date_parts)

                price_parts = []
                contract_amt = rec.get("receivable_contract_amount")
                transfer_amt = rec.get("receivable_transfer_amount")
                rental_price = rec.get("rental_price")
                per_period = rec.get("calculated_rent_withholding_per_period")
                ratio = rec.get("rent_withholding_ratio")
                discount = rec.get("asset_transfer_discount_rate")
                migration = rec.get("migration_type")
                from_product = rec.get("from_trust_product_name")
                if contract_amt is not None:
                    price_parts.append(f"合同金额 {fmt_money(contract_amt)}")
                if transfer_amt is not None:
                    price_parts.append(f"转让价款 {fmt_money(transfer_amt)}")
                if rental_price is not None:
                    price_parts.append(f"出房价格 {fmt_money(rental_price)}")
                if per_period is not None:
                    price_parts.append(f"每期代扣 {fmt_money(per_period)}")
                if ratio is not None:
                    price_parts.append(f"代扣比 {format_rate(ratio)}")
                if discount is not None:
                    price_parts.append(f"折价率 {format_rate(discount)}")

                meta_parts = []
                if migration:
                    meta_parts.append(f"迁移类型：{escape(migration_type_label(str(migration)))}")
                if from_product:
                    meta_parts.append(f"转出信托：{escape(str(from_product))}")
                meta_line = " · ".join(meta_parts)
                price_line = " · ".join(price_parts) if price_parts else "—"

                source = escape(str(rec.get("source_file_name") or ""))

                rec_cards += f"""<div class="issuance-record">
                    <p class="issuance-issue-date">发行日 {issue}{f' · {product}' if product else ''}</p>
                    {f'<p class="issuance-line">{meta_line}</p>' if meta_line else ''}
                    <p class="issuance-line">{location_line}</p>
                    <p class="issuance-line">债务人：{debtor} · 合同：{contract}</p>
                    <p class="issuance-line">{price_line}</p>
                    {f'<p class="issuance-line">{date_line}</p>' if date_line else ''}
                    {f'<p class="muted tiny">来源 {source}</p>' if source else ''}
                </div>"""

            multi = len(recs) > 1
            group_label = f'<span class="issuance-custody">托管房源号 {escape(custody_code)}</span>'
            if multi:
                group_blocks += f"""<details class="issuance-group">
                    <summary class="issuance-group-hd">{group_label} · {len(recs)} 条发行记录</summary>
                    {rec_cards}
                </details>"""
            else:
                group_blocks += f"""<div class="issuance-group">
                    <p class="issuance-group-hd">{group_label}</p>
                    {rec_cards}
                </div>"""

        inner = group_blocks

    return f"""<details class="info-card info-card-folded">
        <summary class="info-card-title">发行信息（{count} 条）</summary>
        <div class="info-card-body">{inner}</div>
    </details>"""


def _repayment_table_row(it: dict) -> str:
    repay_date = _fmt_date_only(it.get("repayment_date"))
    source_label = (
        "手工结算" if it.get("source") == "manual_settlement" else "导入还款"
    )
    return f"""<tr>
        <td class="cell-text">{escape(str(it.get('custody_asset_code') or '—'))}</td>
        <td class="cell-text">{escape(repay_date)}</td>
        <td class="cell-text repay-source">{escape(source_label)}</td>
        <td class="num">{fmt_money(it.get('actual_repayment_amount'))}</td>
    </tr>"""


def _build_panel_preview_table(
    *,
    colgroup_html: str,
    thead_html: str,
    items: list,
    row_fn,
    colspan: int,
    expand_summary: str,
    empty_message: str | None = None,
) -> str:
    preview_items = items[:_PANEL_PREVIEW_ROWS]
    rows: list[str] = []
    for i in range(_PANEL_PREVIEW_ROWS):
        if i < len(preview_items):
            rows.append(row_fn(preview_items[i]))
        elif i == 0 and not preview_items and empty_message:
            rows.append(f'<tr><td colspan="{colspan}" class="empty">{escape(empty_message)}</td></tr>')
        else:
            rows.append(f'<tr class="row-pad"><td colspan="{colspan}">&nbsp;</td></tr>')

    expand_block = ""
    if len(items) > _PANEL_PREVIEW_ROWS:
        more_rows = "".join(row_fn(it) for it in items[_PANEL_PREVIEW_ROWS:50])
        expand_block = f"""<details class="panel-expand">
            <summary class="panel-expand-summary muted tiny">{escape(expand_summary)}</summary>
            <div class="table-wrap panel-expand-table">
                <table class="panel-fixed-rows">
                    {colgroup_html}
                    <tbody>{more_rows}</tbody>
                </table>
            </div>
        </details>"""

    return f"""<div class="table-wrap">
        <table class="panel-fixed-rows">
            {colgroup_html}
            {thead_html}
            <tbody class="panel-preview">{"".join(rows)}</tbody>
        </table>
    </div>
    {expand_block}"""


def _followup_status_label(status: str | None) -> str:
    if not status:
        return "—"
    return FOLLOWUP_STATUS_LABELS.get(status, status)


def _followup_panel_summary(
    events: list,
    followup_case: dict | None,
    summary: dict,
    trust_mark: dict,
    followup_entries: list | None = None,
    followup_cases: list | None = None,
) -> str:
    status_label = (trust_mark or {}).get("internal_status") or summary.get("internal_status") or "正常"
    last_at = _fmt_beijing_datetime(summary.get("last_follow_up_at"))
    followup_count = len([e for e in events if e.get("event_type") == "followup"])
    case_count = len(followup_cases or [])
    return (
        f"内部状态 {escape(str(status_label))} · "
        f"跟进事项 {case_count} · "
        f"最近跟进 {escape(last_at)} · "
        f"跟进记录 {followup_count} 条"
    )


def _panel_repayment(rep: dict) -> str:
    items = rep.get("items") or []
    colgroup = """<colgroup>
        <col class="col-repay-custody">
        <col class="col-repay-date">
        <col class="col-repay-source">
        <col class="col-repay-amt">
    </colgroup>"""
    thead = f"""<thead><tr>
        <th class="cell-text">{CUSTODY_ASSET_CODE_LABEL}</th>
        <th class="cell-text">还款日</th>
        <th class="cell-text">来源</th>
        <th class="num">还款金额</th>
    </tr></thead>"""
    table_html = _build_panel_preview_table(
        colgroup_html=colgroup,
        thead_html=thead,
        items=items,
        row_fn=_repayment_table_row,
        colspan=4,
        expand_summary=f"查看全部还款明细（{len(items)} 条）",
        empty_message="缺少还款明细，逾期天数可能无法重算",
    )
    recent = _fmt_date_only(rep.get("recent_repayment_date"))
    period_n = int(rep.get("period_count") or 0)
    return f"""<div class="info-card panel-dual">
        <h3 class="info-card-title">还款情况</h3>
        <div class="info-card-body">
            <p class="panel-summary-line">已还 {period_n}次，共<strong>{fmt_money(rep.get('total_repaid'))}</strong>
            · 最近还款日 {escape(recent)}</p>
            {table_html}
        </div>
    </div>"""


def _panel_monitor(mon: dict, summary: dict, data_date: str | None) -> str:
    asset_agg = mon.get("custody") or mon.get("asset") or {}
    splits = mon.get("splits") or []
    rows = ""
    for s in splits:
        sod = s.get("overdue_days")
        rows += f"""<tr>
            <td>{escape(str(s.get('custody_asset_code') or '—'))}</td>
            <td class="num">{fmt_money(s.get('initial_transfer_amount'))}</td>
            <td class="num">{fmt_money(s.get('repaid_amount'))}</td>
            <td class="num">{fmt_money(s.get('remaining_amount'))}</td>
            <td>{sod if sod is not None else '—'}</td>
            <td>{fmt_delinquency_badge(s.get('delinquency_bucket'))}</td>
        </tr>"""
    table = f"""<div class="table-wrap"><table>
        <thead><tr><th>{CUSTODY_ASSET_CODE_LABEL}</th><th>初始</th><th>已还</th><th>剩余</th><th>逾期天数</th><th>M级</th></tr></thead>
        <tbody>{rows or '<tr><td colspan="6" class="empty">无</td></tr>'}</tbody></table></div>"""
    return f"""<div class="info-card info-card-primary">
        <h3 class="info-card-title">当前监控</h3>
        <div class="info-card-body">
            <p class="muted tiny">数据日期 {escape(str(data_date or '—'))}</p>
            {table}
        </div>
    </div>"""


def _panel_trust_mark(mark: dict, dto: dict, asset: dict) -> str:
    pid = dto.get("trust_product_id")
    ac_raw = asset.get("asset_code") or dto.get("asset_code") or ""
    data_date = dto.get("data_date")
    marker = mark.get("trust_marker") or "未标记"
    internal = mark.get("internal_status") or "待跟进"
    note = escape(str(mark.get("marker_note") or "—"))
    marker_opts = "".join(
        f'<option value="{escape(m)}"{" selected" if m == marker else ""}>{escape(m)}</option>'
        for m in TRUST_MARKER_OPTIONS
    )
    status_opts = "".join(
        f'<option value="{escape(s)}"{" selected" if s == internal else ""}>{escape(s)}</option>'
        for s in INTERNAL_STATUS_OPTIONS
    )
    return f"""<div class="info-card" id="trust-mark-panel">
        <h3 class="info-card-title">信托标注</h3>
        <div class="info-card-body">
            <div class="mark-readonly">
                <p><span class="lbl">信托标记</span><strong>{escape(marker)}</strong></p>
                <p><span class="lbl">内部状态</span><strong>{escape(internal)}</strong></p>
                <p><span class="lbl">备注</span>{note}</p>
            </div>
            <p class="muted tiny">标注按 {ASSET_CODE_LABEL} {escape(str(ac_raw or '—'))} 保存</p>
            <div class="mark-edit muted tiny">修改标注</div>
            <p><span class="lbl">信托标记</span>
            <select class="mark-select" data-field="trust_marker"
                    data-product="{pid}" data-asset-code="{escape(str(ac_raw))}" data-date="{escape(str(data_date))}">
            {marker_opts}</select></p>
            <p><span class="lbl">内部状态</span>
            <select class="mark-select" data-field="internal_status"
                    data-product="{pid}" data-asset-code="{escape(str(ac_raw))}" data-date="{escape(str(data_date))}">
            {status_opts}</select></p>
            <p class="muted tiny">修改后自动保存</p>
        </div>
    </div>"""


def _panel_ops(ops: dict | None, summary: dict, spatial_hint: dict | None = None) -> str:
    alert_cls = " ops-panel-alert" if summary.get("has_check_anomaly") else ""
    if not ops:
        spatial_line = ""
        if spatial_hint and not spatial_hint.get("ready", True):
            spatial_line = (
                f'<p class="muted tiny">{escape(str(spatial_hint.get("label") or ""))}</p>'
            )
        return f"""<div class="info-card ops-panel{alert_cls}"><h3 class="info-card-title">Ops 建议（只读）</h3>
            <p class="empty">暂无建议</p>{spatial_line}</div>"""
    actions = ops.get("recommended_actions") or []
    action_rows = "".join(
        f"<li>{escape(str(a.get('label') or a.get('action_type') or '—'))}</li>" for a in actions
    ) or "<li>—</li>"
    sla = ops.get("sla") or {}
    sla_txt = escape(str(sla.get("due_date") or "—"))
    breached = sla.get("is_breached")
    sla_badge = (
        '<span class="badge fail-badge">已超期</span>'
        if breached
        else '<span class="badge ok-badge">正常</span>'
    )
    spatial_line = ""
    if spatial_hint and not spatial_hint.get("ready", True):
        spatial_line = (
            f'<p class="muted tiny">{escape(str(spatial_hint.get("label") or ""))}</p>'
        )
    return f"""<div class="info-card ops-panel{alert_cls}">
        <h3 class="info-card-title">Ops 建议（只读）</h3>
        <div class="info-card-body">
            <p><span class="lbl">逾期阶段</span>{fmt_delinquency_badge(ops.get('bucket'))}</p>
            <p><span class="lbl">风险</span>{fmt_risk_badge(ops.get('risk_level'))}</p>
            <p>SLA 截止 {sla_txt} {sla_badge}</p>
            <p class="lbl">建议动作</p><ul class="ops-list">{action_rows}</ul>
            <p class="muted tiny">建议不等于已执行，请在底栏录入跟进</p>
            {spatial_line}
        </div>
    </div>"""


def _truncate_summary(text: str | None, max_len: int = 24) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def _timeline_summary(ev: dict) -> str:
    """保留给摘要卡等非表格用途。"""
    if ev.get("event_type") == "repayment":
        period = ev.get("period_no")
        if period is not None and str(period) != "—":
            return escape(f"期次 {period}")
        return escape(f"还款 · {_fmt_date_only(ev.get('occurred_at'))}")
    title = ev.get("title") or "跟进"
    snippet = _truncate_summary(ev.get("overdue_reason")) or _truncate_summary(
        ev.get("follow_up_plan")
    )
    if snippet:
        return f"{escape(str(title))} · {escape(snippet)}"
    return escape(str(title))


def _followup_entry_summary_text(entry: dict) -> str:
    snippet = _truncate_summary(entry.get("overdue_reason"), 48)
    if not snippet:
        snippet = _truncate_summary(entry.get("follow_up_plan"), 48)
    return snippet or "—"


def _render_followup_history_case_block(
    case: dict, entries: list[dict]
) -> str:
    cid = int(case["id"])
    created = escape(
        _fmt_yyyymmddhhmm(case.get("created_at") or case.get("opened_at"))
    )
    category = escape(str(case.get("category") or "—"))
    status = escape(_followup_status_label(case.get("status")))
    desc = escape(_truncate_summary(case.get("description"), 36) or "—")
    entry_count = len(entries)

    entry_rows = ""
    for entry in entries:
        eid = int(entry["id"])
        pane_id = f"followup-pane-entry-{eid}"
        entry_rows += f"""<tr>
            <td class="cell-text">{escape(_fmt_date_only(entry.get('created_at')))}</td>
            <td class="cell-text">{escape(str(entry.get('owner_name') or '—'))}</td>
            <td class="cell-text">
                <button type="button" class="timeline-goto-entry timeline-detail-link"
                        data-entry-pane="{pane_id}" data-case-id="{cid}">
                    {escape(_followup_entry_summary_text(entry))}
                </button>
            </td>
        </tr>"""
    if not entry_rows:
        entry_rows = (
            '<tr><td colspan="3" class="empty muted tiny">暂无跟进记录</td></tr>'
        )

    return f"""<tbody class="tl-case-block" data-case-id="{cid}">
        <tr class="tl-case-row">
            <td class="cell-text">
                <button type="button" class="tl-case-toggle" aria-expanded="false"
                        title="展开跟进记录（{entry_count}）">
                    <span class="tl-case-caret" aria-hidden="true">▶</span>
                    <span>{created}</span>
                </button>
            </td>
            <td class="cell-text">{category}</td>
            <td class="cell-text">{status}</td>
            <td class="cell-text" title="{escape(str(case.get('description') or ''))}">{desc}</td>
        </tr>
        <tr class="tl-case-detail" hidden>
            <td colspan="4">
                <div class="tl-entry-wrap">
                    <table class="tl-entry-table">
                        <thead><tr>
                            <th class="cell-text">时间</th>
                            <th class="cell-text">跟进人</th>
                            <th class="cell-text">跟进摘要</th>
                        </tr></thead>
                        <tbody>{entry_rows}</tbody>
                    </table>
                </div>
            </td>
        </tr>
    </tbody>"""


def _panel_timeline(
    events: list,
    followup_case: dict | None = None,
    summary: dict | None = None,
    trust_mark: dict | None = None,
    followup_entries: list | None = None,
    followup_cases: list | None = None,
) -> str:
    summary = summary or {}
    trust_mark = trust_mark or {}
    cases = list(followup_cases or [])
    entries = list(followup_entries or [])
    entries_by_case: dict[int, list[dict]] = {}
    for entry in entries:
        if entry.get("case_id") is None:
            continue
        entries_by_case.setdefault(int(entry["case_id"]), []).append(entry)

    if cases:
        body = "".join(
            _render_followup_history_case_block(
                case, entries_by_case.get(int(case["id"]), [])
            )
            for case in cases
        )
        table_html = f"""<div class="table-wrap">
            <table class="panel-fixed-rows tl-history-table">
                <colgroup>
                    <col class="col-tl-time">
                    <col class="col-tl-cat">
                    <col class="col-tl-status">
                    <col class="col-tl-desc">
                </colgroup>
                <thead><tr>
                    <th class="cell-text">时间</th>
                    <th class="cell-text">分类</th>
                    <th class="cell-text">状态</th>
                    <th class="cell-text">描述</th>
                </tr></thead>
                {body}
            </table>
        </div>"""
    else:
        table_html = (
            '<div class="table-wrap"><table class="panel-fixed-rows tl-history-table">'
            "<thead><tr>"
            '<th class="cell-text">时间</th>'
            '<th class="cell-text">分类</th>'
            '<th class="cell-text">状态</th>'
            '<th class="cell-text">描述</th>'
            "</tr></thead>"
            '<tbody><tr><td colspan="4" class="empty">暂无跟进事项</td></tr></tbody>'
            "</table></div>"
        )

    summary_line = _followup_panel_summary(
        events,
        followup_case,
        summary,
        trust_mark,
        followup_entries,
        followup_cases,
    )
    return f"""<div class="info-card panel-dual">
        <h3 class="info-card-title">跟进历史</h3>
        <div class="info-card-body">
            <p class="panel-summary-line">{summary_line}</p>
            {table_html}
        </div>
    </div>"""


def _followup_status_options(current: str | None) -> str:
    options = ""
    for value, label in FOLLOWUP_STATUS_LABELS.items():
        selected = " selected" if value == current else ""
        options += f'<option value="{value}"{selected}>{escape(label)}</option>'
    return options


def _followup_category_options(current: str | None) -> str:
    options = ""
    for cat in FOLLOWUP_CASE_CATEGORIES:
        selected = " selected" if cat == (current or FOLLOWUP_CASE_CATEGORIES[0]) else ""
        options += f'<option value="{escape(cat)}"{selected}>{escape(cat)}</option>'
    return options


def _fmt_yyyymmddhhmm(value) -> str:
    """事项创建时间展示：北京时间 YYYYMMDDHHMM。"""
    dt = _parse_dt_to_beijing(value)
    if dt is not None:
        return dt.strftime("%Y%m%d%H%M")
    text = str(value or "").strip()
    if not text or text == "—":
        return "—"
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 12:
        return digits[:12]
    if len(digits) >= 8:
        return (digits + "0000")[:12]
    return text[:16]


def _followup_entry_tab_label(entry: dict) -> str:
    return _fmt_date_only(entry.get("created_at"))


def _attachment_ext(file_name: str) -> str:
    i = file_name.rfind(".")
    return file_name[i:].lower() if i >= 0 else ""


def _format_attachment_short_name(file_name: str, *, stem_max: int = 5) -> str:
    """长文件名缩短为 ABCDE***.png（主名最多 5 字符 + *** + 后缀）。"""
    name = str(file_name or "").strip() or "file"
    ext = _attachment_ext(name)
    stem = name[: -len(ext)] if ext and name.lower().endswith(ext) else name
    if len(stem) <= stem_max:
        return name
    return f"{stem[:stem_max]}***{ext}"


def _attachment_open_kind(att: dict) -> str:
    ct = (att.get("content_type") or "").lower().split(";")[0].strip()
    if att.get("attachment_type") == "image" or ct.startswith("image/"):
        return "image"
    fname = str(att.get("file_name") or "")
    if _attachment_ext(fname) == ".pdf" or ct == "application/pdf":
        return "pdf"
    return "file"


def _render_saved_attachment_link(att: dict) -> str:
    """图片用小缩略图（复用原附件 URL，无额外生成）；其它文件用短文件名。"""
    aid = att.get("id")
    if not aid:
        return ""
    fname_raw = str(att.get("file_name") or "")
    fname_full = escape(fname_raw)
    kind = _attachment_open_kind(att)
    href = f"/overdue/workbench/attachments/{int(aid)}"
    if kind == "image":
        return (
            f'<a class="attachment-open-link attachment-thumb-link" data-kind="image"'
            f' href="{href}" title="{fname_full} · 点击预览">'
            f'<img class="attachment-thumb attachment-thumb--saved" src="{href}" '
            f'alt="{escape(_format_attachment_short_name(fname_raw))}" loading="lazy"></a>'
        )
    title = {"pdf": "在新标签页打开"}.get(kind, "打开或下载")
    short = escape(_format_attachment_short_name(fname_raw))
    return (
        f'<a class="attachment-open-link" data-kind="{kind}"'
        f' href="{href}" title="{fname_full} · {title}">{short}</a>'
    )


def _render_attachment_uploader(*, existing_count: int = 0, label: str = "", collapsible: bool = True) -> str:
    from app.service.followup_upload import ALLOWED_EXTENSIONS_ATTR, MAX_FILE_SIZE, MAX_FILES_PER_ENTRY

    remaining = max(0, MAX_FILES_PER_ENTRY - int(existing_count))
    toggle_label = label or f"添加附件（{int(existing_count)}/{MAX_FILES_PER_ENTRY}）"
    panel_hidden = " hidden" if collapsible else ""
    return f"""
    <div class="followup-attachment-upload span-full">
        <button type="button" class="btn btn-compact attachment-upload-toggle" aria-expanded="false">{escape(toggle_label)}</button>
        <div class="attachment-upload-panel"{panel_hidden}>
            <div class="attachment-uploader"
                 data-max-files="{MAX_FILES_PER_ENTRY}"
                 data-max-file-size="{MAX_FILE_SIZE}"
                 data-existing-count="{int(existing_count)}"
                 data-allowed-extensions="{escape(ALLOWED_EXTENSIONS_ATTR)}">
                <div class="attachment-dropzone attachment-dropzone-compact" tabindex="0">
                    <strong>拖拽、点击或 Ctrl+V 粘贴</strong>
                    <span>最多 {remaining} 个，单文件 ≤10MB</span>
                </div>
                <input class="attachment-input" type="file" name="files" multiple hidden>
                <div class="attachment-preview"></div>
                <div class="attachment-error" hidden></div>
            </div>
        </div>
    </div>"""


def _followup_entry_is_mutable(case_status: str | None) -> bool:
    return case_status in ("open", "in_progress", "settled_week")


def _render_followup_field_cell(label: str, inner_html: str) -> str:
    return (
        f'<div class="followup-field">'
        f'<span class="followup-field-label">{escape(label)}</span>'
        f"{inner_html}"
        f"</div>"
    )


def _render_followup_field_display(value, *, textarea: bool = False, extra_class: str = "") -> str:
    text = escape(str(value)) if value not in (None, "") else "—"
    cls = "field-display"
    if textarea:
        cls += " field-display--scrollcell"
    if extra_class:
        cls += f" {extra_class}"
    return f'<div class="{cls}">{text}</div>'


def _render_saved_attachment_chip(att: dict) -> str:
    aid = att.get("id")
    if not aid:
        return ""
    fname_raw = str(att.get("file_name") or "")
    fname_full = escape(fname_raw)
    kind = _attachment_open_kind(att)
    href = f"/overdue/workbench/attachments/{int(aid)}"
    if kind == "image":
        meta = (
            f'<a class="attachment-open-link attachment-thumb-link" data-kind="image"'
            f' href="{href}" title="{fname_full} · 点击预览">'
            f'<img class="attachment-thumb attachment-thumb--saved" src="{href}" '
            f'alt="{escape(_format_attachment_short_name(fname_raw))}" loading="lazy"></a>'
        )
    else:
        title = {"pdf": "在新标签页打开"}.get(kind, "打开或下载")
        short = escape(_format_attachment_short_name(fname_raw))
        meta = (
            f'<a class="attachment-open-link attachment-chip-meta-link" data-kind="{kind}"'
            f' href="{href}" title="{fname_full} · {title}">{short}</a>'
        )
    return (
        f'<span class="attachment-chip attachment-chip-saved" data-attachment-id="{int(aid)}">'
        f"{meta}"
        f'<button type="button" class="attachment-chip-remove attachment-saved-remove"'
        f' aria-label="删除附件">×</button>'
        f"</span>"
    )


def _render_followup_attachment_view(entry: dict) -> str:
    att_parts = []
    for att in entry.get("attachments") or []:
        link = _render_saved_attachment_link(att)
        if link:
            att_parts.append(link)
    content = " ".join(att_parts) if att_parts else "—"
    return f'<span class="followup-view-only">{content}</span>'


def _render_followup_attachment_edit(entry: dict) -> str:
    atts = entry.get("attachments") or []
    if not atts:
        return '<div class="followup-saved-attachments followup-edit-only"><span class="muted">—</span></div>'
    chips = [_render_saved_attachment_chip(att) for att in atts]
    chips_html = "".join(c for c in chips if c)
    return f'<div class="followup-saved-attachments followup-edit-only">{chips_html}</div>'


def _render_followup_attachment_row(entry: dict) -> str:
    return f"""<div class="followup-attachment-row">
        <div class="followup-field">
            <span class="followup-field-label">附件</span>
            <div class="field-display field-display--attachment">
                {_render_followup_attachment_view(entry)}
                {_render_followup_attachment_edit(entry)}
            </div>
        </div>
    </div>"""


def _render_followup_status_badge(status: str | None, *, view_only_class: str = "") -> str:
    label = _followup_status_label(status)
    code = escape(str(status or ""))
    extra = f" {view_only_class}" if view_only_class else ""
    return (
        f'<span class="status-badge{extra}" data-status="{code}">{escape(label)}</span>'
    )


def _render_followup_attachment_links(entry: dict) -> str:
    att_parts = []
    for att in entry.get("attachments") or []:
        link = _render_saved_attachment_link(att)
        if link:
            att_parts.append(link)
    return " ".join(att_parts) if att_parts else "—"


def _render_followup_entry_cite_attrs(entry: dict) -> str:
    return (
        f'data-owner="{escape(str(entry.get("owner_name") or ""))}" '
        f'data-reason="{escape(str(entry.get("overdue_reason") or ""))}" '
        f'data-plan="{escape(str(entry.get("follow_up_plan") or ""))}"'
    )


def _render_followup_meta_row_dual(
    *,
    created_display: str,
    owner_name: str,
) -> str:
    owner_esc = escape(owner_name)
    return f"""<div class="followup-meta-row">
        {_render_followup_field_cell(
            "跟进时间",
            f'<div class="field-display field-display--meta">{created_display}</div>',
        )}
        {_render_followup_field_cell(
            "跟进人",
            f"{_render_followup_field_display(owner_name, extra_class='followup-view-only')}"
            f'<input name="owner_name" class="followup-edit-only" value="{owner_esc}">',
        )}
    </div>"""


def _render_followup_body_grid_dual(
    *,
    reason: str = "",
    plan: str = "",
) -> str:
    fields = (
        ("原因说明", "overdue_reason", reason),
        ("跟进方案", "follow_up_plan", plan),
    )
    parts: list[str] = ['<div class="followup-body-grid">']
    for label, name, val in fields:
        parts.append(
            f'<div class="followup-field followup-scroll-cell">'
            f'<span class="followup-field-label">{escape(label)}</span>'
            f"{_render_followup_field_display(val, textarea=True, extra_class='followup-view-only')}"
            f'<textarea name="{name}" rows="2" class="followup-textarea-scroll followup-edit-only">'
            f"{escape(str(val))}</textarea>"
            f"</div>"
        )
    parts.append("</div>")
    return "\n".join(parts)


def _render_followup_attachment_zone(
    entry: dict,
    *,
    uploader_label: str = "",
    show_uploader: bool = True,
) -> str:
    attachments = entry.get("attachments") or []
    existing_count = len(attachments)
    uploader = ""
    if show_uploader:
        uploader = _render_attachment_uploader(
            existing_count=existing_count,
            label=uploader_label or f"追加附件（{existing_count}/10）",
        )
    return f"""<div class="followup-attachment-zone span-full">
        {_render_followup_attachment_row(entry)}
        <div class="followup-attachment-upload-slot followup-edit-only">{uploader}</div>
        <div class="followup-attachment-spacer followup-view-only" aria-hidden="true"></div>
    </div>"""


def _render_followup_entry_panel(
    entry: dict,
    product_hidden: str,
    asset_hidden: str,
    bucket_hidden: str,
    workbench_qs,
    data_date: str,
) -> str:
    eid = int(entry["id"])
    case_status = entry.get("case_status")
    mutable = _followup_entry_is_mutable(case_status)
    created = escape(_fmt_date_only(entry.get("created_at")))
    cite_attrs = _render_followup_entry_cite_attrs(entry)
    disabled = "" if mutable else " disabled"
    disabled_title = "" if mutable else ' title="事项已结案，记录不可编辑或删除"'
    att_count = len(entry.get("attachments") or [])
    shell_layout = f"""<div class="followup-shell-layout">
                {_render_followup_meta_row_dual(
                    created_display=created,
                    owner_name=str(entry.get("owner_name") or ""),
                )}
                {_render_followup_body_grid_dual(
                    reason=str(entry.get("overdue_reason") or ""),
                    plan=str(entry.get("follow_up_plan") or ""),
                )}
                {_render_followup_attachment_zone(
                    entry,
                    uploader_label=f"追加附件（{att_count}/10）",
                )}
            </div>"""

    delete_form = f"""
        <form class="entry-delete-form" method="post" enctype="multipart/form-data"
              action="/overdue/workbench/followups/entries/{eid}/delete{workbench_qs()}">
            <input type="hidden" name="redirect_to_workbench" value="1">
            {product_hidden}
            {asset_hidden}
            {bucket_hidden}
        </form>"""

    return f"""<div class="followup-entry-shell" data-entry-id="{eid}" data-editing="0">
        <form class="followup-form followup-entry-form" method="post" enctype="multipart/form-data"
              action="/overdue/workbench/followups/entries/{eid}{workbench_qs()}">
            <input type="hidden" name="redirect_to_workbench" value="1">
            {product_hidden}
            {asset_hidden}
            {bucket_hidden}
            <input type="hidden" name="data_date" value="{data_date}">
            {shell_layout}
            <div class="followup-actions-bar">
                <div class="followup-view-only followup-entry-view-actions">
                    <button type="button" class="btn btn-compact entry-edit-btn"{disabled}{disabled_title}>修改</button>
                    <button type="button" class="btn btn-compact entry-delete-btn"{disabled}{disabled_title}>删除</button>
                    <button type="button" class="btn btn-compact entry-cite-btn" {cite_attrs}>引用此条到新建</button>
                </div>
                <div class="followup-edit-only followup-entry-edit-actions">
                    <button type="submit" class="btn primary">保存</button>
                    <button type="button" class="btn entry-cancel-btn">取消</button>
                </div>
            </div>
        </form>
        {delete_form}
    </div>"""


def _render_followup_create_pane(
    product_hidden: str,
    asset_hidden: str,
    bucket_hidden: str,
    workbench_qs,
    data_date: str,
    *,
    case_id: int,
    owner_val: str,
    last_reason: str,
    last_plan: str,
    form_id: str = "followup-form",
) -> str:
    return f"""<div class="followup-entry-shell followup-entry-shell--create" data-editing="1">
        <form class="followup-form" id="{escape(form_id)}" method="post" enctype="multipart/form-data"
              action="/overdue/workbench/followups/entries{workbench_qs()}">
            <input type="hidden" name="redirect_to_workbench" value="1">
            {product_hidden}
            {asset_hidden}
            {bucket_hidden}
            <input type="hidden" name="data_date" value="{data_date}">
            <input type="hidden" name="case_id" value="{int(case_id)}">
            <div class="followup-shell-layout">
                {_render_followup_meta_row_dual(
                    created_display="保存后自动生成",
                    owner_name=owner_val,
                )}
                {_render_followup_body_grid_dual(
                    reason=last_reason,
                    plan=last_plan,
                )}
                {_render_followup_attachment_zone(
                    {"attachments": []},
                    uploader_label="添加附件（0/10）",
                )}
            </div>
            <div class="followup-actions-bar" id="followup-form-actions">
                <div class="followup-create-actions">
                    <button type="submit" class="btn primary">保存本次跟进</button>
                    <button type="button" class="btn followup-clear-btn">清空</button>
                </div>
            </div>
        </form>
    </div>"""


def _render_followup_case_chip(case: dict, *, active: bool) -> str:
    cid = int(case["id"])
    cat = escape(str(case.get("category") or "—"))
    status = escape(_followup_status_label(case.get("status")))
    desc = escape(_truncate_summary(case.get("description") or "", 24))
    created = escape(_fmt_yyyymmddhhmm(case.get("created_at") or case.get("opened_at")))
    active_cls = " active" if active else ""
    desc_part = f" · {desc}" if desc and desc != "—" else ""
    return (
        f'<button type="button" class="case-chip{active_cls}" data-case-id="{cid}">'
        f'<span class="case-chip-main">{cat} · {status}</span>'
        f'<span class="case-chip-sub">{created}{desc_part}</span>'
        f"</button>"
    )


def _render_followup_case_edit_panel(
    case: dict,
    product_hidden: str,
    asset_hidden: str,
    bucket_hidden: str,
    workbench_qs,
    data_date: str,
) -> str:
    cid = int(case["id"])
    desc = escape(str(case.get("description") or ""))
    created = escape(_fmt_yyyymmddhhmm(case.get("created_at") or case.get("opened_at")))
    return f"""<div class="followup-case-edit">
        <form method="post" action="/overdue/workbench/followups/cases/{cid}{workbench_qs()}">
            <input type="hidden" name="redirect_to_workbench" value="1">
            {product_hidden}
            {asset_hidden}
            {bucket_hidden}
            <input type="hidden" name="data_date" value="{data_date}">
            <div class="followup-case-edit-grid">
                {_render_followup_field_cell(
                    "分类",
                    f'<select name="category">{_followup_category_options(case.get("category"))}</select>',
                )}
                {_render_followup_field_cell(
                    "状态",
                    f'<select name="status">{_followup_status_options(case.get("status"))}</select>',
                )}
                <div class="followup-field followup-case-desc">
                    <span class="followup-field-label">描述</span>
                    <input type="text" name="description" class="followup-case-desc-input"
                           value="{desc}" placeholder="事项说明（可选）">
                </div>
                {_render_followup_field_cell(
                    "创建时间",
                    f'<div class="field-display field-display--meta">{created}</div>',
                )}
                <div class="followup-case-actions">
                    <button type="submit" class="btn btn-compact primary">保存事项</button>
                </div>
            </div>
        </form>
    </div>"""


def _render_followup_case_create_panel(
    product_hidden: str,
    asset_hidden: str,
    bucket_hidden: str,
    workbench_qs,
    data_date: str,
) -> str:
    return f"""<div class="followup-case-create">
        <form method="post" action="/overdue/workbench/followups/cases{workbench_qs()}">
            <input type="hidden" name="redirect_to_workbench" value="1">
            {product_hidden}
            {asset_hidden}
            {bucket_hidden}
            <input type="hidden" name="data_date" value="{data_date}">
            <input type="hidden" name="status" value="open">
            <div class="followup-case-edit-grid">
                {_render_followup_field_cell(
                    "分类",
                    f'<select name="category">{_followup_category_options(FOLLOWUP_CASE_CATEGORIES[0])}</select>',
                )}
                {_render_followup_field_cell(
                    "状态",
                    f'<div class="field-display field-display--meta">{escape(FOLLOWUP_STATUS_LABELS["open"])}</div>',
                )}
                <div class="followup-field followup-case-desc">
                    <span class="followup-field-label">描述</span>
                    <input type="text" name="description" class="followup-case-desc-input"
                           value="" placeholder="事项说明（可选）">
                </div>
                {_render_followup_field_cell(
                    "创建时间",
                    '<div class="field-display field-display--meta">保存后生成</div>',
                )}
                <div class="followup-case-actions">
                    <button type="submit" class="btn btn-compact primary">创建跟进事项</button>
                </div>
            </div>
        </form>
    </div>"""


def _render_settlement_attachment_link(att: dict) -> str:
    aid = att.get("id")
    if not aid:
        return ""
    fname_raw = str(att.get("file_name") or "")
    fname_full = escape(fname_raw)
    kind = _attachment_open_kind(att)
    href = f"/overdue/workbench/manual-settlements/attachments/{int(aid)}"
    if kind == "image":
        return (
            f'<a class="attachment-open-link attachment-thumb-link" data-kind="image"'
            f' href="{href}" title="{fname_full} · 点击预览">'
            f'<img class="attachment-thumb attachment-thumb--saved" src="{href}" '
            f'alt="{escape(_format_attachment_short_name(fname_raw))}" loading="lazy"></a>'
        )
    title = {"pdf": "在新标签页打开"}.get(kind, "打开或下载")
    short = escape(_format_attachment_short_name(fname_raw))
    return (
        f'<a class="attachment-open-link" data-kind="{kind}"'
        f' href="{href}" title="{fname_full} · {title}">{short}</a>'
    )


def _render_settlement_saved_attachment_chip(att: dict) -> str:
    aid = att.get("id")
    if not aid:
        return ""
    fname_raw = str(att.get("file_name") or "")
    fname_full = escape(fname_raw)
    kind = _attachment_open_kind(att)
    href = f"/overdue/workbench/manual-settlements/attachments/{int(aid)}"
    if kind == "image":
        meta = (
            f'<a class="attachment-open-link attachment-thumb-link" data-kind="image"'
            f' href="{href}" title="{fname_full} · 点击预览">'
            f'<img class="attachment-thumb attachment-thumb--saved" src="{href}" '
            f'alt="{escape(_format_attachment_short_name(fname_raw))}" loading="lazy"></a>'
        )
    else:
        title = {"pdf": "在新标签页打开"}.get(kind, "打开或下载")
        short = escape(_format_attachment_short_name(fname_raw))
        meta = (
            f'<a class="attachment-open-link attachment-chip-meta-link" data-kind="{kind}"'
            f' href="{href}" title="{fname_full} · {title}">{short}</a>'
        )
    return (
        f'<span class="attachment-chip attachment-chip-saved" data-attachment-id="{int(aid)}">'
        f"{meta}"
        f'<button type="button" class="attachment-chip-remove attachment-saved-remove"'
        f' aria-label="删除附件">×</button>'
        f"</span>"
    )


def _render_settlement_attachment_zone(settlement: dict) -> str:
    attachments = settlement.get("attachments") or []
    existing_count = len(attachments)
    if attachments:
        chips = "".join(
            c for c in (_render_settlement_saved_attachment_chip(a) for a in attachments) if c
        )
        atts_html = f'<div class="followup-saved-attachments">{chips}</div>'
    else:
        atts_html = '<div class="followup-saved-attachments"><span class="muted">暂无附件</span></div>'
    uploader = _render_attachment_uploader(
        existing_count=existing_count,
        label=f"追加附件（{existing_count}/10）",
        collapsible=True,
    )
    return f"""<div class="followup-attachment-zone span-full">
        <div class="followup-attachment-row">
            <div class="followup-field">
                <span class="followup-field-label">附件</span>
                <div class="field-display field-display--attachment">{atts_html}</div>
            </div>
        </div>
        <div class="followup-attachment-upload-slot">{uploader}</div>
    </div>"""


def _render_settlement_repayer_select(selected: str | None = None) -> str:
    from app.manual_settlement import DEFAULT_REPAYER, REPAYER_OPTIONS

    current = (selected or "").strip() or DEFAULT_REPAYER
    opts = []
    for name in REPAYER_OPTIONS:
        sel = " selected" if name == current else ""
        opts.append(f'<option value="{escape(name)}"{sel}>{escape(name)}</option>')
    return (
        f'<select name="repayer" required class="settlement-repayer-select">'
        f"{''.join(opts)}</select>"
    )


def _render_settlement_create_fields(today: str) -> str:
    uploader = _render_attachment_uploader(
        existing_count=0,
        label="添加附件（0/10）",
        collapsible=True,
    )
    return f"""<div class="followup-shell-layout">
        <div class="settlement-fields-row">
            <div class="followup-field">
                <span class="followup-field-label">结算日期</span>
                <input type="date" name="settlement_date" required value="{escape(today)}">
            </div>
            <div class="followup-field">
                <span class="followup-field-label">结算人</span>
                <input name="settled_by" required placeholder="结算人" autocomplete="name">
            </div>
            <div class="followup-field">
                <span class="followup-field-label">结算主体</span>
                <input name="payer" required placeholder="结算主体">
            </div>
            <div class="followup-field">
                <span class="followup-field-label">还款方</span>
                {_render_settlement_repayer_select()}
            </div>
            <div class="followup-field">
                <span class="followup-field-label">结算金额</span>
                <input name="amount" required inputmode="decimal" placeholder="0.00">
            </div>
        </div>
        <div class="followup-body-grid">
            <div class="followup-field followup-scroll-cell span-full">
                <span class="followup-field-label">结算说明</span>
                <textarea name="description" rows="2" class="followup-textarea-scroll"
                          placeholder="可选"></textarea>
            </div>
        </div>
        <div class="followup-attachment-zone span-full">
            <div class="followup-attachment-upload-slot">{uploader}</div>
        </div>
    </div>"""


def _render_settlement_entry_shell(
    settlement: dict,
    product_hidden: str,
    asset_hidden: str,
    bucket_hidden: str,
    workbench_qs,
) -> str:
    sid = int(settlement["id"])
    sd_input = escape(str(settlement.get("settlement_date") or "")[:10])
    settled_by = escape(str(settlement.get("settled_by") or ""))
    payer = escape(str(settlement.get("payer") or ""))
    amount_raw = settlement.get("amount")
    amount_val = f"{float(amount_raw):.2f}" if amount_raw is not None else ""
    desc = escape(str(settlement.get("description") or ""))
    repayer_select = _render_settlement_repayer_select(settlement.get("repayer"))

    shell_layout = f"""<div class="followup-shell-layout">
        <div class="settlement-fields-row">
            <div class="followup-field">
                <span class="followup-field-label">结算日期</span>
                <input type="date" name="settlement_date" required value="{sd_input}">
            </div>
            <div class="followup-field">
                <span class="followup-field-label">结算人</span>
                <input name="settled_by" required value="{settled_by}">
            </div>
            <div class="followup-field">
                <span class="followup-field-label">结算主体</span>
                <input name="payer" required value="{payer}">
            </div>
            <div class="followup-field">
                <span class="followup-field-label">还款方</span>
                {repayer_select}
            </div>
            <div class="followup-field">
                <span class="followup-field-label">结算金额</span>
                <input name="amount" required inputmode="decimal" value="{escape(amount_val)}">
            </div>
        </div>
        <div class="followup-body-grid">
            <div class="followup-field followup-scroll-cell span-full">
                <span class="followup-field-label">结算说明</span>
                <textarea name="description" rows="2" class="followup-textarea-scroll">{desc}</textarea>
            </div>
        </div>
        {_render_settlement_attachment_zone(settlement)}
    </div>"""

    delete_form = f"""
        <form class="entry-delete-form" method="post" enctype="multipart/form-data"
              action="/overdue/workbench/manual-settlements/{sid}/delete{workbench_qs()}">
            <input type="hidden" name="redirect_to_workbench" value="1">
            {product_hidden}
            {asset_hidden}
            {bucket_hidden}
        </form>"""

    return f"""<div class="followup-entry-shell settlement-shell" data-settlement-id="{sid}" data-editing="1">
        <form class="followup-form followup-entry-form settlement-form" method="post" enctype="multipart/form-data"
              action="/overdue/workbench/manual-settlements/{sid}{workbench_qs()}">
            <input type="hidden" name="redirect_to_workbench" value="1">
            {product_hidden}
            {asset_hidden}
            {bucket_hidden}
            {shell_layout}
            <div class="followup-actions-bar">
                <div class="followup-entry-edit-actions settlement-actions">
                    <button type="submit" class="btn primary btn-compact">保存修改</button>
                    <button type="button" class="btn btn-compact entry-delete-btn">删除</button>
                    <button type="button" class="btn btn-compact settlement-cancel-btn">取消</button>
                </div>
            </div>
        </form>
        {delete_form}
    </div>"""


def _render_manual_settlement_section(
    product_hidden: str,
    asset_hidden: str,
    bucket_hidden: str,
    workbench_qs,
    dto: dict,
) -> str:
    from app.timeutil import now_beijing

    asset = dto.get("asset") or {}
    settlements = list(asset.get("manual_settlements") or [])
    today = now_beijing().date().isoformat()

    list_rows = ""
    detail_panels = ""
    for s in settlements[:50]:
        sid = int(s["id"])
        att_n = len(s.get("attachments") or [])
        att_label = f"{att_n}" if att_n else "—"
        desc = escape(_truncate_summary(str(s.get("description") or ""), 28))
        list_rows += f"""<tr class="settlement-list-row" data-settlement-id="{sid}" tabindex="0" role="button">
            <td class="cell-text">{escape(_fmt_date_only(s.get("settlement_date")))}</td>
            <td class="cell-text">{escape(str(s.get("settled_by") or "—"))}</td>
            <td class="cell-text">{escape(str(s.get("payer") or "—"))}</td>
            <td class="cell-text">{escape(str(s.get("repayer") or "—"))}</td>
            <td class="num">{fmt_money(s.get("amount"))}</td>
            <td class="cell-text">{desc or "—"}</td>
            <td class="cell-text">{att_label}</td>
        </tr>"""
        detail_panels += (
            f'<div class="settlement-detail-panel" data-settlement-panel="{sid}" hidden>'
            f"{_render_settlement_entry_shell(s, product_hidden, asset_hidden, bucket_hidden, workbench_qs)}"
            f"</div>"
        )

    if not list_rows:
        list_body = (
            '<tr><td colspan="7" class="empty muted">暂无手工结算，点击下方「＋ 结算」新建</td></tr>'
        )
    else:
        list_body = list_rows

    create_panel = f"""
        <div class="settlement-detail-panel" data-settlement-panel="new" hidden>
            <form class="followup-form settlement-form settlement-create-form" method="post"
                  enctype="multipart/form-data"
                  action="/overdue/workbench/manual-settlements{workbench_qs()}">
                <input type="hidden" name="redirect_to_workbench" value="1">
                {product_hidden}
                {asset_hidden}
                {bucket_hidden}
                {_render_settlement_create_fields(today)}
                <div class="followup-actions-bar">
                    <div class="followup-create-actions settlement-actions">
                        <button type="submit" class="btn primary">保存手工结算</button>
                        <button type="button" class="btn settlement-cancel-btn">取消</button>
                    </div>
                </div>
            </form>
        </div>"""

    return f"""
    <section class="followup-case-section settlement-section" aria-label="手工结算录入"
             data-settlement-active="">
        <div class="followup-section-title">手工结算列表</div>
        <p class="muted tiny">写入独立结算账本，不改动还款明细与监控事实表；点选一行可修改或删除。</p>
        <div class="table-wrap settlement-list-wrap">
            <table class="settlement-list-table">
                <thead><tr>
                    <th>结算日</th><th>结算人</th><th>结算主体</th><th>还款方</th>
                    <th class="num">金额</th><th>说明</th><th>附件</th>
                </tr></thead>
                <tbody>{list_body}</tbody>
            </table>
        </div>
        <div class="settlement-new-strip">
            <button type="button" class="settlement-new-chip" id="settlement-new-btn">＋ 结算</button>
        </div>
        <div class="settlement-detail" id="settlement-detail">
            {create_panel}
            {detail_panels}
        </div>
    </section>
    """


def _panel_followup_write(
    product_hidden,
    asset_hidden,
    bucket_hidden,
    workbench_qs,
    dto,
    *,
    write_mode: str = "collapsed",
    initial_pane: str = "followup-pane-new",
    selected_case_id: int | None = None,
    force_new_case: bool = False,
) -> str:
    data_date = escape(str(dto.get("data_date") or ""))
    asset = dto.get("asset") or {}
    asset_code = escape(str(dto.get("asset_code") or asset.get("asset_code") or ""))
    mode = write_mode if write_mode in ("followup", "settlement") else "collapsed"
    if mode == "followup":
        title_prefix = "跟进事项"
        icon = "▼"
        aria_exp = "true"
    elif mode == "settlement":
        title_prefix = "手工结算"
        icon = "▼"
        aria_exp = "true"
    else:
        title_prefix = "资产管理"
        icon = "▶"
        aria_exp = "false"
    cases = list(asset.get("followup_cases") or [])
    followup_entries = asset.get("followup_entries") or []
    cases_by_id = {int(c["id"]): c for c in cases if c.get("id") is not None}

    # Resolve selected case from URL / entry / default
    resolved_case_id: int | None = None
    show_new_case = bool(force_new_case) or not cases
    if not show_new_case:
        if selected_case_id is not None and int(selected_case_id) in cases_by_id:
            resolved_case_id = int(selected_case_id)
        elif initial_pane.startswith("followup-pane-entry-"):
            try:
                eid = int(initial_pane.rsplit("-", 1)[-1])
            except ValueError:
                eid = None
            if eid is not None:
                for entry in followup_entries:
                    if int(entry["id"]) == eid and entry.get("case_id") is not None:
                        resolved_case_id = int(entry["case_id"])
                        break
        if resolved_case_id is None and cases:
            resolved_case_id = int(cases[0]["id"])

    case_chips = ""
    for case in cases:
        cid = int(case["id"])
        case_chips += _render_followup_case_chip(
            case, active=(not show_new_case and resolved_case_id == cid)
        )
    case_chips += (
        f'<button type="button" class="case-chip case-chip-new'
        f'{" active" if show_new_case else ""}" data-case-id="new">＋ 事项</button>'
    )

    case_panels = ""
    # New-case panel
    case_panels += (
        f'<div class="followup-case-panel{" active" if show_new_case else ""}" '
        f'data-case-panel="new">'
        f"{_render_followup_case_create_panel(product_hidden, asset_hidden, bucket_hidden, workbench_qs, data_date)}"
        f"</div>"
    )
    for case in cases:
        cid = int(case["id"])
        active = not show_new_case and resolved_case_id == cid
        case_panels += (
            f'<div class="followup-case-panel{" active" if active else ""}" '
            f'data-case-panel="{cid}">'
            f"{_render_followup_case_edit_panel(case, product_hidden, asset_hidden, bucket_hidden, workbench_qs, data_date)}"
            f"</div>"
        )

    # Entry blocks per case
    entries_blocks = ""
    for case in cases:
        cid = int(case["id"])
        case_entries = [e for e in followup_entries if int(e.get("case_id") or 0) == cid]
        active = not show_new_case and resolved_case_id == cid
        case_active = case.get("status") in ("open", "in_progress", "settled_week")

        last_reason = ""
        last_plan = ""
        owner_val = str(case.get("owner_name") or "")
        if case_entries:
            last_reason = case_entries[0].get("overdue_reason") or ""
            last_plan = case_entries[0].get("follow_up_plan") or ""
            if not owner_val:
                owner_val = str(case_entries[0].get("owner_name") or "")

        # Prefer initial pane if it belongs to this case; else new
        case_initial = f"followup-pane-new-{cid}"
        if initial_pane.startswith("followup-pane-entry-"):
            for entry in case_entries:
                if f"followup-pane-entry-{int(entry['id'])}" == initial_pane:
                    case_initial = initial_pane
                    break

        entry_tabs = (
            f'<button type="button" class="entry-tab'
            f'{" active" if case_initial == f"followup-pane-new-{cid}" else ""}" '
            f'data-pane="followup-pane-new-{cid}">＋ 新建跟进</button>'
        )
        entry_panes = ""
        for entry in case_entries:
            eid = int(entry["id"])
            pane_id = f"followup-pane-entry-{eid}"
            tab_active = " active" if case_initial == pane_id else ""
            entry_tabs += (
                f'<button type="button" class="entry-tab{tab_active}" data-pane="{pane_id}">'
                f"{escape(_followup_entry_tab_label(entry))}</button>"
            )
            pane_active = " active" if case_initial == pane_id else ""
            entry_panes += (
                f'<div class="followup-pane{pane_active}" id="{pane_id}">'
                f"{_render_followup_entry_panel(entry, product_hidden, asset_hidden, bucket_hidden, workbench_qs, data_date)}"
                f"</div>"
            )

        new_pane_active = " active" if case_initial == f"followup-pane-new-{cid}" else ""
        if case_active:
            create_html = _render_followup_create_pane(
                product_hidden,
                asset_hidden,
                bucket_hidden,
                workbench_qs,
                data_date,
                case_id=cid,
                owner_val=owner_val,
                last_reason=str(last_reason),
                last_plan=str(last_plan),
                form_id=f"followup-form-{cid}",
            )
            new_pane = (
                f'<div class="followup-pane{new_pane_active}" id="followup-pane-new-{cid}">'
                f"{create_html}</div>"
            )
        else:
            new_pane = (
                f'<div class="followup-pane{new_pane_active}" id="followup-pane-new-{cid}">'
                f'<p class="muted">事项已结案，不可再新增跟进记录。可先将事项状态改回「待跟进」「跟进中」或「本周结算」。</p>'
                f"</div>"
            )

        entries_blocks += f"""
        <div class="followup-entries-block{" active" if active else ""}" data-case-entries="{cid}">
            <div class="entry-tabs" role="tablist">{entry_tabs}</div>
            {new_pane}
            {entry_panes}
        </div>"""

    empty_entries_hint = ""
    if show_new_case:
        empty_entries_hint = (
            '<div class="followup-entries-block active" data-case-entries="new">'
            '<p class="muted">请先创建跟进事项，再录入跟进记录。</p>'
            "</div>"
        )

    settlement_section = _render_manual_settlement_section(
        product_hidden, asset_hidden, bucket_hidden, workbench_qs, dto
    )

    return f"""
    <div class="sticky-write-bar" id="followup-entry-form" data-mode="{mode}"
         data-active-case="{"new" if show_new_case else (resolved_case_id or "")}">
        <div class="sticky-write-collapsed">
            <button type="button" class="write-toggle" id="write-mode-toggle" aria-expanded="{aria_exp}">
                <span class="write-toggle-icon" aria-hidden="true">{icon}</span>
                <span class="sticky-write-title" data-asset-code="{asset_code}">
                    <span class="sticky-write-mode-label">{title_prefix}</span>
                    · {ASSET_CODE_LABEL} {asset_code}
                </span>
            </button>
            <span class="sticky-write-actions">
                <button type="button" class="btn primary btn-compact write-mode-btn" id="write-open-followup"
                        data-mode="followup">跟进事项</button>
                <button type="button" class="btn primary btn-compact write-mode-btn" id="write-open-settlement"
                        data-mode="settlement">手工结算</button>
                <button type="button" class="btn btn-compact write-collapse-btn" id="write-collapse">收起</button>
            </span>
        </div>
        <div class="sticky-write-panel" id="followup-write-panel">
            <div class="sticky-write-inner write-panel-followup" id="write-panel-followup">
                <section class="followup-case-section" aria-label="跟进事项">
                    <div class="followup-section-title">跟进事项</div>
                    <div class="followup-case-strip" role="tablist">{case_chips}</div>
                    {case_panels}
                </section>
                <section class="followup-entries-section" aria-label="跟进记录">
                    <div class="followup-section-title">跟进记录</div>
                    {entries_blocks}
                    {empty_entries_hint}
                </section>
            </div>
            <div class="sticky-write-inner write-panel-settlement" id="write-panel-settlement">
                {settlement_section}
            </div>
        </div>
    </div>
    """


_ATTACHMENT_LIGHTBOX_HTML = """
<div id="attachment-image-lightbox" class="attachment-image-lightbox" hidden aria-modal="true" role="dialog">
    <div class="attachment-image-lightbox-backdrop"></div>
    <div class="attachment-image-lightbox-panel">
        <button type="button" class="attachment-image-lightbox-close" aria-label="关闭">×</button>
        <img class="attachment-image-lightbox-img" alt="">
    </div>
</div>"""

_ATTACHMENT_OPEN_SCRIPT = """
var _attachmentLightboxInst = null;

function getAttachmentLightbox() {
    if (_attachmentLightboxInst) return _attachmentLightboxInst;
    var root = document.getElementById('attachment-image-lightbox');
    if (!root) return null;
    var img = root.querySelector('.attachment-image-lightbox-img');
    var backdrop = root.querySelector('.attachment-image-lightbox-backdrop');
    var closeBtn = root.querySelector('.attachment-image-lightbox-close');

    function close() {
        root.hidden = true;
        document.body.classList.remove('attachment-lightbox-open');
        if (img) img.removeAttribute('src');
    }

    if (backdrop) backdrop.addEventListener('click', close);
    if (closeBtn) closeBtn.addEventListener('click', close);
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && !root.hidden) close();
    });

    _attachmentLightboxInst = {
        open: function(src, title) {
            if (!img || !src) return;
            img.src = src;
            img.alt = title || '';
            root.hidden = false;
            document.body.classList.add('attachment-lightbox-open');
        },
        close: close
    };
    return _attachmentLightboxInst;
}

function openAttachmentImagePreview(src, title) {
    var lb = getAttachmentLightbox();
    if (lb) lb.open(src, title);
}

function classifyFileKind(file, getExt) {
    if (file.type && file.type.indexOf('image/') === 0) return 'image';
    var ext = getExt(file.name);
    if (ext === '.pdf' || file.type === 'application/pdf') return 'pdf';
    return 'file';
}

function bindPendingAttachmentOpen(el, file, blobUrl, getExt) {
    var kind = classifyFileKind(file, getExt);
    el.classList.add('attachment-chip-open-link');
    el.dataset.kind = kind;
    if (kind === 'image') {
        el.href = '#';
        el.title = '点击预览';
        el.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            openAttachmentImagePreview(blobUrl, file.name);
        });
    } else if (kind === 'pdf') {
        el.href = blobUrl;
        el.target = '_blank';
        el.rel = 'noopener';
        el.title = '在新标签页打开';
        el.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            window.open(blobUrl, '_blank', 'noopener');
        });
    } else {
        el.href = blobUrl;
        el.target = '_blank';
        el.rel = 'noopener';
        el.title = '打开或下载';
    }
}

document.addEventListener('click', function(e) {
    var link = e.target.closest('a.attachment-open-link');
    if (!link) return;
    var kind = link.dataset.kind;
    var href = link.getAttribute('href');
    if (!href) return;
    if (kind === 'image') {
        e.preventDefault();
        openAttachmentImagePreview(href, link.textContent.trim());
    } else if (kind === 'pdf') {
        e.preventDefault();
        window.open(href, '_blank', 'noopener');
    }
});
"""

_ATTACHMENT_UPLOADER_SCRIPT = """
function initAttachmentUploader(container) {
    if (!container || container.dataset.initialized === '1') return;
    container.dataset.initialized = '1';

    var dropzone = container.querySelector('.attachment-dropzone');
    var input = container.querySelector('.attachment-input');
    var preview = container.querySelector('.attachment-preview');
    var errorEl = container.querySelector('.attachment-error');
    var maxFiles = parseInt(container.dataset.maxFiles || '10', 10);
    var maxSize = parseInt(container.dataset.maxFileSize || '10485760', 10);
    var existingCount = parseInt(container.dataset.existingCount || '0', 10);
    var allowedExt = (container.dataset.allowedExtensions || '').split(',').map(function(s) {
        return s.trim().toLowerCase();
    }).filter(Boolean);

    container._attachmentPool = new DataTransfer();
    container._objectUrls = new Map();

    function revokeBlobUrl(key) {
        if (container._objectUrls.has(key)) {
            URL.revokeObjectURL(container._objectUrls.get(key));
            container._objectUrls.delete(key);
        }
    }

    function revokeAllBlobUrls() {
        container._objectUrls.forEach(function(url) {
            URL.revokeObjectURL(url);
        });
        container._objectUrls.clear();
    }

    function getBlobUrl(file) {
        var key = fileKey(file);
        if (container._objectUrls.has(key)) {
            return container._objectUrls.get(key);
        }
        var url = URL.createObjectURL(file);
        container._objectUrls.set(key, url);
        return url;
    }

    function showError(msg) {
        if (!errorEl) return;
        if (msg) {
            errorEl.textContent = msg;
            errorEl.hidden = false;
        } else {
            errorEl.textContent = '';
            errorEl.hidden = true;
        }
    }

    function fileKey(file) {
        return file.name + '|' + file.size + '|' + file.lastModified;
    }

    function pad2(n) { return n < 10 ? '0' + n : String(n); }

    function normalizeFile(file) {
        var name = file.name || '';
        if (!name || name === 'image.png') {
            var now = new Date();
            var ext = '.png';
            if (file.type === 'image/jpeg') ext = '.jpg';
            else if (file.type === 'image/webp') ext = '.webp';
            else if (file.type === 'image/gif') ext = '.gif';
            name = 'screenshot-' + now.getFullYear() + pad2(now.getMonth() + 1) + pad2(now.getDate())
                + '-' + pad2(now.getHours()) + pad2(now.getMinutes()) + pad2(now.getSeconds()) + ext;
            return new File([file], name, { type: file.type || 'image/png', lastModified: file.lastModified });
        }
        return file;
    }

    function getExt(name) {
        var i = name.lastIndexOf('.');
        return i >= 0 ? name.slice(i).toLowerCase() : '';
    }

    function validateFile(file) {
        if (file.size > maxSize) return '单文件不能超过 10MB';
        var ext = getExt(file.name);
        if (!ext || allowedExt.indexOf(ext) < 0) return '不支持该文件类型';
        return null;
    }

    function syncInput() {
        if (input) input.files = container._attachmentPool.files;
    }

    function removeAt(index) {
        var file = container._attachmentPool.files[index];
        if (file) revokeBlobUrl(fileKey(file));
        var next = new DataTransfer();
        Array.prototype.forEach.call(container._attachmentPool.files, function(f, i) {
            if (i !== index) next.items.add(f);
        });
        container._attachmentPool = next;
        syncInput();
        renderPreview();
        showError('');
    }

    function renderPreview() {
        if (!preview) return;
        preview.innerHTML = '';
        Array.prototype.forEach.call(container._attachmentPool.files, function(file, idx) {
            var chip = document.createElement('div');
            chip.className = 'attachment-chip';
            var blobUrl = getBlobUrl(file);
            var isImage = file.type && file.type.indexOf('image/') === 0;

            if (isImage) {
                var thumbLink = document.createElement('a');
                bindPendingAttachmentOpen(thumbLink, file, blobUrl, getExt);
                var img = document.createElement('img');
                img.className = 'attachment-thumb';
                img.alt = file.name;
                var reader = new FileReader();
                reader.onload = function(e) { img.src = e.target.result; };
                reader.readAsDataURL(file);
                thumbLink.appendChild(img);
                chip.appendChild(thumbLink);
            }

            if (!isImage) {
                var metaLink = document.createElement('a');
                bindPendingAttachmentOpen(metaLink, file, blobUrl, getExt);
                metaLink.classList.add('attachment-chip-meta-link');
                var stem = file.name || 'file';
                var ext = getExt(stem);
                var base = ext ? stem.slice(0, stem.length - ext.length) : stem;
                var shortName = base.length <= 5 ? stem : (base.slice(0, 5) + '***' + ext);
                metaLink.textContent = shortName;
                metaLink.title = file.name + ' · ' + Math.round(file.size / 1024) + ' KB';
                chip.appendChild(metaLink);
            }

            var removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'attachment-chip-remove';
            removeBtn.setAttribute('aria-label', '删除');
            removeBtn.textContent = '×';
            removeBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                removeAt(idx);
            });
            chip.appendChild(removeBtn);
            preview.appendChild(chip);
        });
    }

    function addFiles(fileList) {
        if (!fileList || !fileList.length) return;
        showError('');
        var seen = {};
        Array.prototype.forEach.call(container._attachmentPool.files, function(f) {
            seen[fileKey(f)] = true;
        });
        var firstError = '';

        function getEffectiveExistingCount() {
            var shell = container.closest('.followup-entry-shell');
            if (!shell) return existingCount;
            var removed = shell.querySelectorAll('.remove-attachment-input').length;
            return Math.max(0, existingCount - removed);
        }

        for (var i = 0; i < fileList.length; i++) {
            var file = normalizeFile(fileList[i]);
            var key = fileKey(file);
            if (seen[key]) continue;

            if (getEffectiveExistingCount() + container._attachmentPool.files.length + 1 > maxFiles) {
                firstError = '附件最多 10 个';
                break;
            }

            var err = validateFile(file);
            if (err) {
                if (!firstError) firstError = err;
                continue;
            }

            container._attachmentPool.items.add(file);
            seen[key] = true;
        }

        if (firstError) showError(firstError);
        syncInput();
        renderPreview();
    }

    container.clearAttachmentUploader = function() {
        revokeAllBlobUrls();
        container._attachmentPool = new DataTransfer();
        syncInput();
        renderPreview();
        showError('');
    };

    if (dropzone) {
        dropzone.addEventListener('click', function(e) {
            if (e.target.closest('.attachment-chip-remove')) return;
            if (e.target.closest('.attachment-chip-open-link')) return;
            if (input) input.click();
        });
        dropzone.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                if (input) input.click();
            }
        });
        dropzone.addEventListener('dragover', function(e) {
            e.preventDefault();
            dropzone.classList.add('drag-over');
        });
        dropzone.addEventListener('dragenter', function(e) {
            e.preventDefault();
            dropzone.classList.add('drag-over');
        });
        dropzone.addEventListener('dragleave', function(e) {
            e.preventDefault();
            dropzone.classList.remove('drag-over');
        });
        dropzone.addEventListener('drop', function(e) {
            e.preventDefault();
            dropzone.classList.remove('drag-over');
            addFiles(e.dataTransfer.files);
        });
    }

    if (input) {
        input.addEventListener('change', function() {
            addFiles(input.files);
        });
    }

    var form = container.closest('form');
    if (form) {
        form.addEventListener('paste', function(e) {
            var files = e.clipboardData && e.clipboardData.files;
            if (!files || !files.length) return;
            e.preventDefault();
            addFiles(files);
        });
    }
}
"""

_WORKBENCH_SCRIPTS = """
<script>
""" + _ATTACHMENT_OPEN_SCRIPT + _ATTACHMENT_UPLOADER_SCRIPT + """
document.addEventListener('DOMContentLoaded', function() {
    var detailLoadSeq = 0;
    var detailAbort = null;
    var detailInitAbort = null;
    var markerDocBound = false;

    function parseDetailMeta(root) {
        if (!root) return {};
        try {
            return JSON.parse(root.getAttribute('data-wb-meta') || '{}');
        } catch (e) {
            return {};
        }
    }

    function revokeAttachmentUrls(root) {
        if (!root) return;
        root.querySelectorAll('.attachment-uploader').forEach(function(el) {
            if (el._objectUrls) {
                el._objectUrls.forEach(function(url) { URL.revokeObjectURL(url); });
                el._objectUrls.clear();
            }
        });
    }

    function detailHasUnsavedEdit(root) {
        if (!root) return false;
        var shell = root.querySelector(
            '.followup-entry-shell:not(.followup-entry-shell--create):not(.settlement-shell)[data-editing="1"]'
        );
        return !!shell;
    }

    function confirmLeaveUnsaved(root) {
        if (!detailHasUnsavedEdit(root)) return true;
        return confirm('有未保存修改，是否放弃？');
    }

    function setActiveQueueItem(pid, assetCode) {
        var queue = document.getElementById('asset-queue');
        if (!queue) return null;
        var active = null;
        queue.querySelectorAll('.queue-item').forEach(function(item) {
            var id = item.id || '';
            var expect = 'asset-' + pid + '-' + assetCode;
            var isActive = id === expect;
            item.classList.toggle('active', isActive);
            if (isActive) active = item;
        });
        return active;
    }

    function applyQueuePatch(meta) {
        var patch = (meta && meta.queue_patch) || {};
        var pid = patch.trust_product_id;
        var ac = patch.asset_code;
        if (pid == null || !ac) return;
        var item = document.getElementById('asset-' + pid + '-' + ac);
        if (!item) return;
        if (patch.internal_status_html) {
            var cell = item.querySelector('.queue-status, .internal-status-cell');
            if (cell) {
                var wrap = document.createElement('div');
                wrap.innerHTML = patch.internal_status_html;
                var next = wrap.firstElementChild;
                if (next) cell.replaceWith(next);
            }
        }
    }

    function applyHeaderMeta(meta) {
        if (!meta) return;
        var links = document.querySelector('.header-tool-links');
        if (!links) return;
        var jsonLink = null;
        var awLink = null;
        links.querySelectorAll('a.header-tool-link').forEach(function(a) {
            var href = a.getAttribute('href') || '';
            if (href.indexOf('/overdue/workbench/detail') === 0) jsonLink = a;
            if (href.indexOf('/asset-workbench/') === 0) awLink = a;
        });
        if (jsonLink && meta.json_href) jsonLink.setAttribute('href', meta.json_href);
        if (meta.asset_workbench_href) {
            if (awLink) {
                awLink.setAttribute('href', meta.asset_workbench_href);
            } else {
                var a = document.createElement('a');
                a.className = 'header-tool-link';
                a.href = meta.asset_workbench_href;
                a.textContent = 'Asset Workbench';
                links.appendChild(a);
            }
        } else if (awLink) {
            awLink.remove();
        }
    }

    function syncHiddenFilters(meta) {
        var form = document.getElementById('sf-form');
        if (!form || !meta) return;
        var pidInput = form.querySelector('input[name="trust_product_id"]');
        var acInput = form.querySelector('input[name="asset_code"]');
        if (pidInput && meta.trust_product_id != null) {
            pidInput.value = String(meta.trust_product_id);
        }
        if (acInput && meta.asset_code) {
            acInput.value = String(meta.asset_code);
        }
    }

    function setDetailLoading(loading) {
        var root = document.getElementById('workbench-detail');
        if (!root) return;
        root.classList.toggle('is-loading', !!loading);
    }

    function pageUrlToFragmentUrl(pageUrl) {
        var url = new URL(pageUrl, window.location.origin);
        url.pathname = '/overdue/workbench/fragment';
        return url.toString();
    }

    function initWorkbenchDetail(root) {
        if (!root) return;
        if (detailInitAbort) detailInitAbort.abort();
        detailInitAbort = new AbortController();
        var signal = detailInitAbort.signal;
        var opts = { signal: signal };

        var writeBar = root.querySelector('#followup-entry-form') || document.getElementById('followup-entry-form');
        var openFollowupBtn = root.querySelector('#write-open-followup');
        var openSettlementBtn = root.querySelector('#write-open-settlement');
        var modeToggle = root.querySelector('#write-mode-toggle');
        var collapseBtn = root.querySelector('#write-collapse');

        function modeLabel(mode) {
            if (mode === 'followup') return '跟进事项';
            if (mode === 'settlement') return '手工结算';
            return '资产管理';
        }

        function setWriteMode(mode) {
            if (!writeBar) return;
            var next = (mode === 'followup' || mode === 'settlement') ? mode : 'collapsed';
            writeBar.dataset.mode = next;
            var expanded = next !== 'collapsed';
            [modeToggle, openFollowupBtn, openSettlementBtn, collapseBtn].forEach(function(el) {
                if (el) el.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            });
            var icon = writeBar.querySelector('.write-toggle-icon');
            if (icon) icon.textContent = expanded ? '▼' : '▶';
            var label = writeBar.querySelector('.sticky-write-mode-label');
            if (label) label.textContent = modeLabel(next);
        }

        function expandWriteMode(mode) {
            setWriteMode(mode);
            if (writeBar) writeBar.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

        if (openFollowupBtn) {
            openFollowupBtn.addEventListener('click', function() { expandWriteMode('followup'); }, opts);
        }
        if (openSettlementBtn) {
            openSettlementBtn.addEventListener('click', function() { expandWriteMode('settlement'); }, opts);
        }
        if (modeToggle) {
            modeToggle.addEventListener('click', function() {
                if (!writeBar) return;
                if (writeBar.dataset.mode && writeBar.dataset.mode !== 'collapsed') {
                    setWriteMode('collapsed');
                }
            }, opts);
        }
        if (collapseBtn) {
            collapseBtn.addEventListener('click', function() { setWriteMode('collapsed'); }, opts);
        }

        var scrollFollowup = root.getAttribute('data-scroll-followup') || document.body.dataset.scrollFollowup || '0';
        var scrollSettlement = root.getAttribute('data-scroll-settlement') || document.body.dataset.scrollSettlement || '0';
        if (scrollFollowup === '1') expandWriteMode('followup');
        else if (scrollSettlement === '1') expandWriteMode('settlement');

        function setSettlementActive(id) {
            var section = root.querySelector('.settlement-section');
            if (!section) return;
            var next = (id === 'new' || (id != null && String(id) !== '')) ? String(id) : '';
            section.dataset.settlementActive = next;
            section.querySelectorAll('.settlement-list-row').forEach(function(row) {
                row.classList.toggle('active', next !== '' && next !== 'new' && String(row.dataset.settlementId) === next);
            });
            section.querySelectorAll('.settlement-detail-panel').forEach(function(panel) {
                var match = next !== '' && String(panel.dataset.settlementPanel) === next;
                panel.hidden = !match;
                if (match) {
                    var shell = panel.querySelector('.settlement-shell, .settlement-create-form');
                    if (shell) {
                        initSavedAttachmentRemovers(shell.closest('.settlement-shell') || panel);
                        refreshAttachmentUploadLabel(panel);
                        panel.querySelectorAll('.attachment-uploader').forEach(initAttachmentUploader);
                    }
                }
            });
            var newBtn = section.querySelector('#settlement-new-btn');
            if (newBtn) newBtn.classList.toggle('active', next === 'new');
        }

        var settlementNewBtn = root.querySelector('#settlement-new-btn');
        if (settlementNewBtn) {
            settlementNewBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                setSettlementActive('new');
                var panel = root.querySelector('.settlement-detail-panel[data-settlement-panel="new"]');
                if (panel) panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }, opts);
        }

        function refreshAttachmentUploadLabel(shell) {
            if (!shell) return;
            var uploader = shell.querySelector('.attachment-uploader');
            var toggle = shell.querySelector('.attachment-upload-toggle');
            if (!uploader || !toggle) return;
            var maxFiles = parseInt(uploader.dataset.maxFiles || '10', 10);
            var base = parseInt(uploader.dataset.existingCount || '0', 10);
            var removed = shell.querySelectorAll('.remove-attachment-input').length;
            var pending = uploader._attachmentPool ? uploader._attachmentPool.files.length : 0;
            var current = Math.max(0, base - removed) + pending;
            toggle.textContent = (toggle.textContent.indexOf('添加') >= 0 ? '添加附件' : '追加附件')
                + '（' + current + '/' + maxFiles + '）';
        }

        function restoreRemovedAttachments(shell) {
            if (!shell) return;
            shell.querySelectorAll('.attachment-chip-saved.marked-removed').forEach(function(chip) {
                chip.classList.remove('marked-removed');
                chip.hidden = false;
            });
            shell.querySelectorAll('.remove-attachment-input').forEach(function(el) { el.remove(); });
            shell.querySelectorAll('.followup-saved-attachments-empty').forEach(function(el) { el.remove(); });
            refreshAttachmentUploadLabel(shell);
        }

        function initSavedAttachmentRemovers(shell) {
            if (!shell) return;
            shell.querySelectorAll('.attachment-saved-remove').forEach(function(btn) {
                if (btn.dataset.bound === '1') return;
                btn.dataset.bound = '1';
                btn.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    var chip = btn.closest('.attachment-chip-saved');
                    if (!chip || chip.classList.contains('marked-removed')) return;
                    var aid = chip.dataset.attachmentId;
                    var form = shell.querySelector('.followup-entry-form');
                    if (!form || !aid) return;
                    chip.classList.add('marked-removed');
                    chip.hidden = true;
                    var input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = 'remove_attachment_ids';
                    input.value = aid;
                    input.className = 'remove-attachment-input';
                    form.appendChild(input);
                    refreshAttachmentUploadLabel(shell);
                    var list = shell.querySelector('.followup-saved-attachments');
                    if (list && !list.querySelector('.attachment-chip-saved:not(.marked-removed)')) {
                        if (!list.querySelector('.followup-saved-attachments-empty')) {
                            var span = document.createElement('span');
                            span.className = 'muted followup-saved-attachments-empty';
                            span.textContent = '—';
                            list.appendChild(span);
                        }
                    }
                }, opts);
            });
        }

        function cancelEntryEdit(shell) {
            if (!shell) return;
            var form = shell.querySelector('.followup-entry-form');
            if (form) form.reset();
            restoreRemovedAttachments(shell);
            shell.dataset.editing = '0';
            shell.querySelectorAll('.attachment-upload-panel').forEach(function(panel) { panel.hidden = true; });
            shell.querySelectorAll('.attachment-upload-toggle').forEach(function(btn) {
                btn.setAttribute('aria-expanded', 'false');
            });
        }

        function startEntryEdit(shell) {
            if (!shell) return;
            shell.dataset.editing = '1';
            initSavedAttachmentRemovers(shell);
            refreshAttachmentUploadLabel(shell);
        }

        function paneHasUnsavedEdit(pane) {
            var shell = pane && pane.querySelector('.followup-entry-shell:not(.followup-entry-shell--create)');
            return shell && shell.dataset.editing === '1';
        }

        function switchFollowupCase(caseId) {
            if (!caseId && caseId !== 0) return;
            var id = String(caseId);
            if (writeBar) writeBar.dataset.activeCase = id;
            root.querySelectorAll('.case-chip').forEach(function(chip) {
                chip.classList.toggle('active', String(chip.dataset.caseId) === id);
            });
            root.querySelectorAll('.followup-case-panel').forEach(function(panel) {
                panel.classList.toggle('active', String(panel.dataset.casePanel) === id);
            });
            root.querySelectorAll('.followup-entries-block').forEach(function(block) {
                block.classList.toggle('active', String(block.dataset.caseEntries) === id);
            });
        }

        function switchFollowupPane(paneId) {
            if (!paneId) return;
            var targetPane = document.getElementById(paneId);
            if (!targetPane) return;
            var block = targetPane.closest('.followup-entries-block');
            if (block && block.dataset.caseEntries) {
                switchFollowupCase(block.dataset.caseEntries);
            }
            var scope = block || root;
            var activePane = scope.querySelector('.followup-pane.active');
            if (activePane && activePane.id !== paneId && paneHasUnsavedEdit(activePane)) {
                if (!confirm('有未保存修改，是否放弃？')) return;
                cancelEntryEdit(activePane.querySelector('.followup-entry-shell'));
            }
            scope.querySelectorAll('.followup-pane').forEach(function(pane) {
                pane.classList.toggle('active', pane.id === paneId);
            });
            scope.querySelectorAll('.entry-tab').forEach(function(tab) {
                tab.classList.toggle('active', tab.dataset.pane === paneId);
            });
        }

        function followupApiError(data) {
            if (!data) return '操作失败';
            if (typeof data.detail === 'string') return data.detail;
            if (Array.isArray(data.detail)) {
                return data.detail.map(function(d) {
                    return d.msg || JSON.stringify(d);
                }).join('; ') || '操作失败';
            }
            return data.message || '操作失败';
        }

        function reloadWorkbenchAfterFollowup(data) {
            var url = new URL(window.location.href);
            url.searchParams.set('followup_expanded', '1');
            url.searchParams.delete('settlement_expanded');
            url.searchParams.delete('new_followup');
            url.searchParams.delete('new_followup_case');
            var caseId = data && data.case_id != null ? data.case_id : null;
            var entryId = data && data.entry_id != null ? data.entry_id : null;
            if (data && data.deleted) entryId = null;
            if (caseId != null) url.searchParams.set('followup_case_id', String(caseId));
            else url.searchParams.delete('followup_case_id');
            if (entryId != null) url.searchParams.set('followup_entry_id', String(entryId));
            else url.searchParams.delete('followup_entry_id');
            loadWorkbenchDetail(url.toString(), { history: 'replace', skipUnsavedCheck: true });
        }

        function reloadWorkbenchAfterSettlement() {
            var url = new URL(window.location.href);
            url.searchParams.set('settlement_expanded', '1');
            url.searchParams.delete('followup_expanded');
            url.searchParams.delete('new_followup');
            url.searchParams.delete('new_followup_case');
            url.searchParams.delete('followup_case_id');
            url.searchParams.delete('followup_entry_id');
            loadWorkbenchDetail(url.toString(), { history: 'replace', skipUnsavedCheck: true });
        }

        function submitFollowupForm(form, extraDisableEls) {
            if (!form || form.dataset.submitting === '1') return;
            form.dataset.submitting = '1';
            var isSettlement = form.classList.contains('settlement-form')
                || String(form.getAttribute('action') || form.action || '').indexOf('manual-settlements') >= 0;
            var fd = new FormData(form);
            fd.delete('redirect_to_workbench');
            var btns = Array.prototype.slice.call(form.querySelectorAll('button[type="submit"]'));
            if (extraDisableEls && extraDisableEls.length) {
                extraDisableEls.forEach(function(el) {
                    if (el && btns.indexOf(el) < 0) btns.push(el);
                });
            }
            btns.forEach(function(b) { b.disabled = true; });
            fetch(form.getAttribute('action') || form.action, {
                method: 'POST',
                body: fd,
                credentials: 'same-origin',
                headers: { 'Accept': 'application/json' }
            }).then(function(res) {
                return res.text().then(function(text) {
                    var data = {};
                    if (text) {
                        try { data = JSON.parse(text); }
                        catch (e) { data = { detail: text }; }
                    }
                    if (!res.ok) throw new Error(followupApiError(data));
                    if (isSettlement) reloadWorkbenchAfterSettlement();
                    else reloadWorkbenchAfterFollowup(data || {});
                });
            }).catch(function(err) {
                form.dataset.submitting = '0';
                btns.forEach(function(b) { b.disabled = false; });
                alert(err.message || '操作失败');
            });
        }

        if (writeBar) {
            writeBar.addEventListener('submit', function(e) {
                var form = e.target;
                if (!form || form.tagName !== 'FORM') return;
                if (!form.querySelector('[name="redirect_to_workbench"]')) return;
                e.preventDefault();
                submitFollowupForm(form);
            }, opts);
        }

        root.addEventListener('click', function(e) {
            var settlementNew = e.target.closest('#settlement-new-btn, .settlement-new-chip');
            if (settlementNew && root.contains(settlementNew)) {
                e.preventDefault();
                setSettlementActive('new');
                var newPanel = root.querySelector('.settlement-detail-panel[data-settlement-panel="new"]');
                if (newPanel) newPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                return;
            }
            var settlementRow = e.target.closest('.settlement-list-row');
            if (settlementRow && root.contains(settlementRow)) {
                setSettlementActive(settlementRow.dataset.settlementId);
                var panel = root.querySelector(
                    '.settlement-detail-panel[data-settlement-panel="' + settlementRow.dataset.settlementId + '"]'
                );
                if (panel) panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                return;
            }
            var settlementCancel = e.target.closest('.settlement-cancel-btn');
            if (settlementCancel && root.contains(settlementCancel)) {
                setSettlementActive('');
                return;
            }
            var chip = e.target.closest('.case-chip');
            if (chip && root.contains(chip)) {
                switchFollowupCase(chip.dataset.caseId);
                if (chip.dataset.caseId !== 'new') {
                    var newPane = document.getElementById('followup-pane-new-' + chip.dataset.caseId);
                    if (newPane) switchFollowupPane(newPane.id);
                }
                expandWriteMode('followup');
                return;
            }
            var tab = e.target.closest('.entry-tab');
            if (tab && root.contains(tab)) {
                switchFollowupPane(tab.dataset.pane);
                return;
            }
            var editBtn = e.target.closest('.entry-edit-btn');
            if (editBtn && root.contains(editBtn)) {
                if (editBtn.disabled) return;
                startEntryEdit(editBtn.closest('.followup-entry-shell'));
                return;
            }
            var cancelBtn = e.target.closest('.entry-cancel-btn');
            if (cancelBtn && root.contains(cancelBtn)) {
                cancelEntryEdit(cancelBtn.closest('.followup-entry-shell'));
                return;
            }
            var delBtn = e.target.closest('.entry-delete-btn');
            if (delBtn && root.contains(delBtn)) {
                if (delBtn.disabled) return;
                var shell = delBtn.closest('.followup-entry-shell');
                var isSettlement = !!(shell && shell.classList.contains('settlement-shell'));
                var msg = isSettlement
                    ? '确定删除该条手工结算？删除后不再叠加到已还/剩余与核对。'
                    : '确定删除该条跟进记录？此操作不可恢复。';
                if (!confirm(msg)) return;
                var form = shell && shell.querySelector('.entry-delete-form');
                if (form) submitFollowupForm(form, [delBtn]);
                return;
            }
            var uploadToggle = e.target.closest('.attachment-upload-toggle');
            if (uploadToggle && root.contains(uploadToggle)) {
                var wrap = uploadToggle.closest('.followup-attachment-upload');
                var panel = wrap && wrap.querySelector('.attachment-upload-panel');
                if (!panel) return;
                var open = panel.hidden;
                panel.hidden = !open;
                uploadToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
                return;
            }
            var citeBtn = e.target.closest('.entry-cite-btn');
            if (citeBtn && root.contains(citeBtn)) {
                var block = citeBtn.closest('.followup-entries-block');
                var caseId = block && block.dataset.caseEntries;
                var form = caseId
                    ? document.getElementById('followup-form-' + caseId)
                    : root.querySelector('.followup-entries-block.active .followup-entry-shell--create form');
                if (!form) return;
                var owner = form.querySelector('[name="owner_name"]');
                var reason = form.querySelector('[name="overdue_reason"]');
                var plan = form.querySelector('[name="follow_up_plan"]');
                if (owner) owner.value = citeBtn.dataset.owner || '';
                if (reason) reason.value = citeBtn.dataset.reason || '';
                if (plan) plan.value = citeBtn.dataset.plan || '';
                if (caseId) switchFollowupPane('followup-pane-new-' + caseId);
                if (writeBar) writeBar.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                return;
            }
            var tlToggle = e.target.closest('.tl-case-toggle');
            if (tlToggle && root.contains(tlToggle)) {
                var tlBlock = tlToggle.closest('.tl-case-block');
                if (!tlBlock) return;
                var tlOpen = !tlBlock.classList.contains('is-open');
                tlBlock.classList.toggle('is-open', tlOpen);
                tlToggle.setAttribute('aria-expanded', tlOpen ? 'true' : 'false');
                var detail = tlBlock.querySelector('.tl-case-detail');
                if (detail) detail.hidden = !tlOpen;
                return;
            }
            var gotoEntry = e.target.closest('.timeline-goto-entry');
            if (gotoEntry && root.contains(gotoEntry)) {
                if (gotoEntry.dataset.caseId) switchFollowupCase(gotoEntry.dataset.caseId);
                if (gotoEntry.dataset.entryPane) switchFollowupPane(gotoEntry.dataset.entryPane);
                expandWriteMode('followup');
                if (writeBar) writeBar.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                return;
            }
            var statusOpen = e.target.closest('.summary-status-open');
            if (statusOpen && root.contains(statusOpen)) {
                expandWriteMode('followup');
                if (writeBar && writeBar.dataset.activeCase && writeBar.dataset.activeCase !== 'new') {
                    switchFollowupCase(writeBar.dataset.activeCase);
                }
                if (writeBar) writeBar.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                return;
            }
            var newCaseBtn = e.target.closest('.summary-new-case-btn');
            if (newCaseBtn && root.contains(newCaseBtn)) {
                switchFollowupCase('new');
                expandWriteMode('followup');
                if (writeBar) writeBar.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                return;
            }
            var clearBtn = e.target.closest('.followup-clear-btn');
            if (clearBtn && root.contains(clearBtn)) {
                var clearForm = clearBtn.closest('form');
                if (!clearForm) return;
                clearForm.reset();
                var uploader = clearForm.querySelector('.attachment-uploader');
                if (uploader && uploader.clearAttachmentUploader) uploader.clearAttachmentUploader();
                clearForm.querySelectorAll('.attachment-upload-panel').forEach(function(panel) { panel.hidden = true; });
                clearForm.querySelectorAll('.attachment-upload-toggle').forEach(function(btn) {
                    btn.setAttribute('aria-expanded', 'false');
                });
                return;
            }
            var markerBadge = e.target.closest('.trust-marker-badge');
            if (markerBadge && root.contains(markerBadge)) {
                e.stopPropagation();
                var cell = markerBadge.closest('.trust-marker-cell');
                var menu = cell && cell.querySelector('.trust-marker-menu');
                if (!cell || !menu) return;
                var open = !cell.classList.contains('is-open');
                root.querySelectorAll('.trust-marker-cell.is-open').forEach(function(c) {
                    if (c !== cell) {
                        c.classList.remove('is-open');
                        var m = c.querySelector('.trust-marker-menu');
                        var b = c.querySelector('.trust-marker-badge');
                        if (m) m.hidden = true;
                        if (b) b.setAttribute('aria-expanded', 'false');
                    }
                });
                cell.classList.toggle('is-open', open);
                menu.hidden = !open;
                markerBadge.setAttribute('aria-expanded', open ? 'true' : 'false');
                return;
            }
            var markerOpt = e.target.closest('.trust-marker-option');
            if (markerOpt && root.contains(markerOpt)) {
                e.stopPropagation();
                var mCell = markerOpt.closest('.trust-marker-cell');
                if (!mCell) return;
                root.querySelectorAll('.trust-marker-cell.is-open').forEach(function(c) {
                    c.classList.remove('is-open');
                    var m = c.querySelector('.trust-marker-menu');
                    var b = c.querySelector('.trust-marker-badge');
                    if (m) m.hidden = true;
                    if (b) b.setAttribute('aria-expanded', 'false');
                });
                var value = markerOpt.dataset.value;
                if (!value || value === mCell.dataset.value) return;
                saveMarker(mCell, value);
                return;
            }
        }, opts);

        function saveMarker(cell, value) {
            var MARKER_VISUAL = {
                '无标记': { tone: 'none', short: '无' },
                '已关注': { tone: 'watch', short: '已关注' },
                '重点关注': { tone: 'focus', short: '重点关注' }
            };
            var field = cell.dataset.field || 'trust_marker';
            var payload = {
                trust_product_id: parseInt(cell.dataset.trustProductId, 10),
                asset_code: cell.dataset.assetCode,
                data_date: cell.dataset.dataDate
            };
            payload[field] = value;
            cell.classList.remove('saved', 'error');
            cell.classList.add('saving');
            fetch('/overdue/custody-marks', {
                method: 'PATCH',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(function(res) {
                return res.json().then(function(data) {
                    cell.classList.remove('saving');
                    if (!res.ok) {
                        cell.classList.add('error');
                        throw new Error(data.detail || '保存失败');
                    }
                    var vis = MARKER_VISUAL[value] || { tone: 'none', short: value };
                    cell.dataset.value = value;
                    var badge = cell.querySelector('.trust-marker-badge');
                    var label = cell.querySelector('.trust-marker-label');
                    var dot = badge && badge.querySelector('.trust-marker-dot');
                    if (badge) {
                        badge.className = 'trust-marker-badge tone-' + vis.tone;
                        badge.title = '信托标记：' + value;
                        badge.setAttribute('aria-label', '信托标记：' + value + '，点击修改');
                    }
                    if (dot) dot.className = 'trust-marker-dot tone-' + vis.tone;
                    if (label) label.textContent = vis.short;
                    cell.querySelectorAll('.trust-marker-option').forEach(function(opt) {
                        var active = opt.dataset.value === value;
                        opt.classList.toggle('is-active', active);
                        opt.setAttribute('aria-selected', active ? 'true' : 'false');
                    });
                    cell.classList.add('saved');
                    setTimeout(function() { cell.classList.remove('saved'); }, 1200);
                });
            }).catch(function() {
                cell.classList.remove('saving');
                cell.classList.add('error');
            });
        }

        root.querySelectorAll('.mark-select').forEach(function(sel) {
            sel.addEventListener('change', function() {
                var payload = {
                    trust_product_id: parseInt(this.dataset.product, 10),
                    asset_code: this.dataset.assetCode,
                    data_date: this.dataset.date
                };
                payload[this.dataset.field] = this.value;
                fetch('/overdue/custody-marks', {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                }).catch(function() { alert('标注保存失败'); });
            }, opts);
        });

        root.querySelectorAll('.mark-inline-group').forEach(function(group) {
            var display = group.querySelector('.mark-display');
            var sel = group.querySelector('.mark-select');
            if (!display || !sel) return;
            display.addEventListener('dblclick', function() {
                display.classList.add('mark-edit-hidden');
                sel.classList.remove('mark-edit-hidden');
                sel.focus();
            }, opts);
            sel.addEventListener('change', function() {
                display.textContent = this.options[this.selectedIndex].text;
                sel.classList.add('mark-edit-hidden');
                display.classList.remove('mark-edit-hidden');
            }, opts);
            sel.addEventListener('blur', function() {
                sel.classList.add('mark-edit-hidden');
                display.classList.remove('mark-edit-hidden');
            }, opts);
        });

        if (!markerDocBound) {
            markerDocBound = true;
            document.addEventListener('click', function() {
                document.querySelectorAll('.trust-marker-cell.is-open').forEach(function(cell) {
                    cell.classList.remove('is-open');
                    var menu = cell.querySelector('.trust-marker-menu');
                    var badge = cell.querySelector('.trust-marker-badge');
                    if (menu) menu.hidden = true;
                    if (badge) badge.setAttribute('aria-expanded', 'false');
                });
            });
            document.addEventListener('keydown', function(e) {
                if (e.key !== 'Escape') return;
                document.querySelectorAll('.trust-marker-cell.is-open').forEach(function(cell) {
                    cell.classList.remove('is-open');
                    var menu = cell.querySelector('.trust-marker-menu');
                    var badge = cell.querySelector('.trust-marker-badge');
                    if (menu) menu.hidden = true;
                    if (badge) badge.setAttribute('aria-expanded', 'false');
                });
            });
        }

        var initialFollowupPane = root.getAttribute('data-followup-pane')
            || document.body.dataset.followupPane || '';
        if (initialFollowupPane && document.getElementById(initialFollowupPane)) {
            switchFollowupPane(initialFollowupPane);
        } else if (writeBar && writeBar.dataset.activeCase) {
            switchFollowupCase(writeBar.dataset.activeCase);
        }

        root.querySelectorAll('.attachment-uploader').forEach(initAttachmentUploader);
        root.querySelectorAll('.followup-entry-shell:not(.followup-entry-shell--create)').forEach(initSavedAttachmentRemovers);

        // expose for leave-check from navigation
        root._wbConfirmLeave = function() { return confirmLeaveUnsaved(root); };
        root._wbExpandWriteBar = function() { expandWriteMode('followup'); };
        root._wbExpandSettlement = function() { expandWriteMode('settlement'); };
    }

    function replaceDetailMain(html, meta) {
        var current = document.getElementById('workbench-detail');
        if (!current) return null;
        revokeAttachmentUrls(current);
        if (detailInitAbort) detailInitAbort.abort();
        var wrap = document.createElement('div');
        wrap.innerHTML = html;
        var next = wrap.firstElementChild;
        if (!next) return null;
        current.replaceWith(next);
        var resolvedMeta = meta || parseDetailMeta(next);
        document.body.dataset.scrollFollowup = next.getAttribute('data-scroll-followup') || '0';
        document.body.dataset.scrollSettlement = next.getAttribute('data-scroll-settlement') || '0';
        document.body.dataset.followupPane = next.getAttribute('data-followup-pane') || '';
        applyHeaderMeta(resolvedMeta);
        syncHiddenFilters(resolvedMeta);
        applyQueuePatch(resolvedMeta);
        if (resolvedMeta.trust_product_id != null && resolvedMeta.asset_code) {
            setActiveQueueItem(resolvedMeta.trust_product_id, resolvedMeta.asset_code);
        }
        initWorkbenchDetail(next);
        return next;
    }

    function loadWorkbenchDetail(pageUrl, options) {
        options = options || {};
        var current = document.getElementById('workbench-detail');
        if (!options.skipUnsavedCheck && current && current._wbConfirmLeave) {
            if (!current._wbConfirmLeave()) return Promise.resolve(false);
        }
        var seq = ++detailLoadSeq;
        if (detailAbort) detailAbort.abort();
        detailAbort = new AbortController();
        setDetailLoading(true);
        var fragmentUrl = pageUrlToFragmentUrl(pageUrl);
        return fetch(fragmentUrl, {
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' },
            signal: detailAbort.signal
        }).then(function(res) {
            if (res.redirected && res.url && res.url.indexOf('/login') >= 0) {
                window.location.href = pageUrl;
                return null;
            }
            if (res.status === 401 || res.status === 403) {
                window.location.href = pageUrl;
                return null;
            }
            return res.text().then(function(text) {
                if (seq !== detailLoadSeq) return null;
                var data = null;
                try { data = JSON.parse(text); }
                catch (e) {
                    // login HTML or unexpected payload
                    window.location.href = pageUrl;
                    return null;
                }
                if (!res.ok) throw new Error((data && data.detail) || '加载失败');
                if (!data || !data.html) throw new Error('加载失败');
                replaceDetailMain(data.html, data.meta || {});
                if (options.history === 'push') {
                    history.pushState({ workbenchPartial: true }, '', pageUrl);
                } else if (options.history === 'replace') {
                    history.replaceState({ workbenchPartial: true }, '', pageUrl);
                }
                return true;
            });
        }).catch(function(err) {
            if (err && err.name === 'AbortError') return false;
            if (seq !== detailLoadSeq) return false;
            console.error(err);
            alert((err && err.message) || '加载资产详情失败，请重试');
            return false;
        }).finally(function() {
            if (seq === detailLoadSeq) setDetailLoading(false);
        });
    }

    // initial detail bind
    initWorkbenchDetail(document.getElementById('workbench-detail'));
    history.replaceState({ workbenchPartial: true }, '', window.location.href);

    var assetQueue = document.getElementById('asset-queue');
    if (assetQueue) {
        assetQueue.addEventListener('click', function(e) {
            var item = e.target.closest('.queue-item');
            if (!item || !assetQueue.contains(item)) return;
            if (e.defaultPrevented) return;
            if (e.button !== 0) return;
            if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
            var href = item.getAttribute('href');
            if (!href) return;
            e.preventDefault();
            loadWorkbenchDetail(href, { history: 'push' });
        });
    }

    window.addEventListener('popstate', function() {
        loadWorkbenchDetail(window.location.href, { history: 'none', skipUnsavedCheck: true });
    });

    var SIDEBAR_ALL_LABELS = {
        'trust-product': '全部产品',
        'delinquency-bucket': '全部等级',
        'trust-marker': '全部标记',
        'internal-status': '全部状态',
        'city': '全部城市'
    };
    var SIDEBAR_COUNT_UNITS = {
        'trust-product': '产品',
        'delinquency-bucket': '等级',
        'trust-marker': '标记',
        'internal-status': '状态',
        'city': '城市'
    };

    function bindSidebarMultiselects(form) {
        if (!form) return;
        var dirty = false;
        form.querySelectorAll('[data-multiselect]').forEach(function(root) {
            var panel = root.querySelector('.sf-multiselect-panel, .multiselect-panel');
            var trigger = root.querySelector('.sf-multiselect-trigger, .multiselect-trigger, .sf-display');
            var allBox = root.querySelector('.ms-all');
            var key = root.getAttribute('data-multiselect') || '';
            var allLabel = SIDEBAR_ALL_LABELS[key] || '全部';
            var unit = SIDEBAR_COUNT_UNITS[key] || '项';
            function updateTrigger() {
                if (!trigger) return;
                if (allBox && allBox.checked) {
                    trigger.textContent = allLabel;
                    return;
                }
                var names = [];
                root.querySelectorAll('.ms-option').forEach(function(box) {
                    if (box.checked) names.push(box.parentElement.textContent.trim());
                });
                if (!names.length) trigger.textContent = allLabel;
                else if (names.length === 1) trigger.textContent = names[0];
                else trigger.textContent = '已选' + names.length + unit;
            }
            function closePanelAndApply() {
                if (!panel || panel.hidden) return;
                panel.hidden = true;
                if (dirty && form.id === 'sf-form') {
                    dirty = false;
                    submitSidebarFilter(form);
                }
            }
            if (trigger && panel) {
                trigger.addEventListener('click', function(ev) {
                    ev.preventDefault();
                    ev.stopPropagation();
                    form.querySelectorAll('.sf-multiselect-panel, .multiselect-panel').forEach(function(p) {
                        if (p !== panel) p.hidden = true;
                    });
                    panel.hidden = !panel.hidden;
                });
            }
            document.addEventListener('click', function(ev) {
                if (!root.contains(ev.target)) closePanelAndApply();
            });
            if (allBox) {
                allBox.addEventListener('change', function() {
                    root.querySelectorAll('.ms-option').forEach(function(box) {
                        if (allBox.checked) { box.checked = false; box.disabled = true; }
                        else { box.disabled = false; }
                    });
                    dirty = true;
                    updateTrigger();
                });
                if (allBox.checked) {
                    root.querySelectorAll('.ms-option').forEach(function(box) {
                        box.disabled = true;
                    });
                }
            }
            root.querySelectorAll('.ms-option').forEach(function(box) {
                box.addEventListener('change', function() {
                    if (box.checked && allBox) {
                        allBox.checked = false;
                        root.querySelectorAll('.ms-option').forEach(function(other) {
                            other.disabled = false;
                        });
                    }
                    dirty = true;
                    updateTrigger();
                });
            });
            updateTrigger();
        });
    }

    function submitSidebarFilter(form) {
        var params = new URLSearchParams();
        var productRoot = form.querySelector('[data-multiselect="trust-product"]');
        var productAll = productRoot ? productRoot.querySelector('.ms-all') : null;
        var useAllProducts = !productRoot || (productAll && productAll.checked);
        var anyProduct = false;
        var bucketRoot = form.querySelector('[data-multiselect="delinquency-bucket"]');
        var bucketAll = bucketRoot ? bucketRoot.querySelector('.ms-all') : null;
        var useAllBuckets = bucketRoot && bucketAll && bucketAll.checked;
        form.querySelectorAll('input, select').forEach(function(el) {
            if (!el.name || el.disabled) return;
            if (el.classList.contains('ms-all')) return;
            if (el.classList.contains('ms-option')) {
                if (!el.checked) return;
                if (el.classList.contains('tp-product')) {
                    if (!useAllProducts) {
                        params.append('list_product_ids', el.value);
                        anyProduct = true;
                    }
                    return;
                }
                params.append(el.name, el.value);
                return;
            }
            var val = (el.value || '').trim();
            if (val) params.set(el.name, val);
        });
        if (useAllProducts || !anyProduct) params.set('list_product_id', '');
        if (useAllBuckets) params.set('delinquency_bucket', '');
        window.location = form.getAttribute('action') + '?' + params.toString();
    }

    bindSidebarMultiselects(document.getElementById('sf-form'));
    bindSidebarMultiselects(document.querySelector('.workbench-filter'));

    window.addEventListener('beforeunload', function() {
        document.querySelectorAll('.attachment-uploader').forEach(function(el) {
            if (el._objectUrls) {
                el._objectUrls.forEach(function(url) { URL.revokeObjectURL(url); });
                el._objectUrls.clear();
            }
        });
    });
});
</script>
"""

_WORKBENCH_SPECIFIC_CSS = """
    .page-wrap { padding: 0; }
    .container { padding-bottom: 1.5rem; }
    .page-header { margin-bottom: 0.25rem; }
    .detail-main.is-loading {
        opacity: 0.55;
        pointer-events: none;
        transition: opacity 0.12s ease;
    }
    .header-row { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; }
    .header-actions {
        display: flex; flex-direction: column; align-items: flex-end;
        gap: 0.35rem; flex-shrink: 0;
    }
    .header-tool-links {
        display: flex; gap: 0.65rem; font-size: 0.8rem;
    }
    .header-tool-link { color: #38bdf8; }
    .header-action-btns { display: flex; gap: 0.5rem; }
    .header-sub { color: #94a3b8; margin-top: 0.35rem; font-size: 0.9rem; }
    .header-data-date { font-size: 12px; color: #475569; font-weight: 400; white-space: nowrap; }
    /* Sidebar compact inline-edit filter row */
    .sidebar-filter {
        display: flex; flex-wrap: wrap; gap: 3px 4px; align-items: center;
        padding: 6px 0.85rem 8px; border-bottom: 1px solid rgba(255,255,255,0.06);
    }
    .sf-item { display: inline-flex; align-items: center; position: relative; }
    .sf-display {
        font-size: 12px; line-height: 1.35; color: #e2e8f0; cursor: default; user-select: none;
        border-bottom: 1px dashed rgba(255,255,255,0.18); padding: 1px 0;
        background: none; border-top: none; border-left: none; border-right: none;
        font-family: inherit; font-weight: inherit; text-align: left;
    }
    .sf-display:hover { border-bottom-color: rgba(99,179,237,0.55); color: #93c5fd; }
    .sf-multiselect-trigger { cursor: pointer; max-width: 11rem; overflow: hidden;
        text-overflow: ellipsis; white-space: nowrap; }
    .sf-multiselect-panel {
        position: absolute; top: calc(100% + 4px); left: 0; z-index: 300;
        min-width: 11rem; max-height: 14rem; overflow-y: auto;
        padding: 0.35rem 0; border-radius: 8px;
        background: rgba(15,23,42,0.98);
        border: 1px solid rgba(148,163,184,0.25);
        box-shadow: 0 8px 24px rgba(0,0,0,0.35);
    }
    .sf-multiselect-panel .multiselect-option {
        display: flex; align-items: center; gap: 0.4rem;
        padding: 0.28rem 0.65rem; font-size: 12px; color: #cbd5e1; cursor: pointer;
    }
    .sf-multiselect-panel .multiselect-option:hover { background: rgba(56,189,248,0.1); color: #f8fafc; }
    .sf-multiselect-panel .multiselect-all {
        border-bottom: 1px solid rgba(255,255,255,0.08); margin-bottom: 0.15rem;
        padding-bottom: 0.4rem;
    }
    .sf-select {
        display: none;
        position: absolute; top: -2px; left: -4px; z-index: 200;
        font-size: 12px; color: #e2e8f0; height: 26px;
        min-width: 80px; max-width: 140px;
        background: rgba(15,23,42,0.97);
        border: 1px solid rgba(99,179,237,0.4); border-radius: 5px;
        padding: 0 4px; cursor: pointer; outline: none; box-sizing: border-box;
    }
    .sf-sep { color: #475569; padding: 0 2px; font-size: 11px; line-height: 1; }
    .ok-text { color: #4ade80; }
    .warn-text { color: #f87171; }
    .workbench {
        display: grid; grid-template-columns: 300px 1fr; gap: 1rem;
        margin-top: 1rem; align-items: start;
    }
    @media (max-width: 960px) { .workbench { grid-template-columns: 1fr; } }
    .panel {
        background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
        border-radius: 12px; overflow: hidden;
    }
    .panel-hd {
        padding: 0.65rem 0.85rem; border-bottom: 1px solid rgba(255,255,255,0.08);
        font-weight: 600; font-size: 0.85rem;
    }
    .detail-main {
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 1rem;
    }
    /* ── Detail Grid: summary | issuance, repay | timeline, ops ─ */
    .detail-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        grid-template-areas:
            "summary   summary   issuance  issuance"
            "repay     repay     timeline  timeline"
            "ops       ops       ops       ops";
        gap: 16px;
        align-items: stretch;
    }
    .grid-summary  { grid-area: summary; }
    .grid-issuance { grid-area: issuance; }
    .grid-repay    { grid-area: repay; }
    .grid-timeline { grid-area: timeline; }
    .grid-ops      { grid-area: ops; }
    @media (max-width: 960px) {
        .detail-grid {
            grid-template-columns: 1fr;
            grid-template-areas:
                "summary" "issuance"
                "repay" "timeline"
                "ops";
        }
    }
    .panel-dual { height: 100%; display: flex; flex-direction: column; }
    .panel-dual .info-card-body { flex: 1; display: flex; flex-direction: column; min-height: 0; }
    .panel-summary-line {
        margin: 0 0 0.65rem; font-size: 0.875rem; line-height: 1.45;
        min-height: 2.5rem;
    }
    .panel-fixed-rows {
        width: 100%; table-layout: fixed; border-collapse: collapse;
    }
    .panel-fixed-rows th,
    .panel-fixed-rows td {
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .panel-fixed-rows tbody tr { height: 2rem; }
    .panel-fixed-rows tbody tr.row-pad td {
        color: transparent; border-color: rgba(255,255,255,0.04);
    }
    .tl-history-table tbody.tl-case-block tr.tl-case-detail { height: auto; }
    .panel-fixed-rows th.cell-text,
    .panel-fixed-rows td.cell-text { text-align: left; }
    .panel-fixed-rows th.num,
    .panel-fixed-rows td.num { text-align: right; }
    .col-repay-custody { width: 34%; }
    .col-repay-date { width: 22%; }
    .col-repay-source { width: 18%; }
    .col-repay-amt { width: 26%; }
    .grid-repay .table-wrap { overflow-x: hidden; }
    .grid-repay .panel-fixed-rows {
        table-layout: fixed; width: 100%;
    }
    .grid-repay .panel-fixed-rows th,
    .grid-repay .panel-fixed-rows td {
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .grid-repay td.repay-source { color: #94a3b8; font-size: 0.78rem; }
    .col-tl-time { width: 24%; }
    .col-tl-cat { width: 18%; }
    .col-tl-status { width: 16%; }
    .col-tl-desc { width: 42%; }
    .tl-case-toggle {
        display: inline-flex; align-items: center; gap: 0.35rem;
        background: none; border: none; color: #e2e8f0; cursor: pointer;
        padding: 0; font: inherit; font-size: inherit;
    }
    .tl-case-toggle:hover { color: #7dd3fc; }
    .tl-case-caret {
        display: inline-block; width: 0.7rem; font-size: 0.65rem; color: #94a3b8;
        transition: transform 0.12s ease;
    }
    .tl-case-block.is-open .tl-case-caret { transform: rotate(90deg); }
    .tl-case-block.is-open .tl-case-row td { color: #f8fafc; }
    .tl-case-detail td {
        padding: 0.35rem 0.4rem 0.55rem !important;
        white-space: normal; overflow: visible;
        background: rgba(15,23,42,0.35);
    }
    .tl-entry-wrap {
        border: 1px solid rgba(148,163,184,0.18); border-radius: 6px;
        padding: 0.35rem 0.45rem; background: rgba(0,0,0,0.18);
    }
    .tl-entry-table {
        width: 100%; border-collapse: collapse; table-layout: fixed;
        font-size: 0.78rem;
    }
    .tl-entry-table th,
    .tl-entry-table td {
        text-align: left; padding: 0.2rem 0.3rem;
        border-bottom: 1px solid rgba(255,255,255,0.06);
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .tl-entry-table th { color: #94a3b8; font-weight: 500; }
    .tl-entry-table tr:last-child td { border-bottom: none; }
    .timeline-goto-entry, .timeline-detail-link {
        background: none; border: none; color: #38bdf8; cursor: pointer;
        padding: 0; font: inherit; font-size: inherit;
        max-width: 100%; overflow: hidden; text-overflow: ellipsis;
    }
    .timeline-goto-entry:hover, .timeline-detail-link:hover { text-decoration: underline; }
    .panel-expand { margin-top: 0.5rem; }
    .panel-expand-summary { cursor: pointer; color: #38bdf8; font-size: 0.85rem; }
    .panel-expand-table { margin-top: 0; }
    .panel-expand-table table { border-top: none; }
    /* ── Summary Card (4-line scan + hover tips) ─────────────── */
    .card-summary {
        background: rgba(255,255,255,0.06); border: 1px solid rgba(56,189,248,0.2);
        border-radius: 12px; padding: 12px 14px;
    }
    .card-summary-anomaly { border-left: 3px solid #f87171; }
    .card-summary-v2 .summary-line {
        display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px;
        font-size: 13px; color: #cbd5e1; line-height: 1.5;
    }
    .card-summary-v2 .summary-line + .summary-line {
        margin-top: 8px; padding-top: 8px;
        border-top: 1px solid rgba(255,255,255,0.06);
    }
    .summary-line-money { font-variant-numeric: tabular-nums; }
    .summary-em { font-weight: 700; color: #f8fafc; font-size: 15px; }
    .summary-sep { color: #64748b; user-select: none; padding: 0 1px; }
    .summary-warn { color: #f87171; font-weight: 600; }
    .summary-chip { position: relative; display: inline-flex; align-items: center; max-width: 100%; }
    .summary-chip.has-tip { cursor: help; border-bottom: 1px dotted rgba(148,163,184,0.35); }
    .summary-chip.has-tip:hover { border-bottom-color: rgba(56,189,248,0.55); color: #e2e8f0; }
    .summary-chip .tip-panel {
        display: none; position: absolute; left: 0; top: calc(100% + 6px); z-index: 60;
        min-width: 210px; max-width: 340px; padding: 8px 10px;
        background: #1e293b; border: 1px solid rgba(56,189,248,0.25); border-radius: 8px;
        font-size: 12px; line-height: 1.45; color: #e2e8f0; font-weight: 400;
        box-shadow: 0 8px 24px rgba(0,0,0,0.35); white-space: normal;
    }
    .summary-chip.has-tip:hover .tip-panel,
    .summary-chip.has-tip:focus-within .tip-panel { display: block; }
    .summary-chip-editable .mark-display { font-size: 13px; }
    .summary-chip-mark, .summary-chip-status { align-items: center; }
    .summary-chip-mark .tip-panel,
    .summary-chip-status .tip-panel { min-width: 9rem; }
    .internal-status-cell {
        display: inline-flex; align-items: center; gap: 0.3rem; min-height: 1.35rem;
    }
    .internal-status-link {
        display: inline-flex; align-items: center; justify-content: center;
        text-decoration: none; line-height: 1; background: none; border: none;
        padding: 0; cursor: pointer; font: inherit; color: inherit;
    }
    .status-dot, .status-count {
        display: inline-flex; align-items: center; justify-content: center;
        width: 1.35rem; height: 1.35rem; min-width: 1.35rem;
        border-radius: 50%; box-sizing: border-box;
    }
    .status-dot {
        background: #22c55e;
        box-shadow: 0 0 0 2px rgba(34,197,94,0.22);
    }
    .status-count {
        padding: 0; font-size: 0.72rem; font-weight: 700; line-height: 1;
        color: #0f172a; background: #f59e0b;
        box-shadow: 0 0 0 1px rgba(245,158,11,0.35);
    }
    .status-count--settled {
        border-radius: 999px;
        background: linear-gradient(135deg, #fbbf24, #34d399);
        box-shadow: 0 0 0 1px rgba(52,211,153,0.35);
    }
    .internal-status-add {
        display: inline-flex; align-items: center; justify-content: center;
        width: 1.2rem; height: 1.2rem; border-radius: 4px;
        font-size: 0.95rem; font-weight: 700; line-height: 1;
        color: #64748b; text-decoration: none; background: none;
        opacity: 0.28; border: 1px solid transparent; cursor: pointer;
        transition: opacity 0.15s ease, color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
    }
    .summary-line:hover .internal-status-add,
    .internal-status-cell:focus-within .internal-status-add,
    .internal-status-add:focus-visible {
        opacity: 1; color: #e2e8f0;
        border-color: rgba(56,189,248,0.45);
        background: rgba(56,189,248,0.12);
    }
    .trust-marker-cell { position: relative; display: inline-flex; align-items: center; }
    .trust-marker-badge {
        display: inline-flex; align-items: center; gap: 0.35rem;
        padding: 0.12rem 0.4rem; border-radius: 999px;
        border: 1px solid rgba(255,255,255,0.12);
        background: rgba(255,255,255,0.04); color: #cbd5e1;
        font-size: 0.78rem; cursor: pointer; line-height: 1.2;
    }
    .trust-marker-badge:hover,
    .trust-marker-cell.is-open .trust-marker-badge {
        border-color: rgba(56,189,248,0.4);
        background: rgba(56,189,248,0.08);
    }
    .trust-marker-dot {
        width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
        background: #64748b;
    }
    .trust-marker-dot.tone-none {
        background: transparent; border: 1.5px solid #64748b;
    }
    .trust-marker-dot.tone-watch { background: #f59e0b; }
    .trust-marker-dot.tone-focus { background: #f87171; }
    .trust-marker-badge.tone-none { color: #94a3b8; }
    .trust-marker-badge.tone-watch { color: #fbbf24; }
    .trust-marker-badge.tone-focus { color: #fecaca; }
    .trust-marker-menu {
        position: absolute; top: calc(100% + 0.25rem); left: 0; z-index: 50;
        min-width: 8.5rem; padding: 0.25rem;
        border-radius: 8px; border: 1px solid rgba(148,163,184,0.25);
        background: #0f172a; box-shadow: 0 8px 24px rgba(0,0,0,0.45);
        display: flex; flex-direction: column; gap: 0.1rem;
    }
    .trust-marker-menu[hidden] { display: none !important; }
    .trust-marker-option {
        display: flex; align-items: center; gap: 0.4rem;
        width: 100%; padding: 0.35rem 0.45rem; border: none; border-radius: 6px;
        background: transparent; color: #e2e8f0; font-size: 0.78rem;
        cursor: pointer; text-align: left;
    }
    .trust-marker-option:hover { background: rgba(56,189,248,0.12); }
    .trust-marker-option.is-active { background: rgba(56,189,248,0.18); }
    .trust-marker-cell.saving { opacity: 0.6; }
    .trust-marker-cell.saved .trust-marker-badge { border-color: #34d399; }
    .trust-marker-cell.error .trust-marker-badge { border-color: #f87171; }
    .summary-chip-line { max-width: 100%; }
    .check-ok { color: #34d399; font-weight: 600; }
    .check-bad { color: #f87171; font-weight: 600; }
    .tiny-badge { font-size: 10px; padding: 1px 6px; margin-left: 4px; vertical-align: middle; }
    /* legacy summary tiers (hero wrapper) */
    .info-group { display: flex; flex-direction: column; gap: 2px; }
    .info-label { font-size: 12px; color: #94a3b8; line-height: 1.2; }
    .detail-primary {
        display: flex; flex-wrap: wrap; gap: 8px 24px;
        padding-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.08);
        margin-bottom: 12px;
    }
    .info-value-xl {
        font-size: 22px; font-weight: 700; color: #f8fafc;
        font-variant-numeric: tabular-nums; line-height: 1.2;
    }
    .info-value-sm { font-size: 13px; color: #94a3b8; line-height: 1.3; }
    .check-icon-pass { color: #34d399; font-weight: 600; }
    .check-icon-fail { color: #f87171; font-weight: 600; }
    .info-warn { color: #f87171; }
    .summary-select {
        font-size: 12px; color: #e2e8f0; background: rgba(255,255,255,0.07);
        border: 1px solid rgba(255,255,255,0.12); border-radius: 5px;
        padding: 2px 6px; cursor: pointer; outline: none; max-width: 120px;
    }
    .summary-select:focus { border-color: rgba(99,179,237,0.5); }
    .summary-custody-note { font-size: 11px; color: #475569; width: 100%; margin-top: 2px; }
    .mark-edit-hidden { display: none; }
    .mark-display {
        font-size: 12px; color: #e2e8f0; cursor: default;
        border-bottom: 1px dashed rgba(255,255,255,0.18);
        padding: 1px 0; user-select: none;
    }
    .mark-display:hover { border-bottom-color: rgba(99,179,237,0.55); color: #93c5fd; }
    /* kept for sidebar asset-info card */
    .hero-lbl { display: block; font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.25rem; }
    .sidebar-section + .sidebar-section { border-top: 1px solid rgba(255,255,255,0.08); }
    .sidebar-asset-info { padding-bottom: 0.5rem; }
    .compact-queue { max-height: 72vh; overflow-y: auto; }
    .queue-line3 { font-size: 0.68rem; margin-top: 0.15rem; }
    .selection-notice {
        margin-top: 0.5rem; padding: 0.45rem 0.75rem;
        background: rgba(56,189,248,0.08); border: 1px solid rgba(56,189,248,0.2);
        border-radius: 8px; color: #bae6fd;
    }
    .asset-card {
        padding: 0.75rem; margin: 0.5rem 0.75rem;
        background: rgba(56,189,248,0.06); border: 1px solid rgba(56,189,248,0.15);
        border-radius: 10px; font-size: 0.85rem;
    }
    .asset-card p { margin-bottom: 0.35rem; }
    .asset-card-followup { margin-top: 0.4rem; }
    .split-list { max-height: 200px; overflow-y: auto; }
    .queue-item {
        display: block; padding: 0.55rem 0.75rem;
        border-bottom: 1px solid rgba(255,255,255,0.06);
        color: inherit; text-decoration: none;
    }
    .queue-item:hover { background: rgba(56,189,248,0.08); }
    .queue-item.active {
        background: rgba(56,189,248,0.16);
        box-shadow: inset 3px 0 0 #38bdf8;
    }
    .queue-line1 {
        font-size: 0.82rem; font-weight: 500; line-height: 1.3; word-break: break-all;
        display: flex; justify-content: space-between; align-items: flex-start; gap: 0.35rem;
    }
    .queue-line2 {
        font-size: 0.72rem; color: #94a3b8; margin-top: 0.2rem;
        display: flex; flex-wrap: wrap; gap: 0.35rem 0.5rem; align-items: center;
    }
    .queue-bucket-days {
        display: inline-flex; align-items: center; gap: 0.3rem; white-space: nowrap;
    }
    .queue-bucket-days .badge { font-size: 0.68rem; padding: 0.05rem 0.3rem; }
    .queue-status { flex-shrink: 0; }
    .queue-status .status-dot, .queue-status .status-count {
        width: 1.15rem; height: 1.15rem; min-width: 1.15rem; font-size: 0.68rem;
    }
    .custody-card {
        padding: 0.75rem; margin: 0.5rem 0.75rem;
        background: rgba(56,189,248,0.06); border: 1px solid rgba(56,189,248,0.15);
        border-radius: 10px; min-height: 72px;
    }
    .custody-card-multi { margin-bottom: 0; border-radius: 10px 10px 0 0; }
    .custody-card-code { font-size: 0.95rem; font-weight: 600; word-break: break-all; }
    .custody-card-meta {
        font-size: 0.75rem; color: #94a3b8; margin-top: 0.35rem;
        display: flex; flex-wrap: wrap; gap: 0.25rem 0.5rem; align-items: center;
    }
    .custody-card-followup { margin-top: 0.4rem; }
    .info-card {
        background: rgba(0,0,0,0.18); border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px; padding: 1rem 1.1rem; height: 100%;
    }
    .info-card-primary { border-color: rgba(56,189,248,0.25); background: rgba(56,189,248,0.05); }
    .info-card-alert { border-color: rgba(239,68,68,0.3); }
    .info-card-title { font-size: 0.95rem; margin-bottom: 0.65rem; color: #f1f5f9; font-weight: 600; }
    details.info-card { padding: 0; height: auto; }
    details.info-card > summary.info-card-title {
        padding: 1rem 1.1rem; margin: 0; cursor: pointer; list-style: none;
    }
    details.info-card > summary.info-card-title::-webkit-details-marker { display: none; }
    details.info-card > summary.info-card-title::before { content: "▶ "; font-size: 0.7rem; color: #94a3b8; }
    details.info-card[open] > summary.info-card-title::before { content: "▼ "; }
    details.info-card .info-card-body { padding: 0 1.1rem 1rem; }
    .ops-panel { background: rgba(251,191,36,0.06); border-color: rgba(251,191,36,0.15); }
    .ops-panel-alert { border-color: rgba(239,68,68,0.35); box-shadow: inset 3px 0 0 #f87171; }
    .ops-list { margin: 0.35rem 0 0 1.1rem; font-size: 0.85rem; }
    .mark-readonly { margin-bottom: 0.65rem; padding-bottom: 0.65rem; border-bottom: 1px solid rgba(255,255,255,0.06); font-size: 0.85rem; }
    .mark-edit { margin-bottom: 0.35rem; }
    .sub-card { background: rgba(0,0,0,0.15); padding: 0.65rem; border-radius: 8px; margin-bottom: 0.5rem; }
    .sub-hd { font-weight: 600; margin-bottom: 0.35rem; }
    /* Issuance panel */
    .issuance-group { margin-bottom: 10px; }
    .issuance-group-hd {
        font-size: 12px; font-weight: 600; color: #64748b;
        text-transform: uppercase; letter-spacing: 0.05em;
        cursor: pointer; padding: 4px 0; margin-bottom: 6px;
        list-style: none;
    }
    .issuance-group-hd::-webkit-details-marker { display: none; }
    .issuance-group > summary.issuance-group-hd::before { content: "▶ "; font-size: 10px; }
    details.issuance-group[open] > summary.issuance-group-hd::before { content: "▼ "; }
    .issuance-custody { color: #94a3b8; font-variant-numeric: tabular-nums; }
    .issuance-record {
        background: rgba(0,0,0,0.15); border-radius: 8px;
        padding: 8px 12px; margin-bottom: 6px;
    }
    .issuance-issue-date { font-size: 13px; font-weight: 700; color: #e2e8f0; margin-bottom: 4px; }
    .issuance-line { font-size: 12px; color: #94a3b8; line-height: 1.7; word-break: break-all; }
    .monitor-summary { margin-bottom: 0.5rem; }
    .muted { color: #94a3b8; }
    .tiny { font-size: 0.75rem; }
    .lbl { color: #94a3b8; font-size: 0.8rem; margin-right: 0.35rem; }
    .empty { color: #64748b; padding: 0.5rem 0; }
    .badge { display: inline-block; padding: 0.15rem 0.45rem; border-radius: 4px; font-size: 0.75rem; border: 1px solid rgba(255,255,255,0.15); }
    .ok-badge { background: rgba(34,197,94,0.15); color: #4ade80; }
    .fail-badge { background: rgba(239,68,68,0.15); color: #f87171; }
    table { font-size: 0.8rem; }
    th, td { padding: 0.4rem 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.06); text-align: left; vertical-align: middle; }
    th { color: #94a3b8; font-weight: 500; }
    .num { text-align: right; font-variant-numeric: tabular-nums; }
    .sticky-write-bar {
        position: sticky; bottom: 0; z-index: 30;
        width: 100%;
        background: rgba(15,23,42,0.96); border: 1px solid rgba(56,189,248,0.25);
        border-radius: 12px;
        backdrop-filter: blur(8px); margin-top: auto;
        box-shadow: 0 -4px 24px rgba(0,0,0,0.35);
        overflow: hidden;
    }
    .sticky-write-collapsed {
        display: flex; align-items: center; justify-content: space-between; gap: 0.65rem;
        padding: 0.55rem 0.85rem;
    }
    .sticky-write-actions { display: flex; align-items: center; gap: 0.5rem; flex-shrink: 0; }
    .write-toggle {
        display: inline-flex; align-items: center; gap: 0.35rem;
        background: none; border: none; color: #f8fafc; cursor: pointer;
        font-size: 0.95rem; font-weight: 600; padding: 0;
        min-width: 0; flex: 1 1 auto;
    }
    .write-toggle-icon { font-size: 0.65rem; color: #94a3b8; }
    .sticky-write-bar[data-mode="collapsed"] .sticky-write-panel { display: none; }
    .sticky-write-bar[data-mode="collapsed"] .write-collapse-btn { display: none; }
    .sticky-write-bar[data-mode="followup"] .write-mode-btn,
    .sticky-write-bar[data-mode="settlement"] .write-mode-btn { display: none; }
    .sticky-write-bar[data-mode="followup"] #write-panel-settlement { display: none; }
    .sticky-write-bar[data-mode="settlement"] #write-panel-followup { display: none; }
    .sticky-write-panel { border-top: 1px solid rgba(255,255,255,0.06); }
    .sticky-write-inner {
        padding: 0.65rem 0.85rem 0.75rem;
        overflow: visible;
    }
    .sticky-write-title { font-size: 0.95rem; color: #f8fafc; }
    .settlement-section { margin-top: 0; padding-top: 0; border-top: none; }
    .settlement-new-strip {
        display: flex; flex-wrap: wrap; gap: 0.3rem;
        margin: 0.35rem 0 0.45rem;
    }
    .settlement-list-wrap { margin: 0.35rem 0 0.15rem; max-height: 11rem; overflow: auto; }
    .settlement-list-table { width: 100%; }
    .settlement-list-row { cursor: pointer; }
    .settlement-list-row:hover td { background: rgba(56,189,248,0.08); }
    .settlement-list-row.active td { background: rgba(56,189,248,0.16); }
    .settlement-detail { margin-top: 0.35rem; }
    .settlement-detail-panel {
        border: 1px solid rgba(255,255,255,0.08); border-radius: 8px;
        padding: 0.45rem 0.55rem 0.25rem;
        background: rgba(15,23,42,0.35);
    }
    .settlement-shell { border: none; padding: 0; }
    /* 与「＋ 事项」同款虚线透明，但不用 case-chip，避免误开跟进界面 */
    .settlement-new-chip {
        flex-shrink: 0;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.35rem;
        padding: 0.22rem 0.55rem;
        border-radius: 6px;
        border: 1px dashed rgba(148, 163, 184, 0.55);
        background: transparent;
        color: #94a3b8;
        font-size: 0.78rem;
        font-weight: 600;
        cursor: pointer;
        max-width: none;
    }
    .settlement-new-chip:hover {
        border-color: rgba(56, 189, 248, 0.65);
        color: #e0f2fe;
        background: rgba(56, 189, 248, 0.08);
    }
    .settlement-new-chip.active {
        border-color: rgba(56, 189, 248, 0.75);
        color: #e0f2fe;
        background: rgba(56, 189, 248, 0.12);
    }
    .followup-section-title {
        font-size: 0.72rem; font-weight: 600; letter-spacing: 0.02em;
        color: #94a3b8; margin: 0 0 0.25rem;
    }
    .followup-case-section {
        border-left: 3px solid rgba(56,189,248,0.55);
        background: rgba(56,189,248,0.06);
        border-radius: 8px;
        padding: 0.35rem 0.55rem 0.4rem;
        margin-bottom: 0.45rem;
    }
    .followup-entries-section {
        border-top: 1px solid rgba(255,255,255,0.1);
        padding-top: 0.45rem;
        margin-top: 0.1rem;
    }
    .followup-case-strip {
        display: flex; flex-wrap: nowrap; gap: 0.3rem;
        overflow-x: auto; margin: 0 0 0.3rem; padding-bottom: 0;
    }
    .case-chip {
        flex-shrink: 0; display: flex; flex-direction: row; align-items: center; gap: 0.35rem;
        padding: 0.22rem 0.55rem; border-radius: 6px;
        border: 1px solid rgba(255,255,255,0.15); background: rgba(15,23,42,0.45);
        color: #94a3b8; cursor: pointer; text-align: left; max-width: 18rem;
    }
    .case-chip.active {
        background: rgba(56,189,248,0.22); border-color: rgba(56,189,248,0.5); color: #e2e8f0;
    }
    .case-chip-new { border-style: dashed; }
    .case-chip-main { font-size: 0.78rem; font-weight: 600; color: inherit; white-space: nowrap; }
    .case-chip-sub {
        font-size: 0.7rem; color: #64748b; white-space: nowrap;
        overflow: hidden; text-overflow: ellipsis; max-width: 8rem;
    }
    .case-chip.active .case-chip-sub { color: #94a3b8; }
    .followup-case-panel { display: none; margin-bottom: 0; }
    .followup-case-panel.active { display: block; }
    .followup-case-edit-grid {
        display: grid;
        grid-template-columns: 8.5rem 7.5rem minmax(10rem, 16rem);
        gap: 0.25rem 0.5rem; align-items: end;
    }
    .followup-case-edit-grid .followup-case-desc {
        grid-column: 3; grid-row: 1;
        max-width: 16rem;
    }
    .followup-case-edit-grid .followup-field:nth-child(4) {
        grid-column: 1; grid-row: 2;
    }
    .followup-case-edit-grid .followup-case-actions {
        grid-column: 2 / span 2; grid-row: 2;
        display: flex; align-items: end; padding-bottom: 0.05rem;
    }
    .followup-case-edit-grid select,
    .followup-case-edit-grid .followup-case-desc-input,
    .followup-case-edit-grid .field-display--meta {
        width: 100%; margin-top: 0; padding: 0.28rem 0.4rem; border-radius: 6px;
        border: 1px solid rgba(255,255,255,0.15); background: rgba(0,0,0,0.25);
        color: #e2e8f0; box-sizing: border-box; font-size: 0.8rem;
        height: 1.7rem; min-height: 1.7rem; max-height: 1.7rem;
    }
    .followup-case-edit-grid .field-display--meta {
        display: flex; align-items: center;
    }
    .followup-case-edit-grid .followup-case-desc-input {
        max-width: 16rem;
    }
    .followup-case-edit-grid .followup-field-label {
        margin-bottom: 0.1rem; font-size: 0.72rem;
    }
    @media (max-width: 720px) {
        .followup-case-edit-grid {
            grid-template-columns: 1fr 1fr;
        }
        .followup-case-edit-grid .followup-case-desc {
            grid-column: 1 / -1; grid-row: auto; max-width: 16rem;
        }
        .followup-case-edit-grid .followup-field:nth-child(4) {
            grid-column: 1; grid-row: auto;
        }
        .followup-case-edit-grid .followup-case-actions {
            grid-column: 2; grid-row: auto;
        }
    }
    .followup-entries-block { display: none; }
    .followup-entries-block.active { display: block; }
    .entry-tabs {
        display: flex; flex-wrap: nowrap; gap: 0.35rem;
        overflow-x: auto; margin: 0.35rem 0 0.45rem;
        padding-bottom: 0.1rem;
    }
    .entry-tab {
        flex-shrink: 0; padding: 0.35rem 0.7rem; border-radius: 999px;
        border: 1px solid rgba(255,255,255,0.15); background: rgba(255,255,255,0.04);
        color: #94a3b8; cursor: pointer; font-size: 0.8rem; white-space: nowrap;
    }
    .entry-tab.active {
        background: rgba(56,189,248,0.2); border-color: rgba(56,189,248,0.45); color: #e2e8f0;
    }
    .followup-pane { display: none; }
    .followup-pane.active { display: block; }
    .followup-entry-shell {
        min-height: 0;
    }
    .followup-shell-layout {
        display: flex; flex-direction: column; gap: 0.45rem;
    }
    .followup-shell-layout .span-full { width: 100%; }
    .followup-entry-shell[data-editing="0"] .followup-edit-only { display: none !important; }
    .followup-entry-shell[data-editing="1"] .followup-view-only { display: none !important; }
    .followup-entry-shell--create .followup-view-only { display: none !important; }
    .followup-entry-shell--create .followup-edit-only { display: block; }
    .followup-entry-shell--create .followup-entry-view-actions,
    .followup-entry-shell--create .followup-entry-edit-actions { display: none !important; }
    .followup-entry-shell:not(.followup-entry-shell--create) .followup-create-actions {
        display: none !important;
    }
    .followup-entry-shell.settlement-shell .settlement-actions,
    .followup-entry-shell.settlement-shell .followup-entry-edit-actions {
        display: flex !important; gap: 0.45rem; align-items: center;
    }
    .followup-entry-shell:not(.followup-entry-shell--create)[data-editing="0"] .followup-entry-edit-actions {
        display: none !important;
    }
    .followup-entry-shell:not(.followup-entry-shell--create)[data-editing="0"] .followup-entry-view-actions {
        display: flex; gap: 0.45rem; align-items: center;
    }
    .followup-entry-shell:not(.followup-entry-shell--create)[data-editing="1"] .followup-entry-view-actions {
        display: none !important;
    }
    .followup-entry-shell:not(.followup-entry-shell--create)[data-editing="1"] .followup-entry-edit-actions {
        display: flex; gap: 0.45rem; align-items: center;
    }
    .followup-create-actions {
        display: flex; gap: 0.45rem; align-items: center;
    }
    .settlement-fields-row {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 0.45rem 0.5rem;
        align-items: start;
    }
    .settlement-fields-row select,
    .settlement-fields-row input {
        width: 100%; box-sizing: border-box;
        padding: 0.32rem 0.45rem; border-radius: 6px;
        border: 1px solid rgba(255,255,255,0.12); background: rgba(0,0,0,0.2);
        color: #e2e8f0; font-size: 0.82rem;
    }
    .settlement-repayer-select {
        max-width: 100%;
        text-overflow: ellipsis;
    }
    @media (max-width: 1100px) {
        .settlement-fields-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    .followup-meta-row {
        display: grid;
        grid-template-columns: 9rem minmax(0, 1fr);
        gap: 0.45rem 0.65rem;
        align-items: start;
    }
    .followup-body-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0.45rem 0.65rem;
        align-items: start;
    }
    .followup-field { display: block; min-width: 0; }
    .followup-field-label {
        display: block; font-size: 0.78rem; color: #94a3b8; margin-bottom: 0.15rem;
    }
    .followup-scroll-cell label,
    .followup-scroll-cell.followup-field {
        font-size: 0.78rem; color: #94a3b8;
    }
    .field-display {
        width: 100%; margin-top: 0; padding: 0.32rem 0.45rem; border-radius: 6px;
        border: 1px solid rgba(255,255,255,0.08); background: rgba(0,0,0,0.15);
        color: #e2e8f0; font-size: 0.82rem; box-sizing: border-box;
        line-height: 1.35;
    }
    .field-display--meta,
    .followup-meta-row .field-display:not(.field-display--scrollcell):not(.field-display--attachment) {
        height: 1.85rem; min-height: 1.85rem; max-height: 1.85rem;
        display: flex; align-items: center;
    }
    .field-display--scrollcell {
        height: 4.5rem; min-height: 4.5rem; max-height: 4.5rem;
        overflow-y: auto; overflow-x: hidden;
        white-space: pre-wrap; word-break: break-word;
    }
    .field-display--attachment {
        height: auto; min-height: 2.75rem; max-height: 4.5rem;
        overflow-y: auto; overflow-x: hidden;
    }
    .followup-view-only {
        display: inline-flex; flex-wrap: wrap; gap: 0.35rem; align-items: center;
    }
    .followup-saved-attachments {
        display: flex; flex-wrap: wrap; gap: 0.35rem;
        align-items: center; width: 100%;
    }
    .attachment-thumb--saved {
        width: 36px; height: 36px; border-radius: 5px;
        border: 1px solid rgba(148,163,184,0.35);
        background: rgba(15,23,42,0.55);
    }
    .attachment-thumb-link { display: inline-flex; line-height: 0; }
    .attachment-chip-saved {
        max-width: 100%;
    }
    .status-badge {
        display: inline-flex; align-items: center; width: 100%;
        height: 1.85rem; min-height: 1.85rem; max-height: 1.85rem;
        padding: 0.15rem 0.5rem; border-radius: 6px; font-size: 0.82rem;
        box-sizing: border-box;
        background: rgba(56,189,248,0.12); border: 1px solid rgba(56,189,248,0.25);
        color: #e2e8f0;
    }
    .followup-meta-row select,
    .followup-meta-row input {
        width: 100%; margin-top: 0; padding: 0.32rem 0.45rem; border-radius: 6px;
        border: 1px solid rgba(255,255,255,0.15); background: rgba(0,0,0,0.25);
        color: #e2e8f0; box-sizing: border-box;
        height: 1.85rem; min-height: 1.85rem; max-height: 1.85rem;
        font-size: 0.82rem;
    }
    .followup-actions-bar {
        display: flex; flex-wrap: nowrap; gap: 0.45rem; align-items: center;
        height: 2rem; min-height: 2rem; margin-top: 0.45rem;
        flex-shrink: 0;
    }
    .followup-actions-bar .btn[disabled] {
        opacity: 0.45; cursor: not-allowed; pointer-events: none;
    }
    .followup-textarea-scroll,
    .followup-scroll-cell textarea {
        width: 100%; margin-top: 0; padding: 0.32rem 0.45rem; border-radius: 6px;
        border: 1px solid rgba(255,255,255,0.15); background: rgba(0,0,0,0.25);
        color: #e2e8f0; box-sizing: border-box; font-size: 0.82rem;
        height: 4.5rem; min-height: 4.5rem; max-height: 4.5rem;
        overflow-y: auto; resize: none; display: block;
    }
    .followup-attachment-zone { min-height: 6.35rem; }
    .followup-attachment-spacer {
        height: 2.25rem; min-height: 2.25rem; margin-top: 0.1rem;
    }
    .followup-entry-shell--create .followup-attachment-spacer { display: none !important; }
    .followup-attachment-upload-slot { margin-top: 0.1rem; }
    .followup-attachment-upload { margin-top: 0; }
    .attachment-upload-toggle { margin-bottom: 0.25rem; }
    .attachment-upload-panel { margin-top: 0.15rem; }
    .attachment-dropzone-compact {
        padding: 0.55rem 0.65rem !important;
    }
    .attachment-dropzone-compact strong {
        font-size: 0.82rem !important; margin-bottom: 0.15rem !important;
    }
    .attachment-dropzone-compact span {
        font-size: 0.72rem !important;
    }
    .entry-cite-btn { margin-top: 0; }
    @media (max-width: 700px) {
        .followup-meta-row { grid-template-columns: 1fr; }
        .followup-body-grid { grid-template-columns: 1fr; }
    }
    .followup-form label { display: block; font-size: 0.82rem; }
    .followup-form input, .followup-form textarea, .followup-form select {
        width: 100%; margin-top: 0.2rem; padding: 0.4rem; border-radius: 6px;
        border: 1px solid rgba(255,255,255,0.15); background: rgba(0,0,0,0.25); color: #e2e8f0;
    }
    .form-actions { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
    .btn {
        padding: 0.5rem 1rem; border-radius: 6px; border: 1px solid rgba(255,255,255,0.2);
        background: rgba(255,255,255,0.08); color: #e2e8f0; cursor: pointer; font-size: 0.85rem;
        height: 36px; box-sizing: border-box; display: inline-flex; align-items: center;
    }
    .btn.primary { background: #0ea5e9; border-color: #0ea5e9; font-weight: 600; }
    .btn-ghost { display: inline-block; text-align: center; }
    .mark-select {
        padding: 0.35rem; border-radius: 6px; background: rgba(0,0,0,0.2);
        color: #e2e8f0; border: 1px solid rgba(255,255,255,0.15);
    }
    .attachment-uploader-field { display: block; }
    .attachment-uploader-label {
        display: block; font-size: 0.82rem; color: #94a3b8; margin-bottom: 0.35rem;
    }
    .attachment-uploader { margin-top: 0.15rem; }
    .attachment-dropzone {
        border: 1px dashed rgba(148,163,184,0.45);
        border-radius: 12px;
        padding: 16px;
        background: rgba(15,23,42,0.45);
        cursor: pointer;
        text-align: center;
        transition: border-color 0.15s ease, background 0.15s ease;
    }
    .attachment-dropzone strong {
        display: block; color: #e2e8f0; font-size: 0.9rem; margin-bottom: 0.35rem;
    }
    .attachment-dropzone span {
        display: block; color: #94a3b8; font-size: 0.78rem; line-height: 1.4;
    }
    .attachment-dropzone:hover,
    .attachment-dropzone:focus {
        outline: none;
        border-color: rgba(56,189,248,0.55);
        background: rgba(56,189,248,0.08);
    }
    .attachment-dropzone.drag-over {
        border-color: rgba(56,189,248,0.75);
        background: rgba(56,189,248,0.12);
    }
    .attachment-preview {
        display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px;
    }
    .attachment-chip {
        display: flex; align-items: center; gap: 0.45rem;
        max-width: 100%;
        padding: 0.35rem 0.5rem;
        border-radius: 8px;
        background: rgba(255,255,255,0.08);
        border: 1px solid rgba(255,255,255,0.1);
        font-size: 0.75rem;
    }
    .attachment-chip-meta {
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        color: #cbd5e1; max-width: 220px;
    }
    .attachment-chip-meta-link {
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        color: #38bdf8; max-width: 220px; text-decoration: none;
    }
    .attachment-chip-meta-link:hover {
        color: #7dd3fc; text-decoration: underline;
    }
    .attachment-chip-open-link {
        color: inherit; text-decoration: none; flex-shrink: 0;
    }
    .attachment-open-link {
        color: #38bdf8; text-decoration: none;
    }
    .attachment-open-link:hover {
        color: #7dd3fc; text-decoration: underline;
    }
    .attachment-chip-remove {
        flex-shrink: 0;
        border: none; background: transparent; color: #f87171;
        cursor: pointer; font-size: 1rem; line-height: 1; padding: 0 0.2rem;
    }
    .attachment-chip-remove:hover { color: #fca5a5; }
    .attachment-thumb {
        width: 48px; height: 48px; border-radius: 6px;
        object-fit: cover; flex-shrink: 0;
        cursor: pointer;
    }
    .attachment-error {
        margin-top: 0.5rem; font-size: 0.8rem; color: #f87171;
    }
    .attachment-image-lightbox[hidden] { display: none !important; }
    .attachment-image-lightbox {
        position: fixed; inset: 0; z-index: 10000;
        display: flex; align-items: center; justify-content: center;
    }
    .attachment-image-lightbox-backdrop {
        position: absolute; inset: 0;
        background: rgba(0, 0, 0, 0.88);
        cursor: pointer;
    }
    .attachment-image-lightbox-panel {
        position: relative; z-index: 1;
        max-width: 92vw; max-height: 92vh;
    }
    .attachment-image-lightbox-img {
        display: block;
        max-width: 92vw; max-height: 92vh;
        object-fit: contain;
        border-radius: 6px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
    }
    .attachment-image-lightbox-close {
        position: absolute; top: -2.25rem; right: 0;
        border: none; background: transparent;
        color: #f1f5f9; font-size: 2rem; line-height: 1;
        cursor: pointer; padding: 0 0.25rem;
    }
    .attachment-image-lightbox-close:hover { color: #fff; }
    body.attachment-lightbox-open { overflow: hidden; }
"""

_WORKBENCH_CSS = f"""
<style>
{PAGE_CHROME_CSS}
{WORKBENCH_BODY_CSS}
{STANDARD_HEADER_CSS}
{BTN_CSS}
{TABLE_SCROLL_CSS}
{_WORKBENCH_SPECIFIC_CSS}
</style>
"""
