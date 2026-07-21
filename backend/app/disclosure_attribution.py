"""披露资产归属：置换 / 回购 / 发行事件裁决。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection


SOURCE_SWAP = "swap"
SOURCE_REPURCHASE = "repurchase"
SOURCE_ISSUANCE = "issuance"

STATUS_REPURCHASED = "已回购"
STATUS_SWAP_OUT = "已置换转出"


@dataclass(frozen=True)
class AttributionEvent:
    source: str
    business_date: date
    trust_product_id: int
    trust_product_name: str | None = None
    initial_transfer_amount: float | None = None
    repaid_amount: float | None = None
    remaining_amount: float | None = None
    ref: str = ""


@dataclass
class AssetAttribution:
    asset_code: str
    source: str | None = None
    business_date: date | None = None
    trust_product_id: int | None = None
    trust_product_name: str | None = None
    initial_transfer_amount: float | None = None
    repaid_amount: float | None = None
    remaining_amount: float | None = None
    is_repurchased: bool = False


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text_v = str(value).strip()
    if not text_v:
        return None
    return date.fromisoformat(text_v[:10])


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _asset_key(asset_code: Any, custody_asset_code: Any = None) -> str:
    ac = str(asset_code or "").strip()
    if ac:
        return ac
    return str(custody_asset_code or "").strip()


def resolve_events_for_asset(
    events: list[AttributionEvent],
    *,
    asset_label: str,
) -> AttributionEvent | None:
    """按业务日取最新；同日多事件报错。无事件返回 None。"""
    if not events:
        return None
    by_date: dict[date, list[AttributionEvent]] = {}
    for ev in events:
        by_date.setdefault(ev.business_date, []).append(ev)
    latest = max(by_date.keys())
    winners = by_date[latest]
    if len(winners) > 1:
        detail = "；".join(
            f"{w.source}#{w.ref}→产品{w.trust_product_id}" for w in winners
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"资产 {asset_label} 在 {latest.isoformat()} 存在多条归属事件冲突，"
                f"无法取数：{detail}"
            ),
        )
    return winners[0]


def _load_swap_entry_events(conn: Connection, as_of: date) -> list[tuple[str, AttributionEvent]]:
    """置换后归属 = 各腿 to_trust_product_id；金额取转入快照 entry（含 direction=out 进入对手方）。"""
    rows = conn.execute(
        text(
            """
            SELECT a.asset_code,
                   a.to_trust_product_id,
                   a.to_trust_product_name,
                   o.swap_business_date,
                   o.id AS order_id,
                   a.id AS swap_asset_id,
                   s.initial_transfer_amount,
                   s.repaid_amount,
                   s.remaining_amount
            FROM asset_swap_assets a
            JOIN asset_swap_orders o ON o.id = a.swap_order_id
            LEFT JOIN asset_swap_monitor_snapshots s
              ON s.swap_asset_id = a.id
             AND s.snapshot_role = 'entry'
            WHERE o.status = 'completed'
              AND o.swap_business_date IS NOT NULL
              AND o.swap_business_date <= :as_of
              AND a.to_trust_product_id IS NOT NULL
              AND a.asset_code IS NOT NULL
              AND TRIM(a.asset_code) <> ''
            """
        ),
        {"as_of": as_of},
    ).fetchall()
    out: list[tuple[str, AttributionEvent]] = []
    for r in rows:
        key = _asset_key(r.asset_code)
        biz = _as_date(r.swap_business_date)
        if not key or biz is None or r.to_trust_product_id is None:
            continue
        out.append(
            (
                key,
                AttributionEvent(
                    source=SOURCE_SWAP,
                    business_date=biz,
                    trust_product_id=int(r.to_trust_product_id),
                    trust_product_name=(str(r.to_trust_product_name).strip() or None)
                    if r.to_trust_product_name
                    else None,
                    initial_transfer_amount=_as_float(r.initial_transfer_amount),
                    repaid_amount=_as_float(r.repaid_amount),
                    remaining_amount=_as_float(r.remaining_amount),
                    ref=f"order:{int(r.order_id)}/asset:{int(r.swap_asset_id)}",
                ),
            )
        )
    return out


def _load_repurchase_events(conn: Connection, as_of: date) -> list[tuple[str, AttributionEvent]]:
    rows = conn.execute(
        text(
            """
            SELECT ra.asset_code,
                   ra.trust_product_id,
                   ra.trust_product_name,
                   o.repurchase_business_date,
                   o.id AS order_id,
                   ra.initial_transfer_amount,
                   ra.repaid_amount,
                   ra.remaining_amount
            FROM asset_repurchase_assets ra
            JOIN asset_repurchase_orders o ON o.id = ra.repurchase_order_id
            WHERE o.status = 'completed'
              AND o.repurchase_business_date IS NOT NULL
              AND o.repurchase_business_date <= :as_of
              AND ra.asset_code IS NOT NULL
              AND TRIM(ra.asset_code) <> ''
            """
        ),
        {"as_of": as_of},
    ).fetchall()
    out: list[tuple[str, AttributionEvent]] = []
    for r in rows:
        key = _asset_key(r.asset_code)
        biz = _as_date(r.repurchase_business_date)
        if not key or biz is None or r.trust_product_id is None:
            continue
        out.append(
            (
                key,
                AttributionEvent(
                    source=SOURCE_REPURCHASE,
                    business_date=biz,
                    trust_product_id=int(r.trust_product_id),
                    trust_product_name=(str(r.trust_product_name).strip() or None)
                    if r.trust_product_name
                    else None,
                    initial_transfer_amount=_as_float(r.initial_transfer_amount),
                    repaid_amount=_as_float(r.repaid_amount),
                    remaining_amount=_as_float(r.remaining_amount),
                    ref=f"order:{int(r.order_id)}",
                ),
            )
        )
    return out


def _load_issuance_events(conn: Connection, as_of: date) -> list[tuple[str, AttributionEvent]]:
    """发行按 custody_asset_code 建键；调用方再挂到 asset_code。"""
    rows = conn.execute(
        text(
            """
            SELECT custody_asset_code,
                   trust_product_id,
                   trust_product_name,
                   issue_date,
                   id
            FROM trust_product_issuance_asset_records
            WHERE issue_date IS NOT NULL
              AND issue_date <= :as_of
              AND custody_asset_code IS NOT NULL
              AND TRIM(custody_asset_code) <> ''
              AND trust_product_id IS NOT NULL
            """
        ),
        {"as_of": as_of},
    ).fetchall()
    out: list[tuple[str, AttributionEvent]] = []
    for r in rows:
        key = str(r.custody_asset_code).strip()
        biz = _as_date(r.issue_date)
        if not key or biz is None:
            continue
        out.append(
            (
                key,
                AttributionEvent(
                    source=SOURCE_ISSUANCE,
                    business_date=biz,
                    trust_product_id=int(r.trust_product_id),
                    trust_product_name=(str(r.trust_product_name).strip() or None)
                    if r.trust_product_name
                    else None,
                    ref=f"id:{int(r.id)}",
                ),
            )
        )
    return out


def load_repurchased_asset_codes(conn: Connection, as_of: date) -> set[str]:
    rows = conn.execute(
        text(
            """
            SELECT DISTINCT ra.asset_code
            FROM asset_repurchase_assets ra
            JOIN asset_repurchase_orders o ON o.id = ra.repurchase_order_id
            WHERE o.status = 'completed'
              AND o.repurchase_business_date IS NOT NULL
              AND o.repurchase_business_date <= :as_of
              AND ra.asset_code IS NOT NULL
              AND TRIM(ra.asset_code) <> ''
            """
        ),
        {"as_of": as_of},
    ).fetchall()
    return {str(r.asset_code).strip() for r in rows if r.asset_code}


def load_swap_out_pairs(conn: Connection, as_of: date) -> set[tuple[int, str]]:
    """(from_trust_product_id, asset_code) 在 as_of 前已从该产品置换转出（含 out/in 腿）。"""
    rows = conn.execute(
        text(
            """
            SELECT a.from_trust_product_id, a.asset_code
            FROM asset_swap_assets a
            JOIN asset_swap_orders o ON o.id = a.swap_order_id
            WHERE o.status = 'completed'
              AND o.swap_business_date IS NOT NULL
              AND o.swap_business_date <= :as_of
              AND a.from_trust_product_id IS NOT NULL
              AND a.asset_code IS NOT NULL
              AND TRIM(a.asset_code) <> ''
            """
        ),
        {"as_of": as_of},
    ).fetchall()
    return {
        (int(r.from_trust_product_id), str(r.asset_code).strip())
        for r in rows
        if r.from_trust_product_id is not None and r.asset_code
    }


def _monitor_amounts_for_issuance(
    conn: Connection,
    *,
    trust_product_id: int,
    asset_code: str,
    custody_asset_code: str | None,
    as_of: date,
) -> tuple[float | None, float | None, float | None]:
    row = conn.execute(
        text(
            """
            SELECT initial_transfer_amount, repaid_amount, remaining_amount
            FROM trust_asset_monitor_records
            WHERE trust_product_id = :pid
              AND data_date <= :as_of
              AND (
                    asset_code = :ac
                 OR (
                        :cac IS NOT NULL
                    AND custody_asset_code = :cac
                 )
              )
            ORDER BY data_date DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ),
        {
            "pid": trust_product_id,
            "as_of": as_of,
            "ac": asset_code,
            "cac": (custody_asset_code or "").strip() or None,
        },
    ).fetchone()
    if not row:
        return None, None, None
    return (
        _as_float(row.initial_transfer_amount),
        _as_float(row.repaid_amount),
        _as_float(row.remaining_amount),
    )


def build_attribution_index(
    conn: Connection,
    as_of: date,
    assets: list[tuple[str, str | None]],
) -> dict[str, AssetAttribution]:
    """为 (asset_code, custody?) 列表构建归属；同日冲突抛 HTTPException。"""
    wanted: dict[str, str | None] = {}
    for ac, cac in assets:
        key = _asset_key(ac, cac)
        if not key:
            continue
        wanted[key] = (cac or "").strip() or wanted.get(key)

    if not wanted:
        return {}

    events_by_asset: dict[str, list[AttributionEvent]] = {k: [] for k in wanted}

    for key, ev in _load_swap_entry_events(conn, as_of):
        if key in events_by_asset:
            events_by_asset[key].append(ev)

    for key, ev in _load_repurchase_events(conn, as_of):
        if key in events_by_asset:
            events_by_asset[key].append(ev)

    issuance_by_custody: dict[str, list[AttributionEvent]] = {}
    for custody, ev in _load_issuance_events(conn, as_of):
        issuance_by_custody.setdefault(custody, []).append(ev)

    for key, custody in wanted.items():
        # 发行键：custody；若空则尝试 asset_code 本身（常见左 12 一致）
        for cand in dict.fromkeys([c for c in (custody, key) if c]):
            for ev in issuance_by_custody.get(cand, []):
                events_by_asset[key].append(ev)

    repurchased = load_repurchased_asset_codes(conn, as_of)
    result: dict[str, AssetAttribution] = {}
    for key, events in events_by_asset.items():
        # 同源同日多条：resolve_events_for_asset 会报错
        winner = resolve_events_for_asset(events, asset_label=key)
        attr = AssetAttribution(
            asset_code=key,
            is_repurchased=key in repurchased,
        )
        if winner is None:
            result[key] = attr
            continue
        attr.source = winner.source
        attr.business_date = winner.business_date
        attr.trust_product_id = winner.trust_product_id
        attr.trust_product_name = winner.trust_product_name
        if winner.source == SOURCE_ISSUANCE:
            ita, ra, rem = _monitor_amounts_for_issuance(
                conn,
                trust_product_id=winner.trust_product_id,
                asset_code=key,
                custody_asset_code=wanted.get(key),
                as_of=as_of,
            )
            attr.initial_transfer_amount = ita
            attr.repaid_amount = ra
            attr.remaining_amount = rem
        else:
            attr.initial_transfer_amount = winner.initial_transfer_amount
            attr.repaid_amount = winner.repaid_amount
            attr.remaining_amount = winner.remaining_amount
        result[key] = attr
    return result


def apply_triad_from_attribution(row: dict[str, Any], attr: AssetAttribution | None) -> None:
    """覆写披露还款明细三列（仅当存在胜出事件且金额可得）。"""
    if attr is None or attr.source is None:
        return
    if attr.initial_transfer_amount is not None:
        row["initial_renovation_amount"] = attr.initial_transfer_amount
    if attr.repaid_amount is not None:
        row["cumulative_repaid_amount"] = attr.repaid_amount
    if attr.remaining_amount is not None:
        row["remaining_balance"] = attr.remaining_amount


def apply_monitor_amounts_from_attribution(
    row: dict[str, Any], attr: AssetAttribution | None
) -> None:
    """覆写监控/回款计划金额三列（转入快照或回购/发行对应监控值）。"""
    if attr is None or attr.source is None:
        return
    if attr.initial_transfer_amount is not None:
        row["initial_transfer_amount"] = attr.initial_transfer_amount
    if attr.repaid_amount is not None:
        row["repaid_amount"] = attr.repaid_amount
    if attr.remaining_amount is not None:
        row["remaining_amount"] = attr.remaining_amount


def apply_product_from_attribution(
    row: dict[str, Any],
    attr: AssetAttribution | None,
    *,
    name_by_id: dict[int, str] | None = None,
) -> None:
    if attr is None or attr.trust_product_id is None:
        return
    row["trust_product_id"] = attr.trust_product_id
    name = attr.trust_product_name
    if not name and name_by_id:
        name = name_by_id.get(attr.trust_product_id)
    if name:
        row["trust_product_name"] = name
