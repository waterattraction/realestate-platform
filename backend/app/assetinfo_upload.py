"""Excel 导入 V2 — 预检、导入、分页查询."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import assetinfo_cleanse as cleanse
from app import assetinfo_date_rules
from app import assetinfo_templates as templates
from app import query_utils
from app.auth import record_assetinfo_run, record_sheet_run
from app.issuance_labels import format_rate
from app.issuance_upload import ISSUANCE_CITY_UNKNOWN

RECONCILIATION_TOLERANCE = cleanse.RECONCILIATION_TOLERANCE


def coerce_optional_int(value: str | int | None) -> int | None:
    return query_utils.parse_optional_int(value)


def coerce_bool(value: str | int | bool | None) -> bool:
    parsed = query_utils.parse_optional_bool(value)
    return bool(parsed) if parsed is not None else False


def _parse_transferred_filter(value: str | None) -> str | None:
    if value is None:
        return None
    text_val = str(value).strip().lower()
    if not text_val:
        return None
    if text_val in ("yes", "y", "1", "true", "是"):
        return "yes"
    if text_val in ("no", "n", "0", "false", "否"):
        return "no"
    raise HTTPException(status_code=400, detail="已转让筛选仅支持：是/否")


MONITOR_DISCOUNT_RATE_NONE = "__none__"
MONITOR_EXPORT_MAX = 20_000

MONITOR_EXPORT_COLUMNS: tuple[str, ...] = (
    "trust_product_name",
    "asset_code",
    "custody_asset_code",
    "source_asset_code",
    "data_date",
    "overdue_days",
    "initial_transfer_amount",
    "repaid_amount",
    "remaining_amount",
    "asset_transfer_discount_rate",
    "last_renovation_payment_date",
    "city",
    "source_file_name",
    "source_sheet_name",
    "synced_at",
    "created_at",
    "last_payment_date",
    "max_payment_date",
    "risk_score",
    "risk_level",
    "id",
    "trust_product_id",
    "trust_asset_id",
)

MONITOR_EXPORT_LABELS: dict[str, str] = {
    "trust_product_name": "信托产品",
    "asset_code": "资产主编号",
    "custody_asset_code": "托管房源号",
    "source_asset_code": "资产信托号",
    "data_date": "数据日期",
    "overdue_days": "逾期天数",
    "initial_transfer_amount": "初始受让金额",
    "repaid_amount": "已还款金额",
    "remaining_amount": "剩余还款金额",
    "asset_transfer_discount_rate": "资产转让折扣率(%)",
    "last_renovation_payment_date": "最后一期装修款付款时间",
    "city": "城市",
    "source_file_name": "文件名",
    "source_sheet_name": "Sheet名",
    "synced_at": "同步时间",
    "created_at": "创建时间",
    "last_payment_date": "最后回款日",
    "max_payment_date": "最大回款日",
    "risk_score": "风险评分",
    "risk_level": "风险等级",
    "id": "ID",
    "trust_product_id": "产品ID",
    "trust_asset_id": "资产ID",
}

MONITOR_SORT_COLUMNS: dict[str, str] = {
    "trust_product_name": "tp.name",
    "asset_code": "r.asset_code",
    "custody_asset_code": "r.custody_asset_code",
    "source_asset_code": "r.source_asset_code",
    "data_date": "r.data_date",
    "overdue_days": "r.overdue_days",
    "initial_transfer_amount": "r.initial_transfer_amount",
    "repaid_amount": "r.repaid_amount",
    "remaining_amount": "r.remaining_amount",
    "asset_transfer_discount_rate": "iss.asset_transfer_discount_rate",
    "last_renovation_payment_date": "r.last_renovation_payment_date",
}

MONITOR_DEFAULT_ORDER_BY = """
    r.data_date DESC,
    r.custody_asset_code ASC NULLS LAST,
    r.source_asset_code ASC NULLS LAST,
    r.asset_code ASC,
    r.id ASC
"""


def _parse_monitor_discount_rate_filter(raw) -> str | float | None:
    if raw is None or raw == "":
        return None
    text = str(raw).strip()
    if text == MONITOR_DISCOUNT_RATE_NONE:
        return MONITOR_DISCOUNT_RATE_NONE
    try:
        return float(text)
    except ValueError:
        return None


def _parse_monitor_sort_dir(raw) -> str:
    return "asc" if str(raw or "").strip().lower() == "asc" else "desc"


def build_monitor_order_by(sort_by: str | None, sort_dir: str | None) -> str:
    if not sort_by:
        return MONITOR_DEFAULT_ORDER_BY.strip()
    expr = MONITOR_SORT_COLUMNS.get(sort_by)
    if not expr:
        return MONITOR_DEFAULT_ORDER_BY.strip()
    direction = "ASC" if sort_dir == "asc" else "DESC"
    return f"""
        {expr} {direction} NULLS LAST,
        r.data_date DESC,
        r.custody_asset_code ASC NULLS LAST,
        r.id ASC
    """.strip()


def build_record_filters(
    *,
    trust_product_id: str | int | None = None,
    data_date: str | None = None,
    asset_code: str | None = None,
    custody_asset_code: str | None = None,
    source_asset_code: str | None = None,
    source_file_name: str | None = None,
    source_sheet_name: str | None = None,
    include_history: str | int | bool | None = None,
    transferred: str | None = None,
    asset_transfer_discount_rate: str | None = None,
    city: str | None = None,
    sort_by: str | None = None,
    sort_dir: str | None = None,
) -> dict[str, Any]:
    """将查询参数中的空字符串规范为 None，避免 Optional[int] 解析失败."""
    pid = coerce_optional_int(trust_product_id)
    transferred_filter = _parse_transferred_filter(transferred)
    if transferred_filter and pid is None:
        raise HTTPException(status_code=400, detail="已转让筛选须先选择信托产品")
    parsed_sort_by = query_utils.clean_optional_str(sort_by)
    if parsed_sort_by and parsed_sort_by not in MONITOR_SORT_COLUMNS:
        parsed_sort_by = None
    return {
        "trust_product_id": pid,
        "data_date": data_date or None,
        "asset_code": asset_code or None,
        "custody_asset_code": custody_asset_code or None,
        "source_asset_code": source_asset_code or None,
        "source_file_name": source_file_name or None,
        "source_sheet_name": source_sheet_name or None,
        "include_history": coerce_bool(include_history),
        "transferred": transferred_filter,
        "asset_transfer_discount_rate": _parse_monitor_discount_rate_filter(
            asset_transfer_discount_rate
        ),
        "city": query_utils.clean_optional_str(city),
        "sort_by": parsed_sort_by,
        "sort_dir": _parse_monitor_sort_dir(sort_dir),
    }


REPAYMENT_SHEET_KEYWORD = "已还款"
REPAYMENT_PLAN_SHEET = cleanse.REPAYMENT_PLAN_SHEET_KEYWORD
# 兼容旧测试/调用名
REPAYMENT_SKIP_SHEET = REPAYMENT_PLAN_SHEET

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
COL_LAST_RENOVATION_PAYMENT = cleanse.COL_ALIASES["last_renovation_payment_date"]

REPAYMENT_OPTIONAL_FIELDS = (
    "asset_pool_code",
    "current_payer",
    "planned_repayment_amount",
    "initial_renovation_amount",
    "cumulative_repaid_amount",
    "remaining_balance",
)

MONITOR_OPTIONAL_FIELDS = (
    "asset_pool_code",
    "renovation_vendor",
    "asset_status",
    "community_name",
    "city",
    "collection_contract_code",
    "custody_agreement_sign_date",
    "collection_contract_years",
    "owner_code",
    "withholding_ratio",
    "actual_monthly_rent",
)

MONITOR_OPTIONAL_DATE_FIELDS = frozenset({
    "custody_agreement_sign_date",
})
MONITOR_OPTIONAL_RATE_FIELDS = frozenset({
    "withholding_ratio",
})
MONITOR_OPTIONAL_AMOUNT_FIELDS = frozenset({
    "collection_contract_years",
    "actual_monthly_rent",
})
REPAYMENT_OPTIONAL_AMOUNT_FIELDS = frozenset({
    "planned_repayment_amount",
    "initial_renovation_amount",
    "cumulative_repaid_amount",
    "remaining_balance",
})


def upload_root() -> Path:
    root = Path(os.getenv("ASSET_UPLOAD_DIR", "/data/uploads"))
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


def action_to_status(action: str | None) -> str:
    """将预检 action 映射为对外 status（import | needs_confirm | reject）."""
    if action in ("import", "overwrite"):
        return "import"
    if action == "needs_confirm":
        return "needs_confirm"
    if action == "reject":
        return "reject"
    if action == "skip":
        return "skip"
    return "reject"


def sheet_is_selectable(sheet: dict) -> bool:
    status = sheet.get("status") or action_to_status(sheet.get("action"))
    return status in ("import", "needs_confirm")


def enrich_preview_sheet(sheet: dict, batch_uuid: str) -> dict:
    """补充 Sheet 级预检对外字段."""
    status = action_to_status(sheet.get("action"))
    return {
        **sheet,
        "file_id": batch_uuid,
        "sheet_key": sheet_key(sheet["file_name"], sheet["sheet_name"]),
        "type": sheet.get("sheet_type"),
        "rows": sheet.get("row_count", 0),
        "amount": sheet.get("amount_sum"),
        "status": status,
        "selectable": status in ("import", "needs_confirm"),
    }


def resolve_selected_sheet_keys(
    preview: dict,
    selected_sheet_keys: list[str] | None,
    selected_sheets: list[str] | None,
) -> set[str]:
    """解析用户勾选的 Sheet，支持 sheet_key 或 sheet_name（单文件内唯一时）."""
    if selected_sheet_keys:
        return {k.strip() for k in selected_sheet_keys if k and str(k).strip()}

    if not selected_sheets:
        return set()

    names = [str(n).strip() for n in selected_sheets if n and str(n).strip()]
    if not names:
        return set()

    preview_sheets = preview.get("sheets", [])
    resolved: set[str] = set()
    for name in names:
        matches = [
            sheet_key(s["file_name"], s["sheet_name"])
            for s in preview_sheets
            if s.get("sheet_name") == name
        ]
        if not matches:
            raise HTTPException(status_code=400, detail=f"未找到 Sheet: {name}")
        if len(matches) > 1:
            raise HTTPException(
                status_code=400,
                detail=f"Sheet 名「{name}」在多个文件中重复，请使用 sheet_key（file::sheet）",
            )
        resolved.add(matches[0])
    return resolved


def validate_selected_sheets(
    preview: dict,
    selected: set[str],
    confirm_sheet_keys: set[str],
) -> None:
    if not selected:
        raise HTTPException(status_code=400, detail="必须选择至少一个Sheet")

    preview_by_key = {
        sheet_key(s["file_name"], s["sheet_name"]): s for s in preview.get("sheets", [])
    }
    parsed_keys = set(preview_by_key.keys())

    unknown = selected - parsed_keys
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"selected_sheets 包含未预检的 Sheet: {', '.join(sorted(unknown))}",
        )

    for key in selected:
        sheet = preview_by_key[key]
        status = sheet.get("status") or action_to_status(sheet.get("action"))
        action = sheet.get("action")
        if status == "reject" or action in ("reject", "failed"):
            raise HTTPException(
                status_code=400,
                detail=f"Sheet「{sheet.get('sheet_name')}」状态为 reject，禁止导入",
            )
        if status == "skip" or action == "skip":
            raise HTTPException(
                status_code=400,
                detail=f"Sheet「{sheet.get('sheet_name')}」无需导入（skip）",
            )
        if status == "needs_confirm" and key not in confirm_sheet_keys:
            raise HTTPException(
                status_code=400,
                detail=f"Sheet「{sheet.get('sheet_name')}」需二次确认后才能导入",
            )


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


@dataclass
class MonitorParseResult:
    rows: list[dict]
    errors: list[str]
    batch_date: date | None
    raw_row_count: int
    parsed_row_count: int
    skipped_row_count: int
    skipped_reason_summary: dict[str, int]
    detected_columns: list[str]
    required_column_mapping: dict[str, str | None]
    batch_date_source: str | None = None
    warnings: list[str] | None = None

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


def _text_contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _classify_by_name(file_name: str, sheet_name: str) -> str | None:
    if cleanse.is_repayment_plan_sheet(sheet_name):
        return "repayment_plan"
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
    if cleanse.is_repayment_plan_sheet(sheet_name):
        return "repayment_plan"
    if REPAYMENT_SHEET_KEYWORD in sheet_name:
        return "repayment_detail"
    if cleanse.is_monitor_sheet(df):
        return "asset_monitor"
    return None


def classify_sheet(file_name: str, sheet_name: str, df: pd.DataFrame) -> SheetClassification:
    if cleanse.is_repayment_plan_sheet(sheet_name):
        return SheetClassification("repayment_plan", "repayment_plan", "repayment_plan")

    name_type = _classify_by_name(file_name, sheet_name)
    header_type = _classify_by_header(sheet_name, df)

    if (
        name_type in ("repayment_detail", "asset_monitor")
        and header_type in ("repayment_detail", "asset_monitor")
        and name_type != header_type
    ):
        return SheetClassification("ambiguous_sheet_type", name_type, header_type)

    if name_type in ("repayment_detail", "asset_monitor", "repayment_plan"):
        return SheetClassification(name_type, name_type, header_type)

    if header_type in ("repayment_detail", "asset_monitor", "repayment_plan"):
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
        df = pd.read_excel(path, sheet_name=name, header=0, nrows=5)
        result = classify_sheet(path.name, name, df)
        if result.sheet_type not in ("skip", "unknown", "ambiguous_sheet_type", "repayment_plan"):
            types.add(result.sheet_type)
    if "repayment_detail" in types and "asset_monitor" in types:
        return "mixed"
    if "repayment_detail" in types:
        return "repayment_detail"
    if "asset_monitor" in types:
        return "asset_monitor"
    return "unknown"


def _opt_field_from_row(
    row: pd.Series,
    col_map: dict[str, str | None],
    field: str,
    *,
    as_amount: bool = False,
    as_date: bool = False,
    as_rate: bool = False,
):
    col = col_map.get(field)
    if not col:
        return None
    val = row[col]
    if as_date:
        return cleanse.to_date_value(val)
    if as_rate:
        return cleanse.to_rate_value(val)
    if as_amount:
        return cleanse.to_numeric_value(val)
    return cleanse.to_optional_str(val)


def _build_optional_col_map(df: pd.DataFrame, fields: tuple[str, ...]) -> dict[str, str | None]:
    return {field: cleanse.pick_aliased_column(df, field) for field in fields}


def _load_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, header=0)
    return df.dropna(how="all")


def _normalize_excel_asset_code(value) -> str | None:
    """Excel 资产编号/托管编码：去空白、处理数值型 .0。"""
    return cleanse.clean_custody_code(value)


def _primary_asset_code_from_trust_no(trust_no: str | None) -> str | None:
    """资产主编号：资产信托号左 12 位；不足 12 位则用整值。"""
    if not trust_no:
        return None
    return trust_no[:12] if len(trust_no) >= 12 else trust_no


def _resolve_monitor_asset_fields(
    row: pd.Series, col_asset: str | None, col_custody: str | None
) -> tuple[str | None, str | None, str | None]:
    """监控导入：资产编号(房源)整列→source；托管列→custody；信托号左12→asset_code。"""
    trust_no = _normalize_excel_asset_code(row[col_asset]) if col_asset else None
    custody = _normalize_excel_asset_code(row[col_custody]) if col_custody else None

    if trust_no:
        asset_code = _primary_asset_code_from_trust_no(trust_no)
        if custody is None:
            custody = asset_code
        return asset_code, custody, trust_no

    if custody:
        primary = _primary_asset_code_from_trust_no(custody)
        return primary, custody, custody

    return None, None, None


def _excel_custody_source_mismatch_rows(df: pd.DataFrame) -> list[dict]:
    """检测 Excel 原始列：资产编号(房源) vs 托管房源编码 不一致行。"""
    col_asset = cleanse.pick_column(df, *COL_ASSET_CODE)
    col_custody = cleanse.pick_column(df, *COL_CUSTODY)
    if not col_asset or not col_custody:
        return []
    mismatches: list[dict] = []
    for idx, row in df.iterrows():
        asset_no = _normalize_excel_asset_code(row[col_asset])
        custody_no = _normalize_excel_asset_code(row[col_custody])
        if asset_no and custody_no and asset_no != custody_no:
            mismatches.append({
                "excel_row": int(idx) + 2,
                "asset_number": asset_no,
                "custody_from_excel": custody_no,
            })
    return mismatches


def _apply_asset_code_mismatch_precheck(result: dict[str, Any], mismatches: list[dict]) -> None:
    """资产编号与托管编码不一致 → 预检 ERROR（needs_confirm，须二次确认后导入）。"""
    if not mismatches:
        return
    count = len(mismatches)
    samples = mismatches[:5]
    sample_txt = "; ".join(
        f"行{m['excel_row']}: 资产编号={m['asset_number']} 托管={m['custody_from_excel']}"
        for m in samples
    )
    result["asset_code_mismatch_count"] = count
    result["asset_code_mismatch_samples"] = samples
    result["warnings"].insert(
        0,
        f"[ERROR] 资产编号(房源)与托管房源编码不一致 {count} 行；"
        f"导入时以托管编号定位底层资产，分笔号写入 source_asset_code。样例: {sample_txt}",
    )
    if result.get("action") in ("failed", "reject"):
        return
    result["action"] = "needs_confirm"
    result["importable"] = True
    mismatch_reason = (
        f"<strong>编码不一致 {count} 行</strong>：将以「托管房源编码」为持久化锚点；"
        f"「资产编号(房源)」作为分笔号关联。须勾选确认后方可导入。"
    )
    prev = (result.get("reason") or "").strip()
    result["reason"] = mismatch_reason + (f"<br><br>{prev}" if prev else "")


def _finalize_asset_code_mismatch_precheck(
    result: dict[str, Any], mismatches: list[dict]
) -> dict[str, Any]:
    if mismatches and result.get("action") not in ("failed", "reject"):
        _apply_asset_code_mismatch_precheck(result, mismatches)
    return result


def _fetch_trust_asset_row(
    conn: Connection,
    trust_product_id: int,
    *,
    custody_asset_code: str | None = None,
    source_asset_code: str | None = None,
) -> Any | None:
    if custody_asset_code:
        return conn.execute(
            text("""
                SELECT id, asset_code, custody_asset_code, source_asset_code
                FROM trust_assets
                WHERE trust_product_id = :pid AND custody_asset_code = :custody
                LIMIT 1
            """),
            {"pid": trust_product_id, "custody": custody_asset_code},
        ).fetchone()
    if source_asset_code:
        return conn.execute(
            text("""
                SELECT id, asset_code, custody_asset_code, source_asset_code
                FROM trust_assets
                WHERE trust_product_id = :pid AND source_asset_code = :source
                LIMIT 1
            """),
            {"pid": trust_product_id, "source": source_asset_code},
        ).fetchone()
    return None


def _custody_taken_by_other(
    conn: Connection,
    trust_product_id: int,
    custody_asset_code: str,
    exclude_id: int,
) -> bool:
    row = conn.execute(
        text("""
            SELECT id FROM trust_assets
            WHERE trust_product_id = :pid
              AND custody_asset_code = :custody
              AND id != :exclude
            LIMIT 1
        """),
        {"pid": trust_product_id, "custody": custody_asset_code, "exclude": exclude_id},
    ).fetchone()
    return row is not None


def _upsert_trust_asset(
    conn: Connection,
    trust_product_id: int,
    asset_code: str,
    custody_asset_code: str | None,
    initial_transfer_amount: float,
    source_asset_code: str | None = None,
    *,
    distinct_custody: bool = False,
) -> int:
    source = source_asset_code or asset_code
    existing = None

    if distinct_custody:
        if custody_asset_code:
            existing = _fetch_trust_asset_row(
                conn, trust_product_id, custody_asset_code=custody_asset_code,
            )
        if existing is None and source:
            by_source = _fetch_trust_asset_row(
                conn, trust_product_id, source_asset_code=source,
            )
            if by_source:
                ex_custody = by_source.custody_asset_code
                if (
                    not custody_asset_code
                    or ex_custody is None
                    or ex_custody == custody_asset_code
                ):
                    existing = by_source
    else:
        if source:
            existing = _fetch_trust_asset_row(
                conn, trust_product_id, source_asset_code=source,
            )
        if existing is None and asset_code:
            existing = conn.execute(
                text("""
                    SELECT id, asset_code, custody_asset_code, source_asset_code
                    FROM trust_assets
                    WHERE trust_product_id = :pid AND asset_code = :code
                    LIMIT 1
                """),
                {"pid": trust_product_id, "code": asset_code},
            ).fetchone()
        if existing is None and custody_asset_code and (
            source and custody_asset_code == source
        ):
            existing = _fetch_trust_asset_row(
                conn, trust_product_id, custody_asset_code=custody_asset_code,
            )

    if distinct_custody:
        safe_custody = custody_asset_code
    else:
        safe_custody = (
            custody_asset_code if custody_asset_code and custody_asset_code == source else None
        )

    if existing:
        update_custody: str | None = None
        if distinct_custody:
            if custody_asset_code and not existing.custody_asset_code:
                if not _custody_taken_by_other(
                    conn, trust_product_id, custody_asset_code, int(existing.id),
                ):
                    update_custody = custody_asset_code
        else:
            update_custody = safe_custody

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
                "custody": update_custody,
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
            "custody": (custody_asset_code or asset_code) if distinct_custody else (safe_custody or source),
            "source": source,
            "initial": initial_transfer_amount,
        },
    ).fetchone()
    return int(row.id)


def _fetch_monitor_latest_snapshot(
    conn: Connection, trust_product_id: int
) -> tuple[date | None, int, set[str]]:
    """返回 (latest_date, 该日产品监控总行数, 该日 distinct asset_code)。"""
    row = conn.execute(
        text("""
            SELECT MAX(data_date) AS latest_date
            FROM trust_asset_monitor_records
            WHERE trust_product_id = :pid
        """),
        {"pid": trust_product_id},
    ).fetchone()
    if row is None or row.latest_date is None:
        return None, 0, set()

    latest_date = row.latest_date
    total_row = conn.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM trust_asset_monitor_records
            WHERE trust_product_id = :pid AND data_date = :dd
        """),
        {"pid": trust_product_id, "dd": latest_date},
    ).fetchone()
    code_rows = conn.execute(
        text("""
            SELECT DISTINCT asset_code
            FROM trust_asset_monitor_records
            WHERE trust_product_id = :pid AND data_date = :dd
              AND asset_code IS NOT NULL
        """),
        {"pid": trust_product_id, "dd": latest_date},
    )
    codes = {str(r.asset_code) for r in code_rows if r.asset_code}
    return latest_date, int(total_row.cnt), codes


def _monitor_precheck_confirm_reasons(
    *,
    latest_date: date | None,
    latest_total: int,
    latest_codes: set[str],
    excel_rows: int,
    excel_codes: set[str],
    sheet_db_cnt: int,
) -> list[str]:
    reasons: list[str] = []

    if latest_date is None:
        if excel_rows > 0:
            reasons.append(
                f"<strong>首次导入</strong>：产品尚无监控快照，本次解析 {excel_rows} 行，须确认后导入。"
            )
        return reasons

    if excel_rows != latest_total:
        reasons.append(
            f"最新快照日 {latest_date} 产品共 {latest_total} 行，"
            f"本次 Sheet 解析 {excel_rows} 行，记录数不一致。"
        )

    unknown = sorted(excel_codes - latest_codes)
    if unknown:
        sample = "、".join(unknown[:5])
        suffix = " 等" if len(unknown) > 5 else ""
        reasons.append(
            f"存在 {len(unknown)} 个资产主编号不在最新快照日（{latest_date}）中："
            f"{sample}{suffix}。"
        )

    if sheet_db_cnt > 0 and sheet_db_cnt != excel_rows:
        reasons.append(
            f"同 Sheet 已有 {sheet_db_cnt} 条（快照日导入范围），"
            f"本次 {excel_rows} 条，条数不一致。"
        )

    return reasons


def _apply_monitor_confirm_precheck(result: dict[str, Any], reasons: list[str]) -> None:
    if not reasons:
        return
    result["action"] = "needs_confirm"
    result["importable"] = True
    result["reason"] = "<br><br>".join(reasons) + "<br><br>须勾选确认后方可导入。"
    result["monitor_confirm_reasons"] = reasons


def _resolve_asset_fields(
    row: pd.Series, col_asset: str | None, col_custody: str | None
) -> tuple[str | None, str | None, str | None]:
    """资产编号(房源) 为唯一权威；托管列不一致时忽略，由预检 ERROR 提示用户确认。"""
    source = _normalize_excel_asset_code(row[col_asset]) if col_asset else None
    custody_from_excel = _normalize_excel_asset_code(row[col_custody]) if col_custody else None

    if source:
        return source, source, source

    if custody_from_excel:
        return custody_from_excel, custody_from_excel, custody_from_excel

    return None, None, None


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


def _require_monitor_sheet_name(sheet_name: str) -> str | None:
    """返回错误信息；合法则返回 None。"""
    if sheet_name is None or not str(sheet_name).strip():
        return "source_sheet_name 缺失，无法安全覆盖资产监控快照"
    return None


def _require_repayment_sheet_name(sheet_name: str) -> str | None:
    if sheet_name is None or not str(sheet_name).strip():
        return "source_sheet_name 缺失，无法导入还款明细"
    return None


def _require_source_file_name(file_name: str) -> str | None:
    if file_name is None or not str(file_name).strip():
        return "source_file_name 缺失，无法导入还款明细"
    return None


def _check_monitor_within_sheet_multi_rows(rows: list[dict]) -> list[str]:
    """Sheet 内同房源多行提示（不阻止导入）。"""
    from collections import Counter

    custody_keys = [
        r.get("custody_asset_code") or r.get("source_asset_code") or r.get("asset_code")
        for r in rows
    ]
    source_keys = [
        r.get("source_asset_code") or r.get("asset_code")
        for r in rows
    ]
    custody_dup = any(v > 1 for k, v in Counter(custody_keys).items() if k)
    source_dup = any(v > 1 for k, v in Counter(source_keys).items() if k)
    if custody_dup or source_dup:
        return ["同一 Sheet 中存在同一房源多行记录，请确认是否为正常多笔数据"]
    return []


def fetch_monitor_batch_duplicate_checks(
    conn: Connection,
    trust_product_id: int | None = None,
    data_date: str | None = None,
    source_sheet_name: str | None = None,
) -> list[dict]:
    """重复批次检查：同 Sheet 同 trust_asset_id 多行（数据质量，不用于主查询过滤）。"""
    where_parts = ["1=1"]
    params: dict = {}
    if trust_product_id is not None:
        where_parts.append("trust_product_id = :trust_product_id")
        params["trust_product_id"] = trust_product_id
    if data_date:
        where_parts.append("data_date = :data_date")
        params["data_date"] = data_date
    if source_sheet_name:
        where_parts.append("source_sheet_name = :source_sheet_name")
        params["source_sheet_name"] = source_sheet_name
    where_sql = " AND ".join(where_parts)

    rows = conn.execute(
        text(f"""
            SELECT
                trust_product_id,
                data_date,
                source_sheet_name,
                trust_asset_id,
                COUNT(*) AS row_count
            FROM trust_asset_monitor_records
            WHERE {where_sql}
            GROUP BY trust_product_id, data_date, source_sheet_name, trust_asset_id
            HAVING COUNT(*) > 1
            ORDER BY row_count DESC, trust_product_id, data_date, source_sheet_name
        """),
        params,
    )
    items = []
    for r in rows:
        items.append({
            "trust_product_id": r.trust_product_id,
            "data_date": str(r.data_date),
            "source_sheet_name": r.source_sheet_name,
            "trust_asset_id": r.trust_asset_id,
            "row_count": int(r.row_count),
            "check_type": "duplicate_batch_trust_asset_id",
        })

    custody_rows = conn.execute(
        text(f"""
            SELECT
                trust_product_id,
                data_date,
                source_sheet_name,
                COALESCE(custody_asset_code, asset_code) AS custody_asset_code,
                COALESCE(source_asset_code, asset_code) AS source_asset_code,
                COUNT(*) AS row_count
            FROM trust_asset_monitor_records
            WHERE {where_sql}
            GROUP BY trust_product_id, data_date, source_sheet_name,
                     COALESCE(custody_asset_code, asset_code),
                     COALESCE(source_asset_code, asset_code)
            HAVING COUNT(*) > 1
            ORDER BY row_count DESC
        """),
        params,
    )
    for r in custody_rows:
        items.append({
            "trust_product_id": r.trust_product_id,
            "data_date": str(r.data_date),
            "source_sheet_name": r.source_sheet_name,
            "custody_asset_code": r.custody_asset_code,
            "source_asset_code": r.source_asset_code,
            "row_count": int(r.row_count),
            "check_type": "duplicate_batch_custody_source",
        })
    return items


def _check_within_sheet_row_duplicates(
    rows: list[dict],
) -> tuple[str, str | None, list[str]]:
    """Sheet 内仅拒绝五字段完全相同的行；期数不同视为合法多笔。"""
    warnings: list[str] = []
    seen: set[tuple] = set()
    periods_by_four_key: dict[tuple, set] = {}

    for r in rows:
        rd = r["repayment_date"]
        custody = r.get("custody_asset_code") or ""
        source = r.get("source_asset_code") or r["asset_code"]
        pn = r.get("period_no")
        amt = r["actual_repayment_amount"]
        key = (custody, source, rd, amt, pn)

        if key in seen:
            return (
                "reject",
                "Sheet 内完全重复: 托管房源 + 资产分笔 + repayment_date + amount + period_no",
                warnings,
            )
        seen.add(key)

        four_key = (custody, source, rd, amt)
        periods_by_four_key.setdefault(four_key, set()).add(pn)

    for (custody, source, rd, _amt), periods in periods_by_four_key.items():
        if len(periods) > 1:
            warnings.append(f"{custody or source} @ {rd}: 同日同金额多期数（合法多笔）")

    return "ok", None, warnings


def _repayment_period_no_warnings(df: pd.DataFrame, rows: list[dict]) -> list[str]:
    warnings: list[str] = []
    col_period = cleanse.pick_column(df, *COL_PERIOD)
    if col_period is None:
        warnings.append("Excel 未识别到还款期数列（period_no 将为空）")
        return warnings
    missing = sum(1 for r in rows if not r.get("period_no"))
    if missing:
        warnings.append(f"{missing} 行 period_no 缺失")
    return warnings


def _cross_file_repayment_overlap_count(
    conn: Connection,
    trust_product_id: int,
    file_name: str,
    rows: list[dict],
) -> int:
    """统计当前 Sheet 中有多少行在其他 source_file_name 中已有相同付款实质（四字段）。"""
    if not rows:
        return 0
    from collections import defaultdict

    by_key: dict[tuple, int] = defaultdict(int)
    for r in rows:
        custody = r.get("custody_asset_code") or ""
        source = r.get("source_asset_code") or r["asset_code"]
        key = (custody, source, r["repayment_date"], r["actual_repayment_amount"])
        by_key[key] += 1

    overlap_rows = 0
    for (custody, source, rd, amt), row_count in by_key.items():
        hit = conn.execute(
            text("""
                SELECT 1 FROM trust_repayment_detail_records
                WHERE trust_product_id = :pid
                  AND source_file_name != :file
                  AND custody_asset_code = :custody
                  AND source_asset_code IS NOT DISTINCT FROM :source
                  AND repayment_date = :rd
                  AND actual_repayment_amount = :amt
                LIMIT 1
            """),
            {
                "pid": trust_product_id,
                "file": file_name,
                "custody": custody,
                "source": source or None,
                "rd": rd,
                "amt": amt,
            },
        ).fetchone()
        if hit:
            overlap_rows += row_count
    return overlap_rows


def _delete_repayment_sheet_scope(
    conn: Connection,
    trust_product_id: int,
    file_name: str,
    sheet_name: str,
) -> int:
    result = conn.execute(
        text("""
            DELETE FROM trust_repayment_detail_records
            WHERE trust_product_id = :pid
              AND source_file_name = :file
              AND source_sheet_name = :sheet
        """),
        {"pid": trust_product_id, "file": file_name, "sheet": sheet_name},
    )
    return int(result.rowcount or 0)


def _parse_repayment_rows(
    df: pd.DataFrame,
    sheet_fallback_date: date | None,
) -> tuple[list[dict], list[str]]:
    col_asset = cleanse.pick_column(df, *COL_ASSET_CODE)
    col_custody = cleanse.pick_column(df, *COL_CUSTODY)
    col_period = cleanse.pick_column(df, *COL_PERIOD)
    col_amount = cleanse.pick_column(df, *COL_AMOUNT)
    col_date = cleanse.pick_column(df, *COL_REPAYMENT_DATE)
    opt_cols = _build_optional_col_map(df, REPAYMENT_OPTIONAL_FIELDS)

    if not col_custody and not col_asset:
        return [], ["缺少托管房源编码或资产编号(房源)列"]
    if not col_amount:
        return [], ["缺少当期实际还款金额列"]

    rows: list[dict] = []
    errors: list[str] = []
    for idx, row in df.iterrows():
        asset_code, custody, source = _resolve_monitor_asset_fields(row, col_asset, col_custody)
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
        parsed = {
            "asset_code": asset_code,
            "custody_asset_code": custody,
            "source_asset_code": source,
            "period_no": period_no,
            "actual_repayment_amount": amount,
            "repayment_date": repayment_date,
            "data_date": repayment_date,
        }
        for field in REPAYMENT_OPTIONAL_FIELDS:
            parsed[field] = _opt_field_from_row(
                row, opt_cols, field,
                as_amount=field in REPAYMENT_OPTIONAL_AMOUNT_FIELDS,
            )
        rows.append(parsed)
    return rows, errors


def _resolve_monitor_batch_date(
    row_dates: list[date],
    *,
    file_name: str | None,
    sheet_name: str | None,
    product_name: str | None,
) -> tuple[date | None, str, list[str]]:
    """确定监控快照 data_date；优先文件名/Sheet 规则，避免按行统计日期众数误删行。"""
    warnings: list[str] = []
    if file_name and product_name:
        parsed = assetinfo_date_rules.parse_monitor_snapshot_date(
            file_name, sheet_name or "", product_name,
        )
        if parsed.ok and parsed.parsed_date:
            return parsed.parsed_date, parsed.rule_label or "文件名/Sheet规则", warnings

    if not row_dates:
        return None, "", warnings

    from collections import Counter

    counter = Counter(row_dates)
    batch_date, top_count = counter.most_common(1)[0]
    if top_count >= max(2, len(row_dates) * 0.5):
        return batch_date, "列统计日期众数", warnings

    if len(counter) > 1:
        warnings.append(
            f"统计日期存在 {len(counter)} 个不同值，已使用最早日期 {batch_date} 作为快照日期；"
            f"建议确认文件名是否包含 MMDD 快照日期"
        )
    return batch_date, "列统计日期最早值", warnings


def _parse_monitor_rows(
    df: pd.DataFrame,
    *,
    file_name: str | None = None,
    sheet_name: str | None = None,
    product_name: str | None = None,
) -> MonitorParseResult:
    raw_row_count = len(df)
    detected_columns = [str(c) for c in df.columns]
    col_asset = cleanse.pick_column(df, *COL_ASSET_CODE)
    col_custody = cleanse.pick_column(df, *COL_CUSTODY)
    col_data = cleanse.pick_column(df, *COL_DATA_DATE)
    col_initial = cleanse.pick_column(df, *COL_INITIAL)
    col_repaid = cleanse.pick_column(df, *COL_REPAID)
    col_remaining = cleanse.pick_aliased_column(df, "remaining_amount")
    col_last_renovation = cleanse.pick_aliased_column(df, "last_renovation_payment_date")
    opt_cols = _build_optional_col_map(df, MONITOR_OPTIONAL_FIELDS)
    remaining_label = cleanse.aliased_column_label("remaining_amount")

    required_column_mapping = {
        "asset_code": col_asset,
        "custody_asset_code": col_custody,
        "data_date": col_data,
        "initial_transfer_amount": col_initial,
        "repaid_amount": col_repaid,
        "remaining_amount": col_remaining,
        "last_renovation_payment_date": col_last_renovation,
        **opt_cols,
    }

    missing = [label for label, col in [
        ("统计日期", col_data), ("初始受让金额", col_initial),
        ("已还款金额", col_repaid), (remaining_label, col_remaining),
    ] if col is None]
    if missing:
        return MonitorParseResult(
            rows=[], errors=[f"缺少列: {', '.join(missing)}"], batch_date=None,
            raw_row_count=raw_row_count, parsed_row_count=0,
            skipped_row_count=raw_row_count,
            skipped_reason_summary={"missing_columns": raw_row_count},
            detected_columns=detected_columns,
            required_column_mapping=required_column_mapping,
        )
    if not col_custody and not col_asset:
        return MonitorParseResult(
            rows=[], errors=["缺少托管房源编码或资产编号(房源)列"], batch_date=None,
            raw_row_count=raw_row_count, parsed_row_count=0,
            skipped_row_count=raw_row_count,
            skipped_reason_summary={"missing_asset_columns": raw_row_count},
            detected_columns=detected_columns,
            required_column_mapping=required_column_mapping,
        )

    skipped_reason_summary: dict[str, int] = {}
    errors: list[str] = []
    warnings: list[str] = []
    if col_last_renovation is None:
        warnings.append("可选列「最后一期装修款付款时间」缺失，将不写入 last_renovation_payment_date")
    row_dates: list[date] = []
    candidate_rows: list[dict] = []

    def _skip(reason: str) -> None:
        skipped_reason_summary[reason] = skipped_reason_summary.get(reason, 0) + 1

    for idx, row in df.iterrows():
        asset_code, custody, source = _resolve_monitor_asset_fields(row, col_asset, col_custody)
        if not asset_code and not custody:
            _skip("no_asset_identifier")
            continue
        row_date = cleanse.to_date_value(row[col_data])
        if row_date:
            row_dates.append(row_date)
        initial = cleanse.to_numeric_value(row[col_initial])
        repaid = cleanse.to_numeric_value(row[col_repaid])
        remaining = cleanse.to_numeric_value(row[col_remaining])
        if initial is None or repaid is None or remaining is None:
            _skip("invalid_amount")
            errors.append(f"行{idx + 2}: 金额字段无效")
            continue
        last_renovation_payment_date = None
        if col_last_renovation:
            last_renovation_payment_date = cleanse.to_date_value(row[col_last_renovation])
        candidate = {
            "asset_code": asset_code,
            "custody_asset_code": custody,
            "source_asset_code": source,
            "row_stat_date": row_date,
            "initial_transfer_amount": initial,
            "repaid_amount": repaid,
            "remaining_amount": remaining,
            "last_renovation_payment_date": last_renovation_payment_date,
        }
        for field in MONITOR_OPTIONAL_FIELDS:
            candidate[field] = _opt_field_from_row(
                row, opt_cols, field,
                as_amount=field in MONITOR_OPTIONAL_AMOUNT_FIELDS,
                as_date=field in MONITOR_OPTIONAL_DATE_FIELDS,
                as_rate=field in MONITOR_OPTIONAL_RATE_FIELDS,
            )
        candidate_rows.append(candidate)

    if not candidate_rows:
        return MonitorParseResult(
            rows=[], errors=errors or ["无有效监控行"], batch_date=None,
            raw_row_count=raw_row_count, parsed_row_count=0,
            skipped_row_count=sum(skipped_reason_summary.values()),
            skipped_reason_summary=skipped_reason_summary,
            detected_columns=detected_columns,
            required_column_mapping=required_column_mapping,
            warnings=warnings,
        )

    batch_date, batch_source, batch_warnings = _resolve_monitor_batch_date(
        row_dates,
        file_name=file_name,
        sheet_name=sheet_name,
        product_name=product_name,
    )
    warnings.extend(batch_warnings)
    if batch_date is None:
        return MonitorParseResult(
            rows=[], errors=errors or ["无法确定监控快照 data_date"], batch_date=None,
            raw_row_count=raw_row_count, parsed_row_count=0,
            skipped_row_count=sum(skipped_reason_summary.values()),
            skipped_reason_summary=skipped_reason_summary,
            detected_columns=detected_columns,
            required_column_mapping=required_column_mapping,
            warnings=warnings,
        )

    rows: list[dict] = []
    date_mismatch = 0
    for item in candidate_rows:
        row_stat = item.pop("row_stat_date", None)
        if row_stat and row_stat != batch_date:
            date_mismatch += 1
        rows.append({**item, "data_date": batch_date})

    if date_mismatch:
        warnings.append(
            f"{date_mismatch} 行 Excel 统计日期与快照日期 {batch_date} 不一致，"
            f"导入时将统一使用快照日期 {batch_date}"
        )

    return MonitorParseResult(
        rows=rows,
        errors=errors,
        batch_date=batch_date,
        raw_row_count=raw_row_count,
        parsed_row_count=len(rows),
        skipped_row_count=sum(skipped_reason_summary.values()),
        skipped_reason_summary=skipped_reason_summary,
        detected_columns=detected_columns,
        required_column_mapping=required_column_mapping,
        batch_date_source=batch_source,
        warnings=warnings,
    )


def precheck_repayment_sheet(
    conn: Connection,
    trust_product_id: int,
    product_name: str,
    file_name: str,
    sheet_name: str,
    df: pd.DataFrame,
) -> dict[str, Any]:
    mismatches = _excel_custody_source_mismatch_rows(df)
    parsed = assetinfo_date_rules.parse_sheet_repayment_date(sheet_name, product_name)
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
        "cross_file_overlap_count": 0,
    }

    if not trust_product_id:
        result["reason"] = "trust_product_id 缺失，无法预检还款明细"
        return _finalize_asset_code_mismatch_precheck(result, mismatches)

    file_err = _require_source_file_name(file_name)
    if file_err:
        result["reason"] = file_err.replace("导入", "预检")
        return _finalize_asset_code_mismatch_precheck(result, mismatches)

    sheet_err = _require_repayment_sheet_name(sheet_name)
    if sheet_err:
        result["reason"] = sheet_err.replace("导入", "预检")
        return _finalize_asset_code_mismatch_precheck(result, mismatches)

    if not parsed.ok:
        result["reason"] = parsed.error or "Sheet 日期解析失败"
        return _finalize_asset_code_mismatch_precheck(result, mismatches)

    rows, parse_errors = _parse_repayment_rows(df, sheet_fallback)
    if parse_errors:
        result["warnings"].extend(parse_errors[:20])
    if not rows:
        result["reason"] = "无有效数据行" + (f"; {parse_errors[0]}" if parse_errors else "")
        return _finalize_asset_code_mismatch_precheck(result, mismatches)

    result["warnings"].extend(_repayment_period_no_warnings(df, rows))

    status, msg, dup_warnings = _check_within_sheet_row_duplicates(rows)
    result["warnings"].extend(dup_warnings[:20])
    if status == "reject":
        result["action"] = "reject"
        result["reason"] = msg
        return _finalize_asset_code_mismatch_precheck(result, mismatches)

    amount_sum = sum(r["actual_repayment_amount"] for r in rows)
    result["row_count"] = len(rows)
    result["amount_sum"] = amount_sum

    db_cnt, db_sum = _batch_repayment_stats(conn, trust_product_id, file_name, sheet_name)
    result["db_row_count"] = db_cnt
    result["db_amount_sum"] = db_sum
    result["exists"] = db_cnt > 0

    cross_overlap = _cross_file_repayment_overlap_count(
        conn, trust_product_id, file_name, rows,
    )
    result["cross_file_overlap_count"] = cross_overlap

    if cross_overlap > 0:
        result["action"] = "needs_confirm"
        result["importable"] = True
        result["reason"] = (
            f"跨文件疑似重复 {cross_overlap} 条<br>"
            f"其他 source_file_name 中已存在相同付款实质<br><br>"
            f"确认导入后将仅覆盖当前文件+Sheet：<br>"
            f"{file_name} / {sheet_name}<br>"
            f"不会删除其他文件数据"
        )
        return _finalize_asset_code_mismatch_precheck(result, mismatches)

    if db_cnt > 0:
        if db_cnt == len(rows) and cleanse.amounts_equal(db_sum, amount_sum):
            result["action"] = "skip"
            result["importable"] = False
            result["reason"] = "该 Sheet 已存在且数据一致"
            return _finalize_asset_code_mismatch_precheck(result, mismatches)
        result["action"] = "overwrite"
        result["importable"] = True
        result["reason"] = (
            f"该 Sheet 已存在（DB {db_cnt} 条），将删除旧记录并重新导入 {len(rows)} 条"
        )
        return _finalize_asset_code_mismatch_precheck(result, mismatches)

    result["action"] = "import"
    result["importable"] = True
    result["reason"] = "可导入（合法多笔还款）" if dup_warnings else "可导入"
    return _finalize_asset_code_mismatch_precheck(result, mismatches)


def precheck_monitor_sheet(
    conn: Connection,
    trust_product_id: int,
    product_name: str,
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
        "raw_row_count": 0,
        "parsed_row_count": 0,
        "skipped_row_count": 0,
        "skipped_reason_summary": {},
        "detected_columns": [],
        "required_column_mapping": {},
        "amount_sum": None,
        "exists": False,
        "importable": False,
        "action": "failed",
        "reason": "",
        "warnings": [],
        "db_row_count": 0,
        "latest_snapshot_date": None,
        "latest_snapshot_row_count": 0,
        "unknown_asset_code_count": 0,
    }

    if not trust_product_id:
        result["reason"] = "trust_product_id 缺失，无法预检资产监控快照"
        return result

    sheet_err = _require_monitor_sheet_name(sheet_name)
    if sheet_err:
        result["reason"] = sheet_err.replace("覆盖", "预检")
        return result

    parsed = _parse_monitor_rows(
        df, file_name=file_name, sheet_name=sheet_name, product_name=product_name,
    )
    result["raw_row_count"] = parsed.raw_row_count
    result["parsed_row_count"] = parsed.parsed_row_count
    result["skipped_row_count"] = parsed.skipped_row_count
    result["skipped_reason_summary"] = parsed.skipped_reason_summary
    result["detected_columns"] = parsed.detected_columns
    result["required_column_mapping"] = parsed.required_column_mapping
    if parsed.batch_date_source:
        result["date_rule_label"] = parsed.batch_date_source
    if parsed.warnings:
        result["warnings"].extend(parsed.warnings)
    if parsed.errors:
        result["warnings"].extend(parsed.errors[:20])

    batch_date = parsed.batch_date
    rows = parsed.rows
    if not batch_date:
        result["reason"] = "data_date（统计日期）无法解析，无法预检资产监控快照"
        return result
    if not rows:
        result["reason"] = "无有效行"
        return result

    result["warnings"].extend(_check_monitor_within_sheet_multi_rows(rows))

    result["parsed_date"] = str(batch_date)
    excel_rows = len(rows)
    result["row_count"] = excel_rows
    result["parsed_row_count"] = excel_rows

    sheet_db_cnt = _batch_monitor_count(conn, trust_product_id, batch_date, sheet_name)
    result["db_row_count"] = sheet_db_cnt
    result["exists"] = sheet_db_cnt > 0

    latest_date, latest_total, latest_codes = _fetch_monitor_latest_snapshot(
        conn, trust_product_id,
    )
    excel_codes = {str(r["asset_code"]) for r in rows if r.get("asset_code")}
    result["latest_snapshot_date"] = str(latest_date) if latest_date else None
    result["latest_snapshot_row_count"] = latest_total
    result["unknown_asset_code_count"] = (
        len(excel_codes - latest_codes) if latest_date else len(excel_codes)
    )

    dup_checks = fetch_monitor_batch_duplicate_checks(
        conn, trust_product_id, str(batch_date), sheet_name,
    )
    for item in dup_checks[:10]:
        if item["check_type"] == "duplicate_batch_trust_asset_id":
            result["warnings"].append(
                f"数据质量：同 Sheet 内 trust_asset_id={item['trust_asset_id']} 存在 "
                f"{item['row_count']} 行重复批次记录"
            )

    confirm_reasons = _monitor_precheck_confirm_reasons(
        latest_date=latest_date,
        latest_total=latest_total,
        latest_codes=latest_codes,
        excel_rows=excel_rows,
        excel_codes=excel_codes,
        sheet_db_cnt=sheet_db_cnt,
    )
    if confirm_reasons:
        _apply_monitor_confirm_precheck(result, confirm_reasons)
        return result

    if sheet_db_cnt == 0:
        result["action"] = "import"
        result["importable"] = True
        result["reason"] = "可导入"
        return result

    if sheet_db_cnt == excel_rows:
        result["action"] = "overwrite"
        result["importable"] = True
        result["reason"] = "记录数一致，允许覆盖更新"
        return result

    _apply_monitor_confirm_precheck(
        result,
        [
            f"同 Sheet 已有 {sheet_db_cnt} 条，本次 {excel_rows} 条，条数不一致。"
        ],
    )
    return result


def recompute_monitor_payment_fields(
    conn: Connection,
    trust_product_id: int,
    data_date: date,
) -> list[str]:
    """重算 last_payment_date / overdue_days；返回数据质量警告."""
    warnings: list[str] = []
    params = {
        "pid": trust_product_id,
        "dd": data_date,
        "tolerance": RECONCILIATION_TOLERANCE,
    }

    conn.execute(
        text("""
            UPDATE trust_asset_monitor_records m
            SET
                last_payment_date = sub.max_rd,
                max_payment_date = sub.max_rd,
                overdue_days = CASE
                    WHEN m.remaining_amount <= :tolerance THEN NULL
                    ELSE (CAST(:dd AS date) - (sub.max_rd + INTERVAL '1 month')::date)
                END
            FROM (
                SELECT r.trust_product_id, ta.asset_code, MAX(r.repayment_date) AS max_rd
                FROM trust_repayment_detail_records r
                INNER JOIN trust_assets ta ON ta.id = r.trust_asset_id
                WHERE r.trust_product_id = :pid
                GROUP BY r.trust_product_id, ta.asset_code
            ) sub
            WHERE m.trust_product_id = :pid
              AND m.data_date = :dd
              AND m.asset_code = sub.asset_code
        """),
        params,
    )

    conn.execute(
        text("""
            UPDATE trust_asset_monitor_records m
            SET
                last_payment_date = NULL,
                max_payment_date = NULL,
                overdue_days = CASE
                    WHEN m.remaining_amount <= :tolerance THEN NULL
                    ELSE (CAST(:dd AS date) - (iss.min_issue_date + INTERVAL '1 month')::date)
                END
            FROM (
                SELECT
                    m2.id AS monitor_id,
                    COALESCE(ip.min_issue_date, ia.min_issue_date) AS min_issue_date
                FROM trust_asset_monitor_records m2
                LEFT JOIN (
                    SELECT
                        i.trust_product_id,
                        regexp_replace(COALESCE(i.custody_asset_code, ''), '\\.0$', '') AS custody_norm,
                        MIN(i.issue_date) AS min_issue_date
                    FROM trust_product_issuance_asset_records i
                    WHERE i.trust_product_id = :pid
                    GROUP BY i.trust_product_id, custody_norm
                ) ip
                  ON ip.trust_product_id = m2.trust_product_id
                 AND ip.custody_norm = regexp_replace(
                     COALESCE(m2.custody_asset_code, m2.asset_code, ''), '\\.0$', ''
                 )
                LEFT JOIN (
                    SELECT
                        regexp_replace(COALESCE(i.custody_asset_code, ''), '\\.0$', '') AS custody_norm,
                        MIN(i.issue_date) AS min_issue_date
                    FROM trust_product_issuance_asset_records i
                    GROUP BY custody_norm
                ) ia
                  ON ia.custody_norm = regexp_replace(
                      COALESCE(m2.custody_asset_code, m2.asset_code, ''), '\\.0$', ''
                  )
                WHERE m2.trust_product_id = :pid
                  AND m2.data_date = :dd
                  AND COALESCE(ip.min_issue_date, ia.min_issue_date) IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM trust_repayment_detail_records r
                      INNER JOIN trust_assets ta ON ta.id = r.trust_asset_id
                      WHERE r.trust_product_id = :pid
                        AND ta.asset_code = m2.asset_code
                  )
            ) iss
            WHERE m.id = iss.monitor_id
        """),
        params,
    )

    missing_rows = conn.execute(
        text("""
            SELECT m.asset_code FROM trust_asset_monitor_records m
            WHERE m.trust_product_id = :pid AND m.data_date = :dd
              AND m.remaining_amount > :tolerance
              AND NOT EXISTS (
                  SELECT 1
                  FROM trust_repayment_detail_records r
                  INNER JOIN trust_assets ta ON ta.id = r.trust_asset_id
                  WHERE r.trust_product_id = :pid
                    AND ta.asset_code = m.asset_code
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM trust_product_issuance_asset_records i
                  WHERE regexp_replace(COALESCE(i.custody_asset_code, ''), '\\.0$', '')
                      = regexp_replace(
                          COALESCE(m.custody_asset_code, m.asset_code, ''), '\\.0$', ''
                      )
              )
        """),
        params,
    )
    for r in missing_rows:
        warnings.append(f"{r.asset_code}: 无还款明细且无发行日，无法计算逾期天数")

    conn.execute(
        text("""
            UPDATE trust_asset_monitor_records m
            SET last_payment_date = NULL, max_payment_date = NULL, overdue_days = NULL
            WHERE m.trust_product_id = :pid AND m.data_date = :dd
              AND NOT EXISTS (
                  SELECT 1
                  FROM trust_repayment_detail_records r
                  INNER JOIN trust_assets ta ON ta.id = r.trust_asset_id
                  WHERE r.trust_product_id = :pid
                    AND ta.asset_code = m.asset_code
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM trust_product_issuance_asset_records i
                  WHERE regexp_replace(COALESCE(i.custody_asset_code, ''), '\\.0$', '')
                      = regexp_replace(
                          COALESCE(m.custody_asset_code, m.asset_code, ''), '\\.0$', ''
                      )
              )
        """),
        params,
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
    if not trust_product_id:
        raise HTTPException(status_code=400, detail="trust_product_id 缺失，无法导入还款明细")

    file_err = _require_source_file_name(file_name)
    if file_err:
        raise HTTPException(status_code=400, detail=file_err)

    sheet_err = _require_repayment_sheet_name(sheet_name)
    if sheet_err:
        raise HTTPException(status_code=400, detail=sheet_err)

    parsed = assetinfo_date_rules.parse_sheet_repayment_date(sheet_name, product_name)
    if not parsed.ok or not parsed.parsed_date:
        raise HTTPException(status_code=400, detail=parsed.error or "日期解析失败")

    rows, parse_errors = _parse_repayment_rows(df, parsed.parsed_date)
    if not rows:
        return 0, 0, "无有效行"

    _delete_repayment_sheet_scope(conn, trust_product_id, file_name, sheet_name)

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
            distinct_custody=True,
        )
        upsert_count += 1
        conn.execute(
            text("""
                INSERT INTO trust_repayment_detail_records (
                    trust_product_id, trust_asset_id, asset_code,
                    custody_asset_code, source_asset_code,
                    data_date, period_no, actual_repayment_amount, repayment_date,
                    asset_pool_code, current_payer, planned_repayment_amount,
                    initial_renovation_amount, cumulative_repaid_amount, remaining_balance,
                    source_file_name, source_sheet_name, synced_at
                ) VALUES (
                    :pid, :aid, :ac, :custody, :source,
                    :dd, :pn, :amt, :rd,
                    :asset_pool_code, :current_payer, :planned_repayment_amount,
                    :initial_renovation_amount, :cumulative_repaid_amount, :remaining_balance,
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
                "asset_pool_code": r.get("asset_pool_code"),
                "current_payer": r.get("current_payer"),
                "planned_repayment_amount": r.get("planned_repayment_amount"),
                "initial_renovation_amount": r.get("initial_renovation_amount"),
                "cumulative_repaid_amount": r.get("cumulative_repaid_amount"),
                "remaining_balance": r.get("remaining_balance"),
                "file": file_name,
                "sheet": sheet_name,
                "synced": synced_at,
            },
        )
        inserted += 1
    msg = "imported"
    if parse_errors:
        msg = f"imported（{len(parse_errors)} 行解析警告）"
    return inserted, upsert_count, msg


def _import_monitor_sheet(
    conn: Connection,
    trust_product_id: int,
    product_name: str,
    file_name: str,
    sheet_name: str,
    df: pd.DataFrame,
    synced_at: datetime,
) -> tuple[int, int, str, date | None, list[str]]:
    sheet_err = _require_monitor_sheet_name(sheet_name)
    if sheet_err:
        return 0, 0, sheet_err, None, []

    if not trust_product_id:
        return 0, 0, "trust_product_id 缺失，无法导入资产监控快照", None, []

    parsed = _parse_monitor_rows(
        df, file_name=file_name, sheet_name=sheet_name, product_name=product_name,
    )
    batch_date = parsed.batch_date
    rows = parsed.rows
    if not batch_date:
        return 0, 0, "data_date（统计日期）无法解析，无法导入资产监控快照", None, parsed.errors[:20]
    if not rows:
        return 0, 0, "无有效行", None, parsed.errors[:20]

    quality_warnings = list(parsed.errors[:20])
    if parsed.warnings:
        quality_warnings.extend(parsed.warnings)
    quality_warnings.extend(_check_monitor_within_sheet_multi_rows(rows))

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
            distinct_custody=True,
        )
        upsert_count += 1
        conn.execute(
            text("""
                INSERT INTO trust_asset_monitor_records (
                    trust_product_id, trust_asset_id, asset_code,
                    custody_asset_code, source_asset_code,
                    data_date, initial_transfer_amount, repaid_amount, remaining_amount,
                    last_renovation_payment_date,
                    asset_pool_code, renovation_vendor, asset_status, community_name, city,
                    collection_contract_code, custody_agreement_sign_date,
                    collection_contract_years, owner_code, withholding_ratio, actual_monthly_rent,
                    overdue_days, last_payment_date, max_payment_date,
                    source_file_name, source_sheet_name, synced_at
                ) VALUES (
                    :pid, :aid, :ac, :custody, :source,
                    :dd, :initial, :repaid, :remaining,
                    :last_renovation,
                    :asset_pool_code, :renovation_vendor, :asset_status, :community_name, :city,
                    :collection_contract_code, :custody_agreement_sign_date,
                    :collection_contract_years, :owner_code, :withholding_ratio, :actual_monthly_rent,
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
                "last_renovation": r.get("last_renovation_payment_date"),
                "asset_pool_code": r.get("asset_pool_code"),
                "renovation_vendor": r.get("renovation_vendor"),
                "asset_status": r.get("asset_status"),
                "community_name": r.get("community_name"),
                "city": r.get("city"),
                "collection_contract_code": r.get("collection_contract_code"),
                "custody_agreement_sign_date": r.get("custody_agreement_sign_date"),
                "collection_contract_years": r.get("collection_contract_years"),
                "owner_code": r.get("owner_code"),
                "withholding_ratio": r.get("withholding_ratio"),
                "actual_monthly_rent": r.get("actual_monthly_rent"),
                "file": file_name,
                "sheet": sheet_name,
                "synced": synced_at,
            },
        )
        inserted += 1

    quality_warnings.extend(recompute_monitor_payment_fields(conn, trust_product_id, batch_date))
    dup_checks = fetch_monitor_batch_duplicate_checks(
        conn, trust_product_id, str(batch_date), sheet_name,
    )
    for item in dup_checks[:5]:
        if item["check_type"] == "duplicate_batch_trust_asset_id":
            quality_warnings.append(
                f"重复批次检查：trust_asset_id={item['trust_asset_id']} 在同 Sheet 内有 "
                f"{item['row_count']} 行"
            )
    return inserted, upsert_count, "imported", batch_date, quality_warnings


def _parse_repayment_plan_rows(df: pd.DataFrame) -> tuple[list[dict], list[str]]:
    col_asset = cleanse.pick_column(df, *COL_ASSET_CODE)
    col_custody = cleanse.pick_column(df, *COL_CUSTODY)
    if not col_asset and not col_custody:
        return [], ["缺少资产编号(房源)或托管房源编码列"]

    field_keys = (
        "asset_pool_code", "renovation_vendor", "data_date",
        "initial_transfer_amount", "repaid_amount", "remaining_amount",
        "community_name", "city", "current_bill_date", "repayment_amount_detail",
        "planned_monthly_repayment_amount", "final_planned_repayment_amount",
    )
    opt_cols = _build_optional_col_map(df, field_keys)
    # remaining_amount on plan sheet uses 剩余还款金额
    if opt_cols.get("remaining_amount") is None:
        opt_cols["remaining_amount"] = cleanse.pick_aliased_column(df, "remaining_amount")
    if opt_cols.get("data_date") is None:
        opt_cols["data_date"] = cleanse.pick_column(df, *COL_DATA_DATE)
    if opt_cols.get("initial_transfer_amount") is None:
        opt_cols["initial_transfer_amount"] = cleanse.pick_column(df, *COL_INITIAL)
    if opt_cols.get("repaid_amount") is None:
        opt_cols["repaid_amount"] = cleanse.pick_column(df, *COL_REPAID)

    amount_fields = {
        "initial_transfer_amount", "repaid_amount", "remaining_amount",
        "planned_monthly_repayment_amount", "final_planned_repayment_amount",
    }
    date_fields = {"data_date", "current_bill_date"}

    rows: list[dict] = []
    errors: list[str] = []
    for idx, row in df.iterrows():
        asset_code, custody, source = _resolve_monitor_asset_fields(row, col_asset, col_custody)
        if not asset_code and not custody:
            continue
        if not asset_code:
            asset_code = custody or source or ""
        parsed = {
            "asset_code": asset_code,
            "custody_asset_code": custody,
            "source_asset_code": source,
            "source_row_number": int(idx) + 2,
        }
        for field in field_keys:
            parsed[field] = _opt_field_from_row(
                row, opt_cols, field,
                as_amount=field in amount_fields,
                as_date=field in date_fields,
            )
        rows.append(parsed)
    if not rows and not errors:
        errors.append("无有效回款计划行")
    return rows, errors


def precheck_repayment_plan_sheet(
    conn: Connection,
    trust_product_id: int,
    product_name: str,
    file_name: str,
    sheet_name: str,
    df: pd.DataFrame,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "file_name": file_name,
        "sheet_name": sheet_name,
        "sheet_type": "repayment_plan",
        "row_count": 0,
        "amount_sum": 0.0,
        "exists": False,
        "importable": False,
        "action": "failed",
        "reason": "",
        "warnings": [],
        "db_row_count": 0,
    }
    if not trust_product_id:
        result["reason"] = "trust_product_id 缺失，无法预检回款计划"
        return result
    rows, errors = _parse_repayment_plan_rows(df)
    if errors and not rows:
        result["reason"] = errors[0]
        return result
    result["row_count"] = len(rows)
    result["warnings"] = errors[:20]
    existing = conn.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM trust_repayment_plan_records
            WHERE trust_product_id = :pid
              AND source_file_name = :file
              AND source_sheet_name = :sheet
        """),
        {"pid": trust_product_id, "file": file_name, "sheet": sheet_name},
    ).fetchone()
    db_count = int(existing.cnt or 0)
    result["db_row_count"] = db_count
    result["exists"] = db_count > 0
    result["importable"] = True
    if db_count > 0:
        result["action"] = "overwrite"
        result["reason"] = f"将覆盖当前来源 {file_name} / {sheet_name} 的 {db_count} 行旧数据"
    else:
        result["action"] = "import"
        result["reason"] = "可导入"
    return result


def _import_repayment_plan_sheet(
    conn: Connection,
    trust_product_id: int,
    product_name: str,
    file_name: str,
    sheet_name: str,
    df: pd.DataFrame,
    synced_at: datetime,
) -> tuple[int, int, str]:
    if not trust_product_id:
        raise HTTPException(status_code=400, detail="trust_product_id 缺失，无法导入回款计划")
    rows, parse_errors = _parse_repayment_plan_rows(df)
    if not rows:
        return 0, 0, parse_errors[0] if parse_errors else "无有效行"

    conn.execute(
        text("""
            DELETE FROM trust_repayment_plan_records
            WHERE trust_product_id = :pid
              AND source_file_name = :file
              AND source_sheet_name = :sheet
        """),
        {"pid": trust_product_id, "file": file_name, "sheet": sheet_name},
    )

    upsert_count = 0
    inserted = 0
    for r in rows:
        asset_id = _upsert_trust_asset(
            conn,
            trust_product_id,
            r["asset_code"],
            r.get("custody_asset_code"),
            float(r["initial_transfer_amount"] or 0),
            r.get("source_asset_code"),
            distinct_custody=True,
        )
        upsert_count += 1
        conn.execute(
            text("""
                INSERT INTO trust_repayment_plan_records (
                    trust_product_id, trust_asset_id, asset_code,
                    custody_asset_code, source_asset_code,
                    asset_pool_code, renovation_vendor, data_date,
                    initial_transfer_amount, repaid_amount, remaining_amount,
                    community_name, city, current_bill_date, repayment_amount_detail,
                    planned_monthly_repayment_amount, final_planned_repayment_amount,
                    source_file_name, source_sheet_name, source_row_number, synced_at
                ) VALUES (
                    :pid, :aid, :ac, :custody, :source,
                    :asset_pool_code, :renovation_vendor, :data_date,
                    :initial_transfer_amount, :repaid_amount, :remaining_amount,
                    :community_name, :city, :current_bill_date, :repayment_amount_detail,
                    :planned_monthly_repayment_amount, :final_planned_repayment_amount,
                    :file, :sheet, :source_row_number, :synced
                )
            """),
            {
                "pid": trust_product_id,
                "aid": asset_id,
                "ac": r["asset_code"],
                "custody": r.get("custody_asset_code"),
                "source": r.get("source_asset_code"),
                "asset_pool_code": r.get("asset_pool_code"),
                "renovation_vendor": r.get("renovation_vendor"),
                "data_date": r.get("data_date"),
                "initial_transfer_amount": r.get("initial_transfer_amount"),
                "repaid_amount": r.get("repaid_amount"),
                "remaining_amount": r.get("remaining_amount"),
                "community_name": r.get("community_name"),
                "city": r.get("city"),
                "current_bill_date": r.get("current_bill_date"),
                "repayment_amount_detail": r.get("repayment_amount_detail"),
                "planned_monthly_repayment_amount": r.get("planned_monthly_repayment_amount"),
                "final_planned_repayment_amount": r.get("final_planned_repayment_amount"),
                "file": file_name,
                "sheet": sheet_name,
                "source_row_number": r.get("source_row_number"),
                "synced": synced_at,
            },
        )
        inserted += 1
    msg = "imported"
    if parse_errors:
        msg = f"imported（{len(parse_errors)} 行解析警告）"
    return inserted, upsert_count, msg


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
                    conn, trust_product_id, product_name, file_name, sheet_name, df,
                ))
            elif st == "repayment_plan":
                sheets.append(precheck_repayment_plan_sheet(
                    conn, trust_product_id, product_name, file_name, sheet_name, df,
                ))

    payload = {
        "file_id": batch_uuid,
        "batch_uuid": batch_uuid,
        "trust_product_id": trust_product_id,
        "product_name": product_name,
        "trust_product_name": product_name,
        "files": file_names,
        "sheets": [enrich_preview_sheet(s, batch_uuid) for s in sheets],
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
    selected_sheet_keys: list[str] | None = None,
    selected_sheets: list[str] | None = None,
    confirm_sheet_keys: list[str] | None = None,
) -> dict[str, Any]:
    preview_path = preview_json_path(batch_uuid)
    if not preview_path.exists():
        raise HTTPException(status_code=400, detail="预检结果不存在，请先 preview")

    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    if int(preview["trust_product_id"]) != trust_product_id:
        raise HTTPException(status_code=400, detail="trust_product_id 与预检不一致")

    product_name = preview["product_name"]
    selected = resolve_selected_sheet_keys(preview, selected_sheet_keys, selected_sheets)
    confirm_set = set(confirm_sheet_keys or [])
    validate_selected_sheets(preview, selected, confirm_set)
    synced_at = datetime.now(timezone.utc)

    inserted_monitor = 0
    inserted_repayment = 0
    inserted_repayment_plan = 0
    upsert_assets = 0
    skipped = 0
    failed = 0
    not_selected = 0
    sheet_results: list[dict] = []
    monitor_dates: list[date] = []
    quality_warnings: list[str] = []
    risk_recalc_hint = False

    for sheet in preview["sheets"]:
        action = sheet.get("action")
        key = sheet_key(sheet["file_name"], sheet["sheet_name"])
        file_name = sheet["file_name"]
        sheet_name = sheet["sheet_name"]

        if key not in selected:
            not_selected += 1
            sheet_results.append({**sheet, "final_action": "not_selected"})
            continue

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

        savepoint = conn.begin_nested()
        try:
            if sheet["sheet_type"] == "repayment_detail":
                ins, ups, msg = _import_repayment_sheet(
                    conn, trust_product_id, product_name, file_name, sheet_name, df, synced_at,
                )
                inserted_repayment += ins
                upsert_assets += ups
                replaced = action in ("overwrite", "needs_confirm") and sheet.get("db_row_count", 0) > 0
                sheet_results.append({
                    **sheet,
                    "final_action": "overwritten" if replaced else "imported",
                    "inserted": ins,
                })
            elif sheet["sheet_type"] == "repayment_plan":
                ins, ups, msg = _import_repayment_plan_sheet(
                    conn, trust_product_id, product_name, file_name, sheet_name, df, synced_at,
                )
                inserted_repayment_plan += ins
                upsert_assets += ups
                replaced = action in ("overwrite", "needs_confirm") and sheet.get("db_row_count", 0) > 0
                sheet_results.append({
                    **sheet,
                    "final_action": "overwritten" if replaced else "imported",
                    "inserted": ins,
                })
            elif sheet["sheet_type"] == "asset_monitor":
                ins, ups, msg, batch_date, warns = _import_monitor_sheet(
                    conn, trust_product_id, product_name, file_name, sheet_name, df, synced_at,
                )
                inserted_monitor += ins
                upsert_assets += ups
                quality_warnings.extend(warns)
                if batch_date:
                    monitor_dates.append(batch_date)
                if action == "overwrite" or (
                    action == "needs_confirm" and sheet.get("db_row_count", 0) > 0
                ):
                    risk_recalc_hint = True
                replaced = action == "overwrite" or (
                    action == "needs_confirm" and sheet.get("db_row_count", 0) > 0
                )
                sheet_results.append({
                    **sheet,
                    "final_action": "overwritten" if replaced else "imported",
                    "inserted": ins,
                    "quality_warnings": warns,
                })
            else:
                failed += 1
                sheet_results.append({**sheet, "final_action": "failed"})
            savepoint.commit()
        except Exception as exc:
            savepoint.rollback()
            failed += 1
            sheet_results.append({**sheet, "final_action": "failed", "reason": str(exc)})

    pipeline_data_date = monitor_dates[0] if monitor_dates else None
    source_files = ", ".join(preview.get("files", []))
    error_message = None
    if failed:
        error_message = f"{failed} 个 Sheet 导入失败"

    run_id, created_at = record_assetinfo_run(
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
        "inserted_repayment_plan_count": inserted_repayment_plan,
        "upsert_asset_count": upsert_assets,
        "skipped_sheet_count": skipped,
        "not_selected_sheet_count": not_selected,
        "failed_sheet_count": failed,
        "selected_sheet_count": len(selected),
        "sheet_results": sheet_results,
        "quality_warnings": quality_warnings,
    }
    if risk_recalc_hint:
        result["risk_recalc_hint"] = "监控快照已覆盖，请手动重新计算风险评分（POST /risk/score/recalculate）"
    return result


def _monitor_snapshot_view_mode(filters: dict[str, Any]) -> str:
    if filters.get("include_history"):
        return "history"
    if filters.get("data_date"):
        return "fixed_date"
    return "latest_effective"


def _monitor_latest_snapshot_join_sql() -> str:
    """每个 (trust_product_id, trust_asset_id) 仅保留 MAX(data_date) 记录。"""
    return """
        INNER JOIN (
            SELECT trust_product_id, trust_asset_id, MAX(data_date) AS data_date
            FROM trust_asset_monitor_records
            GROUP BY trust_product_id, trust_asset_id
        ) latest_snap
            ON latest_snap.trust_product_id = r.trust_product_id
           AND latest_snap.trust_asset_id = r.trust_asset_id
           AND latest_snap.data_date = r.data_date
    """


def _monitor_custody_norm_match_sql(left_expr: str, right_expr: str) -> str:
    return (
        f"regexp_replace(COALESCE({left_expr}, ''), '\\.0$', '')"
        f" = regexp_replace(COALESCE({right_expr}, ''), '\\.0$', '')"
    )


def _monitor_transferred_in_exists_sql() -> str:
    """已转让=是：监控行在转入方，且存在从 trust_product_id 转出的发行记录。"""
    custody_match = _monitor_custody_norm_match_sql(
        "i.custody_asset_code",
        "COALESCE(r.custody_asset_code, r.asset_code, '')",
    )
    return f"""
        EXISTS (
            SELECT 1
            FROM trust_product_issuance_asset_records i
            WHERE i.migration_type = 'transfer'
              AND i.from_trust_product_id = :trust_product_id
              AND i.trust_product_id = r.trust_product_id
              AND {custody_match}
        )
    """


def _monitor_issuance_lateral_join_sql() -> str:
    return """
        LEFT JOIN LATERAL (
            SELECT i.asset_transfer_discount_rate, i.city
            FROM trust_product_issuance_asset_records i
            WHERE i.trust_product_id = r.trust_product_id
              AND (
                  i.custody_asset_code = r.custody_asset_code
                  OR split_part(i.custody_asset_code, '-', 1) = r.asset_code
              )
            ORDER BY i.issue_date DESC NULLS LAST, i.id DESC
            LIMIT 1
        ) iss ON TRUE
    """


def _append_monitor_issuance_filters(
    where_parts: list[str],
    params: dict[str, Any],
    filters: dict[str, Any],
) -> None:
    rate_filter = filters.get("asset_transfer_discount_rate")
    if rate_filter == MONITOR_DISCOUNT_RATE_NONE:
        where_parts.append("iss.asset_transfer_discount_rate IS NULL")
    elif rate_filter is not None:
        where_parts.append(
            "ABS(iss.asset_transfer_discount_rate - :asset_transfer_discount_rate) < 1e-6"
        )
        params["asset_transfer_discount_rate"] = float(rate_filter)

    city_filter = filters.get("city")
    if city_filter == ISSUANCE_CITY_UNKNOWN:
        where_parts.append("(NULLIF(TRIM(r.city), '') IS NULL)")
    elif city_filter:
        where_parts.append("NULLIF(TRIM(r.city), '') = :city")
        params["city"] = city_filter


def _build_monitor_record_query(
    filters: dict[str, Any],
) -> tuple[str, dict[str, Any], str, str, str, str]:
    """返回 where_sql, params, snapshot_join, issuance_join, order_by_sql, select_extra."""
    where_parts = ["1=1"]
    params: dict[str, Any] = {}
    transferred = filters.get("transferred")

    for key in (
        "trust_product_id", "data_date", "asset_code",
        "custody_asset_code", "source_asset_code",
        "source_file_name", "source_sheet_name",
    ):
        _append_assetinfo_record_filter(
            where_parts,
            params,
            key,
            filters.get(key),
            skip_trust_product_where=(
                key == "trust_product_id" and transferred == "yes"
            ),
        )

    snapshot_join = ""
    if _monitor_snapshot_view_mode(filters) == "latest_effective":
        snapshot_join = _monitor_latest_snapshot_join_sql()

    issuance_join = _monitor_issuance_lateral_join_sql()
    _append_monitor_issuance_filters(where_parts, params, filters)

    if transferred in ("yes", "no"):
        if transferred == "yes":
            where_parts.append(_monitor_transferred_in_exists_sql())
        else:
            where_parts.append(f"NOT ({_monitor_transferred_out_exists_sql()})")

    where_sql = " AND ".join(where_parts)
    order_by_sql = build_monitor_order_by(
        filters.get("sort_by"),
        filters.get("sort_dir"),
    )
    # 城市只展示监控表 Excel 导入值，不再 COALESCE 发行城市（避免 city_resolved 重复列）
    select_extra = ", iss.asset_transfer_discount_rate"
    return where_sql, params, snapshot_join, issuance_join, order_by_sql, select_extra


MONITOR_ROW_FLOAT_KEYS = frozenset({
    "initial_transfer_amount",
    "repaid_amount",
    "remaining_amount",
    "asset_transfer_discount_rate",
    "overdue_days",
    "risk_score",
    "withholding_ratio",
    "actual_monthly_rent",
    "collection_contract_years",
    "planned_repayment_amount",
    "initial_renovation_amount",
    "cumulative_repaid_amount",
    "remaining_balance",
})


def _normalize_monitor_row(row) -> dict[str, Any]:
    item = dict(row._mapping)
    item.pop("city_resolved", None)
    for k, v in item.items():
        if hasattr(v, "isoformat"):
            item[k] = str(v)
        elif isinstance(v, (int, float)) and v is not None and (
            k.endswith("amount") or k in MONITOR_ROW_FLOAT_KEYS
        ):
            item[k] = float(v)
    return item


def _format_monitor_export_cell(key: str, value) -> Any:
    if value is None or value == "":
        return "—"
    if key == "asset_transfer_discount_rate":
        return format_rate(value)
    if key == "withholding_ratio":
        try:
            return format_rate(value)
        except (TypeError, ValueError):
            return value
    if key in ("synced_at", "created_at") and isinstance(value, str):
        return value[:16].replace("T", " ") if len(value) >= 16 else value
    if key in (
        "data_date",
        "last_renovation_payment_date",
        "last_payment_date",
        "max_payment_date",
        "custody_agreement_sign_date",
        "current_bill_date",
        "repayment_date",
    ) and isinstance(value, str):
        return value[:10]
    if key == "city":
        text = str(value).strip()
        return text if text else "—"
    return value


def fetch_monitor_discount_rate_options(
    conn: Connection,
    trust_product_id: int | None = None,
) -> list[dict[str, str]]:
    sql = """
        SELECT DISTINCT asset_transfer_discount_rate AS rate
        FROM trust_product_issuance_asset_records
        WHERE asset_transfer_discount_rate IS NOT NULL
    """
    params: dict[str, Any] = {}
    if trust_product_id is not None:
        sql += " AND trust_product_id = :trust_product_id"
        params["trust_product_id"] = trust_product_id
    sql += " ORDER BY rate"
    rows = conn.execute(text(sql), params)
    return [
        {"value": str(float(row.rate)), "label": format_rate(row.rate)}
        for row in rows
    ]


def fetch_monitor_city_options(
    conn: Connection,
    trust_product_id: int | None = None,
) -> list[str]:
    """城市筛选项：仅监控表 Excel 导入的 city。"""
    params: dict[str, Any] = {"unknown": ISSUANCE_CITY_UNKNOWN}
    product_filter = ""
    if trust_product_id is not None:
        product_filter = " AND trust_product_id = :trust_product_id"
        params["trust_product_id"] = trust_product_id
    sql = f"""
        SELECT DISTINCT COALESCE(NULLIF(TRIM(city), ''), :unknown) AS city
        FROM trust_asset_monitor_records
        WHERE 1 = 1{product_filter}
        ORDER BY city
    """
    rows = conn.execute(text(sql), params)
    cities = [str(row.city) for row in rows]
    if ISSUANCE_CITY_UNKNOWN not in cities:
        cities.append(ISSUANCE_CITY_UNKNOWN)
    return cities


def fetch_monitor_records_for_export(
    conn: Connection,
    filters: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    where_sql, params, snapshot_join, issuance_join, order_by_sql, select_extra = (
        _build_monitor_record_query(filters)
    )
    count_row = conn.execute(
        text(f"""
            SELECT COUNT(*) AS cnt
            FROM trust_asset_monitor_records r
            JOIN trust_products tp ON tp.id = r.trust_product_id
            {snapshot_join}
            {issuance_join}
            WHERE {where_sql}
        """),
        params,
    ).fetchone()
    total = int(count_row.cnt)
    if total > MONITOR_EXPORT_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"结果超过 {MONITOR_EXPORT_MAX} 条，请缩小筛选范围",
        )
    rows = conn.execute(
        text(f"""
            SELECT r.*, tp.name AS trust_product_name{select_extra}
            FROM trust_asset_monitor_records r
            JOIN trust_products tp ON tp.id = r.trust_product_id
            {snapshot_join}
            {issuance_join}
            WHERE {where_sql}
            ORDER BY {order_by_sql}
        """),
        params,
    )
    return [_normalize_monitor_row(row) for row in rows], total


def build_monitor_export_xlsx(items: list[dict[str, Any]]) -> bytes:
    """按资产监控表模版列序导出."""
    headers = templates.template_headers(templates.MONITOR_TEMPLATE_COLUMNS)
    data_rows = [
        templates.row_values_for_template(
            item, templates.MONITOR_TEMPLATE_COLUMNS, format_cell=_format_monitor_export_cell,
        )
        for item in items
    ]
    df = pd.DataFrame(data_rows, columns=headers)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="资产监控表")
    return buffer.getvalue()


def fetch_repayment_records_for_export(
    conn: Connection,
    filters: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    where_parts = ["1=1"]
    params: dict[str, Any] = {}
    for key in (
        "trust_product_id", "data_date", "asset_code",
        "custody_asset_code", "source_asset_code",
        "source_file_name", "source_sheet_name",
    ):
        _append_assetinfo_record_filter(where_parts, params, key, filters.get(key))
    where_sql = " AND ".join(where_parts)

    count_row = conn.execute(
        text(f"""
            SELECT COUNT(*) AS cnt
            FROM trust_repayment_detail_records r
            JOIN trust_products tp ON tp.id = r.trust_product_id
            WHERE {where_sql}
        """),
        params,
    ).fetchone()
    total = int(count_row.cnt)
    if total > MONITOR_EXPORT_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"结果超过 {MONITOR_EXPORT_MAX} 条，请缩小筛选范围",
        )

    # 当期逾期天数：取同产品同托管号最新监控快照 overdue_days（不从还款 Excel 导入）
    rows = conn.execute(
        text(f"""
            SELECT r.*, tp.name AS trust_product_name,
                   mon.overdue_days AS overdue_days
            FROM trust_repayment_detail_records r
            JOIN trust_products tp ON tp.id = r.trust_product_id
            LEFT JOIN LATERAL (
                SELECT m.overdue_days
                FROM trust_asset_monitor_records m
                WHERE m.trust_product_id = r.trust_product_id
                  AND (
                      m.custody_asset_code = r.custody_asset_code
                      OR (
                          r.custody_asset_code IS NULL
                          AND m.asset_code = r.asset_code
                      )
                  )
                ORDER BY m.data_date DESC NULLS LAST, m.id DESC
                LIMIT 1
            ) mon ON TRUE
            WHERE {where_sql}
            ORDER BY r.repayment_date DESC NULLS LAST, r.id DESC
        """),
        params,
    )
    items = []
    for row in rows:
        item = dict(row._mapping)
        for k, v in item.items():
            if hasattr(v, "isoformat"):
                item[k] = str(v)
            elif isinstance(v, (int, float)) and v is not None and (
                k.endswith("amount") or k in MONITOR_ROW_FLOAT_KEYS
            ):
                item[k] = float(v)
        items.append(item)
    return items, total


def fetch_repayment_plan_records_for_export(
    conn: Connection,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    where_parts = ["1=1"]
    params: dict[str, Any] = {}
    for key in (
        "trust_product_id", "asset_code",
        "custody_asset_code", "source_asset_code",
        "source_file_name", "source_sheet_name",
    ):
        _append_assetinfo_record_filter(where_parts, params, key, filters.get(key))
    if filters.get("data_date"):
        where_parts.append("r.data_date = :data_date")
        params["data_date"] = filters["data_date"]
    where_sql = " AND ".join(where_parts)
    rows = conn.execute(
        text(f"""
            SELECT r.*
            FROM trust_repayment_plan_records r
            WHERE {where_sql}
            ORDER BY r.data_date DESC NULLS LAST, r.id ASC
        """),
        params,
    )
    items = []
    for row in rows:
        item = dict(row._mapping)
        for k, v in item.items():
            if hasattr(v, "isoformat"):
                item[k] = str(v)
            elif isinstance(v, (int, float)) and v is not None and (
                k.endswith("amount") or k in MONITOR_ROW_FLOAT_KEYS
            ):
                item[k] = float(v)
        # 模版「资产编号(房源)」优先 source，再 asset_code
        if not item.get("source_asset_code"):
            item["source_asset_code"] = item.get("asset_code")
        items.append(item)
    return items


def build_repayment_disclosure_export_xlsx(
    repayment_items: list[dict[str, Any]],
    plan_items: list[dict[str, Any]],
) -> bytes:
    """按还款明细披露信息模版导出双 Sheet."""
    detail_headers = templates.template_headers(templates.REPAYMENT_DETAIL_TEMPLATE_COLUMNS)
    detail_rows = [
        templates.row_values_for_template(
            item, templates.REPAYMENT_DETAIL_TEMPLATE_COLUMNS,
            format_cell=_format_monitor_export_cell,
        )
        for item in repayment_items
    ]
    plan_headers = templates.template_headers(templates.REPAYMENT_PLAN_TEMPLATE_COLUMNS)
    plan_rows = [
        templates.row_values_for_template(
            item, templates.REPAYMENT_PLAN_TEMPLATE_COLUMNS,
            format_cell=_format_monitor_export_cell,
        )
        for item in plan_items
    ]
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(detail_rows, columns=detail_headers).to_excel(
            writer, index=False, sheet_name="还款明细",
        )
        pd.DataFrame(plan_rows, columns=plan_headers).to_excel(
            writer, index=False, sheet_name="回款计划",
        )
    return buffer.getvalue()


def _monitor_transferred_out_exists_sql() -> str:
    """已转让=否：排除已从 trust_product_id 转出的托管房源。"""
    custody_match = _monitor_custody_norm_match_sql(
        "i.custody_asset_code",
        "COALESCE(r.custody_asset_code, r.asset_code, '')",
    )
    return f"""
        EXISTS (
            SELECT 1
            FROM trust_product_issuance_asset_records i
            WHERE i.migration_type = 'transfer'
              AND i.from_trust_product_id = :trust_product_id
              AND {custody_match}
        )
    """


ASSETINFO_FUZZY_FILTER_KEYS = frozenset({
    "asset_code",
    "custody_asset_code",
    "source_asset_code",
    "source_file_name",
    "source_sheet_name",
})


def _append_assetinfo_record_filter(
    where_parts: list[str],
    params: dict[str, Any],
    key: str,
    val: Any,
    *,
    skip_trust_product_where: bool = False,
) -> None:
    if val is None or val == "":
        return
    if key == "trust_product_id":
        params[key] = int(val)
        if skip_trust_product_where:
            return
        where_parts.append("r.trust_product_id = :trust_product_id")
        return
    if key in ASSETINFO_FUZZY_FILTER_KEYS:
        where_parts.append(f"r.{key}::text ILIKE :{key}")
        params[key] = f"%{val}%"
        return
    where_parts.append(f"r.{key} = :{key}")
    params[key] = val


def fetch_paginated_records(
    conn: Connection,
    table: str,
    page: int,
    page_size: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    allowed = {
        "repayment": "trust_repayment_detail_records",
        "repayment_plan": "trust_repayment_plan_records",
        "monitor": "trust_asset_monitor_records",
    }
    table_name = allowed.get(table)
    if not table_name:
        raise HTTPException(status_code=400, detail="invalid table")

    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    offset = (page - 1) * page_size

    if table == "monitor":
        where_sql, base_params, snapshot_join, issuance_join, order_by_sql, select_extra = (
            _build_monitor_record_query(filters)
        )
        params = {**base_params, "limit": page_size, "offset": offset}
        count_row = conn.execute(
            text(f"""
                SELECT COUNT(*) AS cnt
                FROM {table_name} r
                JOIN trust_products tp ON tp.id = r.trust_product_id
                {snapshot_join}
                {issuance_join}
                WHERE {where_sql}
            """),
            base_params,
        ).fetchone()
        total = int(count_row.cnt)
        rows = conn.execute(
            text(f"""
                SELECT r.*, tp.name AS trust_product_name{select_extra}
                FROM {table_name} r
                JOIN trust_products tp ON tp.id = r.trust_product_id
                {snapshot_join}
                {issuance_join}
                WHERE {where_sql}
                ORDER BY {order_by_sql}
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
        items = [_normalize_monitor_row(row) for row in rows]
        result: dict[str, Any] = {
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": items,
            "view_mode": _monitor_snapshot_view_mode(filters),
            "include_history": bool(filters.get("include_history")),
        }
        if filters.get("transferred"):
            result["transferred"] = filters["transferred"]
        if filters.get("sort_by"):
            result["sort_by"] = filters["sort_by"]
            result["sort_dir"] = filters.get("sort_dir") or "desc"
        return result

    where_parts = ["1=1"]
    params: dict[str, Any] = {"limit": page_size, "offset": offset}

    for key in (
        "trust_product_id", "data_date", "asset_code",
        "custody_asset_code", "source_asset_code",
        "source_file_name", "source_sheet_name",
    ):
        _append_assetinfo_record_filter(
            where_parts,
            params,
            key,
            filters.get(key),
            skip_trust_product_where=False,
        )

    where_sql = " AND ".join(where_parts)
    if table == "repayment_plan":
        order_by_sql = "r.data_date DESC NULLS LAST, r.id DESC"
    else:
        order_by_sql = MONITOR_DEFAULT_ORDER_BY.strip()

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
            ORDER BY {order_by_sql}
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
            elif isinstance(v, (int, float)) and v is not None and (
                k.endswith("amount") or k in MONITOR_ROW_FLOAT_KEYS
            ):
                item[k] = float(v)
        items.append(item)

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": items,
    }
