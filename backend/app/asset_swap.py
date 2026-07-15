"""资产置换推荐 — 只读查询与组合算法（不写库）."""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app import assetinfo_upload as au
from app.issuance_labels import format_rate
from app.overdue.buckets import (
    DELINQUENCY_BUCKET_LABELS,
    RECONCILIATION_TOLERANCE_DEFAULT,
    calc_delinquency_bucket,
    sql_m1_filter,
)

MEIRUN_PRODUCT_NAME = "美润1号"
MEIHAOSHENG_NAME_PREFIX = "美好生活"
MAX_SOURCE_ASSETS = 20
MAX_EXCLUDE_ASSETS = 50
N_MAX = 5
MAX_REQUIRED_ASSETS = N_MAX
POOL_CAP = 500
SEARCH_POOL_CAP = 80
RATE_EPS = 1e-6
# 自动候选池未付天数上限（必选房源仍可超过，仅提示）
SWAP_CANDIDATE_MAX_OVERDUE_DAYS = 25

TOLERANCE = RECONCILIATION_TOLERANCE_DEFAULT


def parse_asset_code_list(
    raw: str | list[str] | None,
    *,
    max_count: int,
    field_label: str = "资产编号",
) -> list[str]:
    if raw is None:
        return []
    parts: list[str]
    if isinstance(raw, list):
        parts = [str(p) for p in raw]
    else:
        parts = re.split(r"[\s,，;；]+", str(raw).strip())
    seen: set[str] = set()
    result: list[str] = []
    for part in parts:
        code = part.strip()
        if not code or code in seen:
            continue
        seen.add(code)
        result.append(code)
    if len(result) > max_count:
        raise HTTPException(
            status_code=400,
            detail=f"{field_label}最多 {max_count} 个",
        )
    return result


def fetch_meihaosheng_products(conn: Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        text("""
            SELECT id, name
            FROM trust_products
            WHERE name LIKE :prefix
            ORDER BY id
        """),
        {"prefix": f"{MEIHAOSHENG_NAME_PREFIX}%"},
    )
    return [{"id": int(r.id), "name": str(r.name)} for r in rows]


def resolve_meirun_product_id(conn: Connection) -> int:
    row = conn.execute(
        text("SELECT id FROM trust_products WHERE name = :name LIMIT 1"),
        {"name": MEIRUN_PRODUCT_NAME},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=500, detail=f"未找到信托产品「{MEIRUN_PRODUCT_NAME}」")
    return int(row.id)


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = (next_month - date(year, month, 1)).days
    return date(year, month, min(value.day, last_day))


def _parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text_val = str(value).strip()[:10]
    if not text_val:
        return None
    return date.fromisoformat(text_val)


@dataclass
class SourceAsset:
    asset_code: str
    issue_date: date
    remaining_amount: float
    asset_transfer_discount_rate: float
    renovation_deadline: date
    city: str | None = None


@dataclass
class Candidate:
    asset_code: str
    custody_asset_code: str
    remaining_amount: float
    asset_transfer_discount_rate: float
    last_renovation_payment_date: date
    data_date: date
    city: str | None
    delinquency_bucket: str
    overdue_days: int

    def to_dict(self) -> dict[str, Any]:
        bucket_label = DELINQUENCY_BUCKET_LABELS.get(
            self.delinquency_bucket,
            self.delinquency_bucket,
        )
        return {
            "asset_code": self.asset_code,
            "custody_asset_code": self.custody_asset_code,
            "remaining_amount": self.remaining_amount,
            "asset_transfer_discount_rate": self.asset_transfer_discount_rate,
            "asset_transfer_discount_rate_display": format_rate(
                self.asset_transfer_discount_rate
            ),
            "last_renovation_payment_date": self.last_renovation_payment_date.isoformat(),
            "data_date": self.data_date.isoformat(),
            "city": self.city or "—",
            "delinquency_bucket": self.delinquency_bucket,
            "overdue_days": self.overdue_days,
            "delinquency_bucket_display": f"{bucket_label} · {self.overdue_days}天",
        }


def _issuance_lateral_join_sql(select_fields: str) -> str:
    return f"""
        LEFT JOIN LATERAL (
            SELECT {select_fields}
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


def _fetch_source_asset(
    conn: Connection,
    trust_product_id: int,
    asset_code: str,
) -> SourceAsset:
    row = conn.execute(
        text(f"""
            SELECT
                r.asset_code,
                r.remaining_amount,
                iss.issue_date,
                iss.asset_transfer_discount_rate,
                iss.city
            FROM trust_asset_monitor_records r
            {au._monitor_latest_snapshot_join_sql()}
            {_issuance_lateral_join_sql("i.issue_date, i.asset_transfer_discount_rate, i.city")}
            WHERE r.trust_product_id = :trust_product_id
              AND r.asset_code = :asset_code
            LIMIT 1
        """),
        {"trust_product_id": trust_product_id, "asset_code": asset_code},
    ).fetchone()
    if not row:
        raise HTTPException(
            status_code=400,
            detail=f"资产 {asset_code} 在所选产品下无监控快照",
        )
    remaining = float(row.remaining_amount or 0)
    if remaining <= TOLERANCE:
        raise HTTPException(
            status_code=400,
            detail=f"资产 {asset_code} 已结清或剩余为 0",
        )
    issue_date = _parse_date(row.issue_date)
    if issue_date is None:
        raise HTTPException(
            status_code=400,
            detail=f"资产 {asset_code} 无发行记录",
        )
    rate = row.asset_transfer_discount_rate
    if rate is None:
        raise HTTPException(
            status_code=400,
            detail=f"资产 {asset_code} 发行折扣率未录入",
        )
    return SourceAsset(
        asset_code=str(row.asset_code),
        issue_date=issue_date,
        remaining_amount=remaining,
        asset_transfer_discount_rate=float(rate),
        renovation_deadline=_add_months(issue_date, 36),
        city=str(row.city).strip() if getattr(row, "city", None) else None,
    )


def _build_exclude_set(
    source_codes: list[str],
    manual_exclude: list[str],
) -> tuple[set[str], list[str], list[str]]:
    from_source = list(dict.fromkeys(source_codes))
    manual = [c for c in manual_exclude if c not in set(from_source)]
    effective = list(dict.fromkeys(from_source + manual))
    return set(effective), from_source, manual


def _transferred_out_filter_sql(meirun_product_id: int) -> str:
    custody_match = au._monitor_custody_norm_match_sql(
        "i.custody_asset_code",
        "COALESCE(r.custody_asset_code, r.asset_code, '')",
    )
    return f"""
        NOT EXISTS (
            SELECT 1
            FROM trust_product_issuance_asset_records i
            WHERE i.migration_type = 'transfer'
              AND i.from_trust_product_id = {int(meirun_product_id)}
              AND {custody_match}
        )
    """


def fetch_candidates(
    conn: Connection,
    meirun_product_id: int,
    *,
    renovation_deadline: date,
    exclude_codes: set[str],
) -> list[Candidate]:
    where_parts = [
        "r.trust_product_id = :meirun_product_id",
        f"r.remaining_amount > {TOLERANCE}",
        sql_m1_filter("r.overdue_days", "r.remaining_amount"),
        f"COALESCE(r.overdue_days, 0) <= {SWAP_CANDIDATE_MAX_OVERDUE_DAYS}",
        "r.last_renovation_payment_date IS NOT NULL",
        "r.last_renovation_payment_date <= :renovation_deadline",
        "iss.asset_transfer_discount_rate IS NOT NULL",
        _transferred_out_filter_sql(meirun_product_id),
    ]
    params: dict[str, Any] = {
        "meirun_product_id": meirun_product_id,
        "renovation_deadline": renovation_deadline,
        "tolerance": TOLERANCE,
    }
    if exclude_codes:
        placeholders = ", ".join(f":ex_{i}" for i in range(len(exclude_codes)))
        where_parts.append(f"r.asset_code NOT IN ({placeholders})")
        for i, code in enumerate(sorted(exclude_codes)):
            params[f"ex_{i}"] = code

    where_sql = " AND ".join(where_parts)
    rows = conn.execute(
        text(f"""
            SELECT
                r.asset_code,
                r.custody_asset_code,
                r.remaining_amount,
                r.overdue_days,
                r.last_renovation_payment_date,
                r.data_date,
                iss.asset_transfer_discount_rate,
                iss.city
            FROM trust_asset_monitor_records r
            {au._monitor_latest_snapshot_join_sql()}
            {au._monitor_issuance_lateral_join_sql()}
            WHERE {where_sql}
            ORDER BY r.remaining_amount DESC
        """),
        params,
    )
    candidates: list[Candidate] = []
    for row in rows:
        remaining = float(row.remaining_amount or 0)
        rate = float(row.asset_transfer_discount_rate)
        reno = _parse_date(row.last_renovation_payment_date)
        data_dt = _parse_date(row.data_date)
        if reno is None or data_dt is None:
            continue
        od = int(row.overdue_days or 0)
        bucket = calc_delinquency_bucket(od, remaining, tolerance=TOLERANCE)
        if bucket != "M1":
            continue
        if od > SWAP_CANDIDATE_MAX_OVERDUE_DAYS:
            continue
        candidates.append(
            Candidate(
                asset_code=str(row.asset_code),
                custody_asset_code=str(row.custody_asset_code or ""),
                remaining_amount=remaining,
                asset_transfer_discount_rate=rate,
                last_renovation_payment_date=reno,
                data_date=data_dt,
                city=str(row.city).strip() if row.city else None,
                delinquency_bucket=bucket,
                overdue_days=od,
            )
        )
    if len(candidates) > POOL_CAP:
        raise HTTPException(
            status_code=400,
            detail=f"候选资产超过 {POOL_CAP} 条，请增加排除条件后重试",
        )
    return candidates


def _is_asset_transferred_out(
    conn: Connection,
    meirun_product_id: int,
    asset_code: str,
    custody_asset_code: str,
) -> bool:
    custody_match = au._monitor_custody_norm_match_sql(
        "i.custody_asset_code",
        ":custody_norm",
    )
    row = conn.execute(
        text(f"""
            SELECT 1
            FROM trust_product_issuance_asset_records i
            WHERE i.migration_type = 'transfer'
              AND i.from_trust_product_id = :meirun_product_id
              AND {custody_match}
            LIMIT 1
        """),
        {
            "meirun_product_id": meirun_product_id,
            "custody_norm": custody_asset_code or asset_code,
        },
    ).fetchone()
    return row is not None


def _row_to_candidate(row) -> Candidate | None:
    remaining = float(row.remaining_amount or 0)
    rate_raw = row.asset_transfer_discount_rate
    reno = _parse_date(row.last_renovation_payment_date)
    data_dt = _parse_date(row.data_date)
    if rate_raw is None or reno is None or data_dt is None:
        return None
    od = int(row.overdue_days or 0)
    bucket = calc_delinquency_bucket(od, remaining, tolerance=TOLERANCE)
    return Candidate(
        asset_code=str(row.asset_code),
        custody_asset_code=str(row.custody_asset_code or ""),
        remaining_amount=remaining,
        asset_transfer_discount_rate=float(rate_raw),
        last_renovation_payment_date=reno,
        data_date=data_dt,
        city=str(row.city).strip() if row.city else None,
        delinquency_bucket=bucket,
        overdue_days=od,
    )


def _required_asset_ineligibility_reason(
    *,
    remaining: float,
    overdue_days: int,
    delinquency_bucket: str,
    last_renovation_payment_date: date | None,
    discount_rate: float | None,
    transferred: bool,
    renovation_deadline: date,
) -> str | None:
    if transferred:
        return "已从美润1号转出"
    if remaining <= TOLERANCE:
        return "已结清或剩余还款为 0"
    if delinquency_bucket != "M1":
        label = DELINQUENCY_BUCKET_LABELS.get(
            delinquency_bucket,
            delinquency_bucket,
        )
        if delinquency_bucket == "ES":
            return f"非 M1（{label}）"
        return f"非 M1（{label}，未付 {overdue_days} 天，仅接受 M1）"
    if last_renovation_payment_date is None:
        return "缺少装修款截止日"
    if last_renovation_payment_date > renovation_deadline:
        return (
            f"装修款截止日 {last_renovation_payment_date.isoformat()} "
            f"晚于转出要求 {renovation_deadline.isoformat()}"
        )
    if discount_rate is None:
        return "发行折扣率未录入"
    return None


def _fetch_meirun_asset_snapshot(
    conn: Connection,
    meirun_product_id: int,
    asset_code: str,
):
    return conn.execute(
        text(f"""
            SELECT
                r.asset_code,
                r.custody_asset_code,
                r.remaining_amount,
                r.overdue_days,
                r.last_renovation_payment_date,
                r.data_date,
                iss.asset_transfer_discount_rate,
                iss.city
            FROM trust_asset_monitor_records r
            {au._monitor_latest_snapshot_join_sql()}
            {au._monitor_issuance_lateral_join_sql()}
            WHERE r.trust_product_id = :meirun_product_id
              AND r.asset_code = :asset_code
            LIMIT 1
        """),
        {"meirun_product_id": meirun_product_id, "asset_code": asset_code},
    ).fetchone()


def resolve_required_candidates(
    conn: Connection,
    meirun_product_id: int,
    required_codes: list[str],
    *,
    renovation_deadline: date,
) -> list[Candidate]:
    pinned: list[Candidate] = []
    errors: list[str] = []
    for code in required_codes:
        row = _fetch_meirun_asset_snapshot(conn, meirun_product_id, code)
        if row is None:
            errors.append(f"{code}：在美润1号下无监控快照")
            continue
        remaining = float(row.remaining_amount or 0)
        od = int(row.overdue_days or 0)
        bucket = calc_delinquency_bucket(od, remaining, tolerance=TOLERANCE)
        reno = _parse_date(row.last_renovation_payment_date)
        rate = (
            float(row.asset_transfer_discount_rate)
            if row.asset_transfer_discount_rate is not None
            else None
        )
        transferred = _is_asset_transferred_out(
            conn,
            meirun_product_id,
            str(row.asset_code),
            str(row.custody_asset_code or row.asset_code),
        )
        reason = _required_asset_ineligibility_reason(
            remaining=remaining,
            overdue_days=od,
            delinquency_bucket=bucket,
            last_renovation_payment_date=reno,
            discount_rate=rate,
            transferred=transferred,
            renovation_deadline=renovation_deadline,
        )
        if reason:
            errors.append(f"{code}：{reason}")
            continue
        cand = _row_to_candidate(row)
        if cand is None:
            errors.append(f"{code}：数据不完整，无法作为候选")
        else:
            pinned.append(cand)
    if errors:
        detail = "手工指定房源不符合条件：\n" + "\n".join(errors)
        raise HTTPException(status_code=400, detail=detail)
    return pinned


def _rate_tier(rate: float, k0: float) -> int:
    if abs(rate - k0) < RATE_EPS:
        return 0
    return 1


def _combo_weighted_cost(combo: list[Candidate]) -> float:
    return sum(c.remaining_amount * c.asset_transfer_discount_rate for c in combo)


def _priority_sort_candidates(candidates: list[Candidate], k0: float) -> list[Candidate]:
    return sorted(
        candidates,
        key=lambda c: (
            _rate_tier(c.asset_transfer_discount_rate, k0),
            c.asset_transfer_discount_rate,
            c.remaining_amount,
        ),
    )


def _greedy_sort_candidates(candidates: list[Candidate], k0: float) -> list[Candidate]:
    return sorted(
        candidates,
        key=lambda c: (
            _rate_tier(c.asset_transfer_discount_rate, k0),
            c.asset_transfer_discount_rate,
            -c.remaining_amount,
        ),
    )


def _combo_sort_key(combo: list[Candidate], r0: float, c0: float) -> tuple:
    total = sum(c.remaining_amount for c in combo)
    surplus = total - r0
    weighted = _combo_weighted_cost(combo)
    cost_delta = abs(weighted - c0)
    max_rate = max(c.asset_transfer_discount_rate for c in combo)
    return (len(combo), surplus, cost_delta, max_rate, weighted)


def _combo_to_dict(
    combo: list[Candidate],
    r0: float,
    c0: float,
    *,
    rank: int,
    required_codes: set[str] | None = None,
) -> dict[str, Any]:
    req = required_codes or set()
    total = sum(c.remaining_amount for c in combo)
    weighted = _combo_weighted_cost(combo)
    return {
        "rank": rank,
        "asset_count": len(combo),
        "total_remaining": total,
        "surplus": round(total - r0, 2),
        "weighted_cost": round(weighted, 2),
        "cost_delta": round(abs(weighted - c0), 2),
        "assets": [
            {**c.to_dict(), "pinned": c.asset_code in req}
            for c in sorted(combo, key=lambda x: x.remaining_amount)
        ],
    }


def _pinned_remaining_total(pinned: list[Candidate]) -> float:
    return sum(c.remaining_amount for c in pinned)


def _enumerate_combos_with_pinned(
    pool: list[Candidate],
    pinned: list[Candidate],
    r0: float,
    n_extra: int,
) -> list[list[Candidate]]:
    if n_extra == 0:
        if _pinned_remaining_total(pinned) >= r0 - TOLERANCE:
            return [list(pinned)]
        return []
    if len(pool) < n_extra:
        return []
    r0_sub = r0 - _pinned_remaining_total(pinned)
    if r0_sub <= TOLERANCE:
        return [list(pinned)]
    sub_combos = _enumerate_combos(pool, r0_sub, n_extra)
    return [pinned + sub for sub in sub_combos]


def _enumerate_combos(
    pool: list[Candidate],
    r0: float,
    n: int,
) -> list[list[Candidate]]:
    if n == 1:
        return [[c] for c in pool if c.remaining_amount > r0]
    if len(pool) < n:
        return []
    result: list[list[Candidate]] = []
    for combo in itertools.combinations(pool, n):
        items = list(combo)
        if sum(c.remaining_amount for c in items) >= r0:
            result.append(items)
    return result


def scheme_a_combinations(
    candidates: list[Candidate],
    r0: float,
    c0: float,
    k0: float,
    *,
    pinned: list[Candidate] | None = None,
    required_codes: set[str] | None = None,
    limit: int = 3,
) -> tuple[list[dict[str, Any]], int | None]:
    pinned = pinned or []
    req = required_codes or {c.asset_code for c in pinned}
    pool = _priority_sort_candidates(candidates, k0)[:SEARCH_POOL_CAP]
    p_count = len(pinned)
    if p_count > N_MAX:
        return [], None
    if _pinned_remaining_total(pinned) >= r0 - TOLERANCE:
        return [_combo_to_dict(pinned, r0, c0, rank=1, required_codes=req)], p_count
    for n_extra in range(1, N_MAX - p_count + 1):
        combos = _enumerate_combos_with_pinned(pool, pinned, r0, n_extra)
        if not combos:
            continue
        combos.sort(key=lambda c: _combo_sort_key(c, r0, c0))
        return [
            _combo_to_dict(c, r0, c0, rank=i + 1, required_codes=req)
            for i, c in enumerate(combos[:limit])
        ], p_count + n_extra
    return [], None


def scheme_b_combinations(
    candidates: list[Candidate],
    r0: float,
    c0: float,
    k0: float,
    *,
    pinned: list[Candidate] | None = None,
    required_codes: set[str] | None = None,
) -> list[dict[str, Any]]:
    pinned = list(pinned or [])
    req = required_codes or {c.asset_code for c in pinned}
    pool = _greedy_sort_candidates(candidates, k0)
    selected: list[Candidate] = list(pinned)
    total = _pinned_remaining_total(pinned)
    for c in pool:
        if total >= r0 - TOLERANCE:
            break
        selected.append(c)
        total += c.remaining_amount
    if total < r0 - TOLERANCE:
        return []

    def improve(current: list[Candidate]) -> list[Candidate]:
        best = list(current)
        pinned_codes = {c.asset_code for c in pinned}
        for idx, old in enumerate(best):
            if old.asset_code in pinned_codes:
                continue
            for cand in pool:
                if cand.asset_code == old.asset_code:
                    continue
                if cand.asset_code in pinned_codes:
                    continue
                trial = list(best)
                trial[idx] = cand
                trial_total = sum(c.remaining_amount for c in trial)
                if trial_total >= r0 - TOLERANCE and _combo_sort_key(
                    trial, r0, c0
                ) < _combo_sort_key(best, r0, c0):
                    best = trial
        return best

    primary = improve(selected)
    variants: list[list[Candidate]] = [primary]

    if len(primary) > 1:
        pinned_codes = {c.asset_code for c in pinned}
        for drop_idx in range(len(primary)):
            if primary[drop_idx].asset_code in pinned_codes:
                continue
            subset = [c for i, c in enumerate(primary) if i != drop_idx]
            sub_total = sum(c.remaining_amount for c in subset)
            if sub_total >= r0 - TOLERANCE:
                variants.append(subset)

    seen: set[tuple[str, ...]] = set()
    results: list[dict[str, Any]] = []
    for combo in sorted(variants, key=lambda c: _combo_sort_key(c, r0, c0)):
        key = tuple(sorted(c.asset_code for c in combo))
        if key in seen:
            continue
        seen.add(key)
        results.append(
            _combo_to_dict(combo, r0, c0, rank=len(results) + 1, required_codes=req)
        )
        if len(results) >= 3:
            break
    return results


def scheme_c_combinations(
    candidates: list[Candidate],
    r0: float,
    c0: float,
    k0: float,
    *,
    pinned: list[Candidate] | None = None,
    required_codes: set[str] | None = None,
) -> dict[str, Any]:
    pinned = pinned or []
    req = required_codes or {c.asset_code for c in pinned}
    pool = _priority_sort_candidates(candidates, k0)[:SEARCH_POOL_CAP]
    p_count = len(pinned)
    empty = {"c1_min_count": None, "c2_min_surplus": None, "c3_best_cost_match": None}

    if _pinned_remaining_total(pinned) >= r0 - TOLERANCE and p_count <= N_MAX:
        only = _combo_to_dict(pinned, r0, c0, rank=1, required_codes=req)
        return {
            "c1_min_count": only,
            "c2_min_surplus": only,
            "c3_best_cost_match": only,
        }

    all_feasible: list[list[Candidate]] = []
    for n_total in range(max(1, p_count), N_MAX + 1):
        n_extra = n_total - p_count
        sub_pool = pool if n_total <= 3 else pool[:50]
        all_feasible.extend(
            _enumerate_combos_with_pinned(sub_pool, pinned, r0, n_extra)
        )

    if not all_feasible:
        return empty

    c1 = min(all_feasible, key=lambda c: _combo_sort_key(c, r0, c0))

    n3_pool = [c for c in all_feasible if len(c) <= 3]
    c2 = min(n3_pool, key=lambda c: _combo_sort_key(c, r0, c0)) if n3_pool else c1

    c3 = min(
        all_feasible,
        key=lambda c: (
            abs(_combo_weighted_cost(c) - c0),
            _combo_sort_key(c, r0, c0),
        ),
    )

    return {
        "c1_min_count": _combo_to_dict(c1, r0, c0, rank=1, required_codes=req),
        "c2_min_surplus": _combo_to_dict(c2, r0, c0, rank=1, required_codes=req),
        "c3_best_cost_match": _combo_to_dict(c3, r0, c0, rank=1, required_codes=req),
    }


def fetch_swap_recommendations(
    conn: Connection,
    *,
    trust_product_id: int,
    asset_codes: list[str],
    exclude_asset_codes: list[str] | None = None,
    required_asset_codes: list[str] | None = None,
    limit: int = 3,
) -> dict[str, Any]:
    if not asset_codes:
        raise HTTPException(status_code=400, detail="请至少输入一个资产主编号")

    product_row = conn.execute(
        text("SELECT id, name FROM trust_products WHERE id = :id"),
        {"id": trust_product_id},
    ).fetchone()
    if not product_row:
        raise HTTPException(status_code=400, detail="信托产品不存在")
    product_name = str(product_row.name)
    if not product_name.startswith(MEIHAOSHENG_NAME_PREFIX):
        raise HTTPException(status_code=400, detail="仅支持美好生活系列信托产品")

    source_assets = [
        _fetch_source_asset(conn, trust_product_id, code) for code in asset_codes
    ]
    r0 = sum(a.remaining_amount for a in source_assets)
    c0 = sum(a.remaining_amount * a.asset_transfer_discount_rate for a in source_assets)
    k0 = max(a.asset_transfer_discount_rate for a in source_assets)
    renovation_deadline = min(a.renovation_deadline for a in source_assets)

    exclude_manual = parse_asset_code_list(
        exclude_asset_codes,
        max_count=MAX_EXCLUDE_ASSETS,
        field_label="排除资产编号",
    )
    required_parsed = parse_asset_code_list(
        required_asset_codes,
        max_count=MAX_REQUIRED_ASSETS,
        field_label="手工指定房源",
    )
    if len(required_parsed) > N_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"手工指定房源最多 {N_MAX} 个",
        )
    overlap = set(required_parsed) & set(exclude_manual)
    if overlap:
        joined = "、".join(sorted(overlap)[:5])
        raise HTTPException(
            status_code=400,
            detail=f"以下编号不能同时指定与排除：{joined}",
        )
    exclude_set, from_source, manual = _build_exclude_set(asset_codes, exclude_manual)
    required_set = set(required_parsed)
    overlap_exclude = required_set & exclude_set
    if overlap_exclude:
        joined = "、".join(sorted(overlap_exclude)[:5])
        raise HTTPException(
            status_code=400,
            detail=f"以下编号不能同时指定与排除：{joined}",
        )

    meirun_id = resolve_meirun_product_id(conn)
    candidates = fetch_candidates(
        conn,
        meirun_id,
        renovation_deadline=renovation_deadline,
        exclude_codes=exclude_set,
    )

    pinned: list[Candidate] = []
    free_pool = candidates
    if required_parsed:
        pinned = resolve_required_candidates(
            conn,
            meirun_id,
            required_parsed,
            renovation_deadline=renovation_deadline,
        )
        pinned_set = {c.asset_code for c in pinned}
        free_pool = [c for c in candidates if c.asset_code not in pinned_set]

    req_codes = set(required_parsed)
    combos_a, min_n = scheme_a_combinations(
        free_pool, r0, c0, k0, pinned=pinned, required_codes=req_codes, limit=limit
    )
    combos_b = scheme_b_combinations(
        free_pool, r0, c0, k0, pinned=pinned, required_codes=req_codes
    )
    scheme_c = scheme_c_combinations(
        free_pool, r0, c0, k0, pinned=pinned, required_codes=req_codes
    )

    return {
        "source": {
            "trust_product_id": trust_product_id,
            "trust_product_name": product_name,
            "asset_count": len(source_assets),
            "assets": [
                {
                    "asset_code": a.asset_code,
                    "issue_date": a.issue_date.isoformat(),
                    "city": a.city or "—",
                    "remaining_amount": a.remaining_amount,
                    "asset_transfer_discount_rate": a.asset_transfer_discount_rate,
                    "asset_transfer_discount_rate_display": format_rate(
                        a.asset_transfer_discount_rate
                    ),
                    "renovation_deadline": a.renovation_deadline.isoformat(),
                }
                for a in source_assets
            ],
            "total_remaining": round(r0, 2),
            "reference_weighted_cost": round(c0, 2),
            "reference_discount_rate": k0,
            "reference_discount_rate_display": format_rate(k0),
            "renovation_deadline": renovation_deadline.isoformat(),
        },
        "exclude": {
            "from_source": from_source,
            "manual": manual,
            "effective": sorted(exclude_set),
        },
        "required": {
            "asset_codes": required_parsed,
            "asset_count": len(pinned),
            "total_remaining": round(_pinned_remaining_total(pinned), 2),
            "assets": [
                {**c.to_dict(), "pinned": True} for c in pinned
            ],
            "overdue_warnings": [
                (
                    f"{c.asset_code}：未付天数 {c.overdue_days} 天，"
                    f"超过 {SWAP_CANDIDATE_MAX_OVERDUE_DAYS} 天"
                )
                for c in pinned
                if c.overdue_days > SWAP_CANDIDATE_MAX_OVERDUE_DAYS
            ],
        },
        "schemes": {
            "a": {
                "scheme_id": "a",
                "scheme_label": "最少户数（分层枚举）",
                "min_asset_count": min_n,
                "combinations": combos_a,
            },
            "b": {
                "scheme_id": "b",
                "scheme_label": "启发式贪心",
                "combinations": combos_b,
            },
            "c": {
                "scheme_id": "c",
                "scheme_label": "多视角推荐",
                **scheme_c,
            },
        },
        "meta": {
            "target_product_id": meirun_id,
            "target_product_name": MEIRUN_PRODUCT_NAME,
            "candidate_pool_size": len(candidates),
            "n_max": N_MAX,
            "pool_cap": POOL_CAP,
            "candidate_max_overdue_days": SWAP_CANDIDATE_MAX_OVERDUE_DAYS,
        },
    }
