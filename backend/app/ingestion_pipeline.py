"""信托风控数据准入管道 V1."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.auth import record_ingestion_run

RECONCILIATION_TOLERANCE = 0.01
SHEET_MONITOR = "2更新的资产数据表"
SHEET_REPAYMENT = "1全量还款明细汇总"
ALIAS_COLUMN = "当前信托计划（已发行）"

DEFAULT_EXCEL_PATH = "excel文件/逾期自查（对账单更新至20260610）.xlsx"
DEFAULT_ASSET_LOOKUP_PATH = "excel文件/美好生活1号-资产监控表_0612.xlsx"

DEFAULT_MAPPINGS = [
    {"sheet_name": SHEET_MONITOR, "sheet_type": "asset_monitor", "excel_column": "托管房源编码",
     "target_table": "trust_asset_monitor_records", "target_column": "custody_asset_code",
     "transform_rule": "to_custody_code", "is_required": True},
    {"sheet_name": SHEET_MONITOR, "sheet_type": "asset_monitor", "excel_column": "统计日期",
     "target_table": "trust_asset_monitor_records", "target_column": "data_date",
     "transform_rule": "to_date", "is_required": True},
    {"sheet_name": SHEET_MONITOR, "sheet_type": "asset_monitor", "excel_column": "初始受让金额",
     "target_table": "trust_asset_monitor_records", "target_column": "initial_transfer_amount",
     "transform_rule": "to_numeric", "is_required": True},
    {"sheet_name": SHEET_MONITOR, "sheet_type": "asset_monitor", "excel_column": "已还款金额",
     "target_table": "trust_asset_monitor_records", "target_column": "repaid_amount",
     "transform_rule": "to_numeric", "is_required": True},
    {"sheet_name": SHEET_MONITOR, "sheet_type": "asset_monitor", "excel_column": "剩余还款金额",
     "target_table": "trust_asset_monitor_records", "target_column": "remaining_amount",
     "transform_rule": "to_numeric", "is_required": True},
    {"sheet_name": SHEET_MONITOR, "sheet_type": "asset_monitor", "excel_column": "文件名",
     "target_table": "trust_asset_monitor_records", "target_column": "source_file_name",
     "transform_rule": None, "is_required": False},
    {"sheet_name": SHEET_REPAYMENT, "sheet_type": "repayment_detail", "excel_column": "托管房源编号",
     "target_table": "trust_repayment_detail_records", "target_column": "custody_asset_code",
     "transform_rule": "to_custody_code", "is_required": True},
    {"sheet_name": SHEET_REPAYMENT, "sheet_type": "repayment_detail", "excel_column": "当期实际还款金额",
     "target_table": "trust_repayment_detail_records", "target_column": "actual_repayment_amount",
     "transform_rule": "to_numeric", "is_required": True},
    {"sheet_name": SHEET_REPAYMENT, "sheet_type": "repayment_detail", "excel_column": "还款日期",
     "target_table": "trust_repayment_detail_records", "target_column": "repayment_date",
     "transform_rule": "to_date", "is_required": True},
    {"sheet_name": SHEET_REPAYMENT, "sheet_type": "repayment_detail", "excel_column": "所属文件名称",
     "target_table": "trust_repayment_detail_records", "target_column": "source_file_name",
     "transform_rule": None, "is_required": False},
    {"sheet_name": SHEET_REPAYMENT, "sheet_type": "repayment_detail", "excel_column": "所属Sheet名称",
     "target_table": "trust_repayment_detail_records", "target_column": "source_sheet_name",
     "transform_rule": None, "is_required": False},
]


def _repo_root() -> Path:
    env_root = os.getenv("INGESTION_REPO_ROOT")
    if env_root:
        root = Path(env_root)
        if root.is_dir():
            return root
    for candidate in (
        Path(__file__).resolve().parents[2],
        Path("/app"),
        Path("/data/repo"),
    ):
        if (candidate / "excel文件").is_dir():
            return candidate
    return Path(__file__).resolve().parents[2]


def _resolve_path(path: str | None, default: str) -> Path:
    raw = path or default
    p = Path(raw)
    if not p.is_absolute():
        p = _repo_root() / p
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {p}")
    return p


def to_custody_code(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    text_val = str(value).strip()
    return text_val or None


def to_date_value(value) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return pd.Timestamp(value).date()


def to_numeric_value(value) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    return float(value)


def load_mapping_config(conn: Connection) -> list[dict]:
    try:
        rows = conn.execute(
            text("""
                SELECT sheet_name, sheet_type, excel_column, target_table, target_column,
                       transform_rule, is_required
                FROM data_mapping_config
                WHERE active = TRUE
                  AND sheet_name IN (:sheet_monitor, :sheet_repayment)
                ORDER BY priority, id
            """),
            {"sheet_monitor": SHEET_MONITOR, "sheet_repayment": SHEET_REPAYMENT},
        )
        mappings = [
            {
                "sheet_name": r.sheet_name,
                "sheet_type": r.sheet_type,
                "excel_column": r.excel_column,
                "target_table": r.target_table,
                "target_column": r.target_column,
                "transform_rule": r.transform_rule,
                "is_required": bool(r.is_required),
            }
            for r in rows
        ]
        if mappings:
            return mappings
    except Exception:
        pass
    return DEFAULT_MAPPINGS


def _mappings_for_sheet(mappings: list[dict], sheet_name: str) -> list[dict]:
    return [m for m in mappings if m["sheet_name"] == sheet_name]


def _apply_transform(rule: str | None, series: pd.Series) -> pd.Series:
    if rule == "to_custody_code":
        return series.map(to_custody_code)
    if rule == "to_date":
        return series.map(to_date_value)
    if rule == "to_numeric":
        return series.map(to_numeric_value)
    return series


def _map_dataframe(df: pd.DataFrame, mappings: list[dict]) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    for m in mappings:
        col = m["excel_column"]
        target = m["target_column"]
        if m["is_required"] and col not in df.columns:
            raise HTTPException(status_code=400, detail=f"Missing required column: {col}")
        if col not in df.columns:
            continue
        out[target] = _apply_transform(m.get("transform_rule"), df[col])
    if ALIAS_COLUMN in df.columns:
        out["trust_plan_alias"] = df[ALIAS_COLUMN]
    return out


def _load_excel_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, header=0)
    return df.dropna(how="all")


def _filter_by_alias(df: pd.DataFrame, trust_plan_alias: str | None) -> pd.DataFrame:
    if not trust_plan_alias or ALIAS_COLUMN not in df.columns:
        return df
    return df[df[ALIAS_COLUMN].astype(str) == trust_plan_alias].copy()


def _resolve_batch_data_date(dates: pd.Series) -> tuple[date, int]:
    """Pick unified batch date (mode); return (date, excluded_row_count)."""
    parsed = [to_date_value(d) for d in dates if to_date_value(d) is not None]
    if not parsed:
        raise HTTPException(status_code=400, detail="Sheet2 has no valid 统计日期")
    from collections import Counter

    counter = Counter(parsed)
    batch_date, _ = counter.most_common(1)[0]
    excluded = sum(1 for d in parsed if d != batch_date)
    return batch_date, excluded


def load_f1_asset_lookup(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    df = _load_excel_sheet(path, df_sheet_name(path))
    lookup: dict[str, str] = {}
    if "托管房源编码" not in df.columns or "资产编号(房源)" not in df.columns:
        return lookup
    for _, row in df.iterrows():
        custody = to_custody_code(row["托管房源编码"])
        asset_code = row.get("资产编号(房源)")
        if custody and asset_code is not None and not pd.isna(asset_code):
            lookup[custody] = str(asset_code).strip()
    return lookup


def df_sheet_name(path: Path) -> str:
    xl = pd.ExcelFile(path)
    return xl.sheet_names[0]


def load_db_asset_lookup(conn: Connection, trust_product_id: int) -> dict[str, str]:
    rows = conn.execute(
        text("""
            SELECT custody_asset_code,
                   COALESCE(source_asset_code, asset_code) AS source_asset_code
            FROM trust_assets
            WHERE trust_product_id = :trust_product_id
              AND custody_asset_code IS NOT NULL
        """),
        {"trust_product_id": trust_product_id},
    )
    return {r.custody_asset_code: r.source_asset_code for r in rows}


def resolve_asset_code(
    custody: str,
    f1_lookup: dict[str, str],
    db_lookup: dict[str, str],
) -> str:
    if custody in f1_lookup:
        return f1_lookup[custody]
    if custody in db_lookup:
        return db_lookup[custody]
    return custody


def _compute_payment_dates(repayment_df: pd.DataFrame) -> dict[str, date]:
    if repayment_df.empty:
        return {}
    grouped = repayment_df.groupby("custody_asset_code")["repayment_date"].max()
    return {k: v for k, v in grouped.items() if v is not None}


def _verify_trust_product(conn: Connection, trust_product_id: int) -> None:
    row = conn.execute(
        text("SELECT id FROM trust_products WHERE id = :id"),
        {"id": trust_product_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"trust_product_id {trust_product_id} not found")


def _delete_existing_batch(conn: Connection, trust_product_id: int, data_date: date) -> None:
    conn.execute(
        text("""
            DELETE FROM trust_repayment_detail_records
            WHERE trust_product_id = :trust_product_id AND data_date = :data_date
        """),
        {"trust_product_id": trust_product_id, "data_date": data_date},
    )
    conn.execute(
        text("""
            DELETE FROM trust_asset_monitor_records
            WHERE trust_product_id = :trust_product_id AND data_date = :data_date
        """),
        {"trust_product_id": trust_product_id, "data_date": data_date},
    )


def _upsert_trust_asset(
    conn: Connection,
    trust_product_id: int,
    asset_code: str,
    custody_asset_code: str,
    initial_transfer_amount: float,
) -> int:
    row = conn.execute(
        text("""
            INSERT INTO trust_assets (
                trust_product_id, asset_code, custody_asset_code,
                source_asset_code, initial_transfer_amount
            ) VALUES (
                :trust_product_id, :asset_code, :custody_asset_code,
                :source_asset_code, :initial_transfer_amount
            )
            ON CONFLICT (trust_product_id, asset_code) DO UPDATE SET
                custody_asset_code = EXCLUDED.custody_asset_code,
                source_asset_code = COALESCE(
                    trust_assets.source_asset_code, EXCLUDED.source_asset_code
                ),
                initial_transfer_amount = EXCLUDED.initial_transfer_amount,
                updated_at = NOW()
            RETURNING id
        """),
        {
            "trust_product_id": trust_product_id,
            "asset_code": asset_code,
            "custody_asset_code": custody_asset_code,
            "source_asset_code": asset_code,
            "initial_transfer_amount": initial_transfer_amount,
        },
    ).fetchone()
    return int(row.id)


def run_consistency_checks(
    conn: Connection,
    trust_product_id: int,
    data_date: date,
) -> dict:
    rows = conn.execute(
        text("""
            SELECT
                m.trust_asset_id,
                m.asset_code,
                m.initial_transfer_amount,
                m.repaid_amount,
                m.remaining_amount,
                COALESCE(rs.total_repaid, 0) AS detail_total_repaid
            FROM trust_asset_monitor_records m
            LEFT JOIN (
                SELECT trust_asset_id, SUM(actual_repayment_amount) AS total_repaid
                FROM trust_repayment_detail_records
                WHERE trust_product_id = :trust_product_id AND data_date = :data_date
                GROUP BY trust_asset_id
            ) rs ON rs.trust_asset_id = m.trust_asset_id
            WHERE m.trust_product_id = :trust_product_id AND m.data_date = :data_date
        """),
        {"trust_product_id": trust_product_id, "data_date": data_date},
    )

    balance_failures = 0
    cross_sheet_failures = 0
    missing_last_payment = 0

    for r in rows:
        balance_diff = abs(
            float(r.initial_transfer_amount) - float(r.repaid_amount) - float(r.remaining_amount)
        )
        if balance_diff > RECONCILIATION_TOLERANCE:
            balance_failures += 1
        cross_diff = abs(float(r.repaid_amount) - float(r.detail_total_repaid))
        if cross_diff > RECONCILIATION_TOLERANCE:
            cross_sheet_failures += 1

    null_last = conn.execute(
        text("""
            SELECT COUNT(*) AS cnt
            FROM trust_asset_monitor_records
            WHERE trust_product_id = :trust_product_id
              AND data_date = :data_date
              AND last_payment_date IS NULL
        """),
        {"trust_product_id": trust_product_id, "data_date": data_date},
    ).fetchone()
    missing_last_payment = int(null_last.cnt) if null_last else 0

    return {
        "balance_equation_failures": balance_failures,
        "cross_sheet_repayment_failures": cross_sheet_failures,
        "missing_last_payment_date_count": missing_last_payment,
        "tolerance": RECONCILIATION_TOLERANCE,
    }


def run_ingestion_pipeline(
    conn: Connection,
    trust_product_id: int,
    trust_plan_alias: str | None = None,
    excel_path: str | None = None,
    asset_lookup_path: str | None = None,
    user_id: int | None = None,
) -> dict:
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    _verify_trust_product(conn, trust_product_id)
    mappings = load_mapping_config(conn)

    excel_file = _resolve_path(excel_path, DEFAULT_EXCEL_PATH)
    lookup_file = _resolve_path(asset_lookup_path, DEFAULT_ASSET_LOOKUP_PATH)

    monitor_raw = _filter_by_alias(_load_excel_sheet(excel_file, SHEET_MONITOR), trust_plan_alias)
    repayment_raw = _filter_by_alias(_load_excel_sheet(excel_file, SHEET_REPAYMENT), trust_plan_alias)

    if monitor_raw.empty:
        raise HTTPException(status_code=400, detail="No monitor rows after filter")

    monitor_mapped = _map_dataframe(monitor_raw, _mappings_for_sheet(mappings, SHEET_MONITOR))
    repayment_mapped = _map_dataframe(repayment_raw, _mappings_for_sheet(mappings, SHEET_REPAYMENT))

    data_date, excluded_mixed_batch_rows = _resolve_batch_data_date(monitor_mapped["data_date"])
    monitor_mapped = monitor_mapped[monitor_mapped["data_date"] == data_date].copy()
    if monitor_mapped.empty:
        raise HTTPException(status_code=400, detail=f"No monitor rows for batch data_date {data_date}")

    f1_lookup = load_f1_asset_lookup(lookup_file)
    db_lookup = load_db_asset_lookup(conn, trust_product_id)

    custody_set = set(monitor_mapped["custody_asset_code"].dropna().astype(str))
    repayment_mapped = repayment_mapped[
        repayment_mapped["custody_asset_code"].isin(custody_set)
    ].copy()

    payment_dates = _compute_payment_dates(repayment_mapped)
    synced_at = datetime.now(timezone.utc)
    source_file_name = excel_file.name

    _delete_existing_batch(conn, trust_product_id, data_date)

    upsert_asset_count = 0
    inserted_monitor_count = 0
    asset_id_by_custody: dict[str, int] = {}

    for _, row in monitor_mapped.iterrows():
        custody = row["custody_asset_code"]
        if not custody:
            continue
        asset_code = resolve_asset_code(custody, f1_lookup, db_lookup)
        trust_asset_id = _upsert_trust_asset(
            conn,
            trust_product_id,
            asset_code,
            custody,
            float(row["initial_transfer_amount"]),
        )
        upsert_asset_count += 1
        asset_id_by_custody[custody] = trust_asset_id
        db_lookup[custody] = asset_code

        last_payment_date = payment_dates.get(custody)
        max_payment_date = last_payment_date
        if last_payment_date:
            overdue_days = max(0, (data_date - last_payment_date).days)
        else:
            overdue_days = 0

        monitor_source_file = row.get("source_file_name")
        if monitor_source_file is None or (isinstance(monitor_source_file, float) and pd.isna(monitor_source_file)):
            monitor_source_file = source_file_name
        else:
            monitor_source_file = str(monitor_source_file)

        conn.execute(
            text("""
                INSERT INTO trust_asset_monitor_records (
                    trust_product_id, trust_asset_id, asset_code,
                    custody_asset_code, source_asset_code, data_date,
                    initial_transfer_amount, repaid_amount, remaining_amount,
                    overdue_days, last_payment_date, max_payment_date,
                    source_file_name, source_sheet_name, synced_at
                ) VALUES (
                    :trust_product_id, :trust_asset_id, :asset_code,
                    :custody_asset_code, :source_asset_code, :data_date,
                    :initial_transfer_amount, :repaid_amount, :remaining_amount,
                    :overdue_days, :last_payment_date, :max_payment_date,
                    :source_file_name, :source_sheet_name, :synced_at
                )
            """),
            {
                "trust_product_id": trust_product_id,
                "trust_asset_id": trust_asset_id,
                "asset_code": asset_code,
                "custody_asset_code": custody,
                "source_asset_code": asset_code,
                "data_date": data_date,
                "initial_transfer_amount": float(row["initial_transfer_amount"]),
                "repaid_amount": float(row["repaid_amount"]),
                "remaining_amount": float(row["remaining_amount"]),
                "overdue_days": overdue_days,
                "last_payment_date": last_payment_date,
                "max_payment_date": max_payment_date,
                "source_file_name": monitor_source_file,
                "source_sheet_name": SHEET_MONITOR,
                "synced_at": synced_at,
            },
        )
        inserted_monitor_count += 1

    inserted_repayment_count = 0
    for _, row in repayment_mapped.iterrows():
        custody = row["custody_asset_code"]
        if not custody or custody not in asset_id_by_custody:
            continue
        asset_code = db_lookup.get(custody, custody)
        conn.execute(
            text("""
                INSERT INTO trust_repayment_detail_records (
                    trust_product_id, trust_asset_id, asset_code,
                    custody_asset_code, source_asset_code,
                    data_date, period_no, actual_repayment_amount, repayment_date,
                    source_file_name, source_sheet_name, synced_at
                ) VALUES (
                    :trust_product_id, :trust_asset_id, :asset_code,
                    :custody_asset_code, :source_asset_code,
                    :data_date, NULL, :actual_repayment_amount, :repayment_date,
                    :source_file_name, :source_sheet_name, :synced_at
                )
            """),
            {
                "trust_product_id": trust_product_id,
                "trust_asset_id": asset_id_by_custody[custody],
                "asset_code": asset_code,
                "custody_asset_code": custody,
                "source_asset_code": asset_code,
                "data_date": data_date,
                "actual_repayment_amount": float(row["actual_repayment_amount"]),
                "repayment_date": row["repayment_date"],
                "source_file_name": row.get("source_file_name") or source_file_name,
                "source_sheet_name": row.get("source_sheet_name") or SHEET_REPAYMENT,
                "synced_at": synced_at,
            },
        )
        inserted_repayment_count += 1

    consistency_checks = run_consistency_checks(conn, trust_product_id, data_date)
    product_row = conn.execute(
        text("SELECT name FROM trust_products WHERE id = :id"),
        {"id": trust_product_id},
    ).fetchone()
    run_id, created_at = record_ingestion_run(
        conn,
        trust_product_id=trust_product_id,
        data_date=data_date,
        trust_plan_alias=trust_plan_alias,
        source_file=str(excel_file),
        created_by=user_id,
        inserted_monitor_count=inserted_monitor_count,
        inserted_repayment_count=inserted_repayment_count,
        upsert_asset_count=upsert_asset_count,
        trust_product_name=product_row.name if product_row else None,
    )
    conn.commit()

    return {
        "trust_product_id": trust_product_id,
        "trust_plan_alias": trust_plan_alias,
        "data_date": str(data_date),
        "source_file": str(excel_file),
        "excluded_mixed_batch_rows": excluded_mixed_batch_rows,
        "inserted_monitor_count": inserted_monitor_count,
        "inserted_repayment_count": inserted_repayment_count,
        "upsert_asset_count": upsert_asset_count,
        "consistency_checks": consistency_checks,
        "run_id": run_id,
        "created_by": user_id,
        "created_at": created_at,
    }
