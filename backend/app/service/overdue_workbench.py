"""Overdue workbench — single read path: get_detail()."""

from sqlalchemy.engine import Engine

from app.repo.followup_repo import FollowupRepo
from app.repo.issuance_repo import IssuanceRepo
from app.repo.marks_repo import MarksRepo
from app.repo.monitor_repo import MonitorRepo
from app.repo.repayment_repo import RepaymentRepo
from app.service import checks_service
from app.service.location_service import build_location_service
from app.service.ops_service import suggest_ops
from app.overdue.buckets import matches_any_delinquency_bucket_filter
from app.issuance_upload import ISSUANCE_CITY_UNKNOWN

DEFAULT_DELINQUENCY_BUCKET = "M0_PLUS"


def _match_internal_status_filter(got: str, wants: list[str] | None) -> bool:
    if not wants:
        return True
    got_s = str(got or "")
    for want in wants:
        if want == "正常" and got_s == "正常":
            return True
        if want == "待跟进" and got_s.startswith("待跟进"):
            return True
        if want == "本周结算" and got_s.startswith("本周结算"):
            return True
        if got_s == want:
            return True
    return False


def _pick_issuance_identity_id(
    issuance_records: list[dict], trust_product_id: int
) -> int | None:
    for rec in issuance_records:
        if rec.get("trust_product_id") == trust_product_id:
            return rec.get("id")
    return issuance_records[0]["id"] if issuance_records else None


class OverdueWorkbenchService:
    def __init__(self, engine: Engine):
        self._engine = engine
        self._issuance = IssuanceRepo(engine)
        self._monitor = MonitorRepo(engine)
        self._repayment = RepaymentRepo(engine)
        self._followup = FollowupRepo(engine)
        self._marks = MarksRepo(engine)

    def resolve_asset_code(
        self,
        trust_product_id: int,
        custody_asset_code: str,
        data_date: str | None = None,
    ) -> str | None:
        return self._monitor.resolve_asset_code(
            trust_product_id, custody_asset_code, data_date
        )

    def get_detail(
        self,
        *,
        trust_product_id: int | None = None,
        asset_code: str | None = None,
        custody_asset_code: str | None = None,
        trust_asset_id: int | None = None,
        data_date: str | None = None,
    ) -> dict:
        empty = {
            "trust_product_id": trust_product_id,
            "asset_code": asset_code,
            "custody_asset_code": custody_asset_code,
            "identity_id": None,
            "data_date": data_date,
            "summary": None,
            "issuance_records": [],
            "repayment": {"total_repaid": 0.0, "items": [], "recent_repayment_date": None},
            "monitor": {"custody": None, "splits": []},
            "checks": None,
            "trust_mark": None,
            "ops": None,
            "spatial_hint": None,
            "followup_case": None,
            "timeline": [],
            "queue": [],
            "selected_asset_id": None,
            "detail": None,
        }

        resolved_asset = asset_code
        if not resolved_asset and custody_asset_code and trust_product_id is not None:
            resolved_asset = self.resolve_asset_code(
                trust_product_id, custody_asset_code, data_date
            )

        if trust_product_id is None or not resolved_asset:
            return empty

        empty["asset_code"] = resolved_asset

        resolved_date = self._monitor.resolve_latest_data_date(trust_product_id, data_date)
        if resolved_date is None:
            return empty

        splits_raw = self._monitor.fetch_splits_by_asset_code(
            trust_product_id, resolved_asset, resolved_date
        )
        custody_codes = list(
            dict.fromkeys(
                s.get("custody_asset_code")
                for s in splits_raw
                if s.get("custody_asset_code")
            )
        )

        issuance_records = self._issuance.fetch_by_primary_asset_code(resolved_asset)
        identity_id = _pick_issuance_identity_id(issuance_records, trust_product_id)

        if not splits_raw:
            empty["data_date"] = resolved_date
            empty["issuance_records"] = issuance_records
            empty["trust_mark"] = self._marks.fetch_mark(
                trust_product_id, resolved_asset, resolved_date
            )
            empty["ops"] = suggest_ops(self._engine, identity_id)
            empty["spatial_hint"] = build_location_service(self._engine).get_spatial_hint(
                trust_product_id, resolved_asset
            )
            return empty

        repayment_total = self._repayment.sum_by_product_asset_code(
            trust_product_id, resolved_asset
        )
        repayment_items = self._repayment.fetch_by_product_asset_code(
            trust_product_id, resolved_asset
        )
        from app import manual_settlement as ms

        with self._engine.connect() as _conn:
            settlements = ms.list_settlements_for_asset(
                _conn, trust_product_id, resolved_asset
            )
        settlement_sum = sum(float(s.get("amount") or 0) for s in settlements)
        repayment_items = ms.merge_repayment_items_with_settlements(
            repayment_items, settlements
        )
        repayment_total = float(repayment_total or 0) + float(settlement_sum or 0)
        code_mismatch = self._repayment.fetch_code_mismatch_summary(
            trust_product_id, resolved_asset
        )
        canonical_recent_repay = self._repayment.max_repayment_date_by_canonical_asset_code(
            trust_product_id, resolved_asset
        )

        queue = []
        for row in splits_raw:
            remaining = float(row.get("remaining_amount") or 0)
            repaid = float(row.get("repaid_amount") or 0)
            # 手工结算叠加在资产主编号汇总层；分笔行先保留事实值，custody_agg 再叠加
            is_es = checks_service.is_es_closed(remaining)
            od_val = None if is_es else int(row.get("overdue_days") or 0)
            bucket = (
                "ES"
                if is_es
                else checks_service.calc_risk_level(int(row.get("overdue_days") or 0), remaining)
            )
            checks = checks_service.run_asset_checks(
                float(row.get("initial_transfer_amount") or 0),
                repaid,
                remaining,
                repayment_total,
                code_mismatch=code_mismatch,
            )
            active = self._followup.fetch_active_by_trust_asset_id(int(row["trust_asset_id"]))
            queue.append(
                {
                    "trust_asset_id": row["trust_asset_id"],
                    "asset_code": row.get("asset_code"),
                    "custody_asset_code": row.get("custody_asset_code"),
                    "source_asset_code": row.get("source_asset_code"),
                    "asset_name": row.get("asset_name"),
                    "trust_product_id": row.get("trust_product_id"),
                    "trust_product_name": row.get("trust_product_name"),
                    "data_date": str(row.get("data_date")),
                    "overdue_days": od_val,
                    "risk_score": row.get("risk_score"),
                    "risk_level": "ES" if is_es else row.get("risk_level"),
                    "delinquency_bucket": bucket,
                    "last_payment_date": (
                        str(row["last_payment_date"]) if row.get("last_payment_date") else None
                    ),
                    "initial_transfer_amount": float(row.get("initial_transfer_amount") or 0),
                    "repaid_amount": repaid,
                    "remaining_amount": remaining,
                    "checks": checks,
                    "followup_id": active.get("id") if active else None,
                    "followup_status": active.get("status") if active else None,
                    "followup_owner": active.get("owner_name") if active else None,
                    "followup_reason": active.get("overdue_reason") if active else None,
                    "followup_plan": active.get("follow_up_plan") if active else None,
                    "followup_feedback": None,
                    "followup_last_at": active.get("last_follow_up_at") if active else None,
                    "has_follow_up": active is not None,
                }
            )

        selected_id = trust_asset_id
        if selected_id is None and queue:
            selected_id = queue[0]["trust_asset_id"]
        elif selected_id is not None and not any(q["trust_asset_id"] == selected_id for q in queue):
            selected_id = queue[0]["trust_asset_id"] if queue else None

        detail = next((q for q in queue if q["trust_asset_id"] == selected_id), None)

        fact_initial = sum(q["initial_transfer_amount"] for q in queue)
        fact_repaid = sum(q["repaid_amount"] for q in queue)
        fact_remaining = sum(q["remaining_amount"] for q in queue)
        overlay_repaid, overlay_remaining = ms.apply_amount_overlay(
            fact_repaid, fact_remaining, settlement_sum
        )
        # 核对左右两侧均含手工结算叠加，避免一侧叠加一侧不叠加产生假异常
        custody_checks = checks_service.run_asset_checks(
            fact_initial,
            overlay_repaid,
            overlay_remaining,
            repayment_total,
            code_mismatch=code_mismatch,
        )

        custody_agg = {
            "initial_transfer_amount": fact_initial,
            "repaid_amount": overlay_repaid,
            "remaining_amount": overlay_remaining,
            "overdue_days": max(
                (q["overdue_days"] for q in queue if q["overdue_days"] is not None),
                default=None,
            ),
            "split_count": len(queue),
        }
        if queue:
            remaining_sum = custody_agg["remaining_amount"]
            if checks_service.is_es_closed(remaining_sum):
                custody_agg["delinquency_bucket"] = "ES"
            else:
                raw_od = custody_agg.get("overdue_days")
                od = int(raw_od) if raw_od is not None else None
                custody_agg["delinquency_bucket"] = checks_service.calc_risk_level(
                    od,
                    remaining_sum,
                )

        recent_repay = None
        for item in repayment_items:
            rd = item.get("repayment_date")
            if rd is None:
                continue
            rd_s = str(rd).strip()[:10]
            if rd_s and (recent_repay is None or rd_s > recent_repay):
                recent_repay = rd_s
        for s in settlements:
            sd = s.get("settlement_date")
            if sd is None:
                continue
            sd_s = str(sd).strip()[:10]
            if sd_s and (recent_repay is None or sd_s > recent_repay):
                recent_repay = sd_s
        if recent_repay is None and canonical_recent_repay is not None:
            recent_repay = str(canonical_recent_repay).strip()[:10] or None

        followup_cases = self._followup.fetch_cases_by_asset_code(
            trust_product_id, resolved_asset
        )
        case_row = followup_cases[0] if followup_cases else None
        # 时间线：汇总所有事项下的 entries
        entry_list: list[dict] = []
        for c in followup_cases:
            for entry in self._followup.fetch_entries_by_case_id(int(c["id"])):
                entry_list.append(
                    {
                        **entry,
                        "case_id": int(c["id"]),
                        "case_category": c.get("category"),
                        "case_status": c.get("status"),
                    }
                )
        entry_list.sort(key=lambda e: str(e.get("created_at") or ""), reverse=True)

        entry_ids = [int(e["id"]) for e in entry_list]
        attachments = self._followup.fetch_attachments_by_entry_ids(entry_ids)
        attachments_by_entry: dict[int, list] = {}
        for att in attachments:
            attachments_by_entry.setdefault(int(att["entry_id"]), []).append(att)

        timeline = _build_timeline(
            repayment_items, entry_list, attachments_by_entry
        )
        followup_entries = []
        for entry in entry_list:
            eid = int(entry["id"])
            followup_entries.append({**entry, "attachments": attachments_by_entry.get(eid, [])})
        trust_mark = self._marks.fetch_mark(
            trust_product_id, resolved_asset, resolved_date
        )
        # 派生内部状态以 cases 为准（与 marks 对齐）
        from app.repo.followup_repo import (
            PROBLEM_CASE_STATUSES,
            format_internal_status,
        )

        problem_n = sum(
            1 for c in followup_cases if c.get("status") in PROBLEM_CASE_STATUSES
        )
        settled_n = sum(
            1 for c in followup_cases if c.get("status") == "settled_week"
        )
        derived_status = format_internal_status(problem_n, settled_n)
        if trust_mark is not None:
            trust_mark = {**trust_mark, "internal_status": derived_status}
        ops = suggest_ops(self._engine, identity_id)

        primary = detail or (queue[0] if queue else {})
        has_check_anomaly = False
        if custody_checks:
            has_check_anomaly = not (
                custody_checks["balance_equation"]["passed"]
                and custody_checks["cross_sheet_repayment"]["passed"]
                and custody_checks.get("code_mismatch", {}).get("passed", True)
            )
        summary = {
            "delinquency_bucket": custody_agg.get("delinquency_bucket")
            or primary.get("delinquency_bucket"),
            "overdue_days": custody_agg.get("overdue_days")
            if custody_agg.get("overdue_days") is not None
            else primary.get("overdue_days"),
            "risk_level": primary.get("risk_level"),
            "risk_score": primary.get("risk_score"),
            "trust_product_name": primary.get("trust_product_name"),
            "remaining_amount": custody_agg.get("remaining_amount"),
            "repaid_amount": custody_agg.get("repaid_amount"),
            "initial_transfer_amount": custody_agg.get("initial_transfer_amount"),
            "split_count": custody_agg.get("split_count"),
            "internal_status": (trust_mark or {}).get("internal_status"),
            "has_check_anomaly": has_check_anomaly,
            "last_payment_date": recent_repay,
        }

        followup_case = self._followup.fetch_case_by_asset_code(
            trust_product_id, resolved_asset, active_only=True
        ) or case_row

        last_follow_up_at = None
        last_follow_up_owner = None
        if followup_case:
            last_follow_up_at = followup_case.get("last_follow_up_at")
            last_follow_up_owner = followup_case.get("owner_name")
        if entry_list:
            if not last_follow_up_at:
                last_follow_up_at = entry_list[0].get("created_at")
            if not last_follow_up_owner:
                last_follow_up_owner = entry_list[0].get("owner_name")

        summary["last_follow_up_at"] = (
            str(last_follow_up_at) if last_follow_up_at is not None else None
        )
        summary["last_follow_up_owner"] = last_follow_up_owner

        product_queue = self.get_product_queue(trust_product_id, resolved_date)
        spatial_hint = build_location_service(self._engine).get_spatial_hint(
            trust_product_id, resolved_asset
        )

        return {
            "trust_product_id": trust_product_id,
            "asset_code": resolved_asset,
            "custody_asset_codes": custody_codes,
            "identity_id": identity_id,
            "data_date": resolved_date,
            "summary": summary,
            "issuance_records": issuance_records,
            "repayment": {
                "total_repaid": repayment_total,
                "items": repayment_items,
                "recent_repayment_date": recent_repay,
                "canonical_recent_repayment_date": canonical_recent_repay,
                "period_count": len(repayment_items),
                "code_mismatch": code_mismatch,
            },
            "monitor": {"custody": custody_agg, "splits": queue},
            "checks": custody_checks,
            "trust_mark": trust_mark,
            "ops": ops,
            "spatial_hint": spatial_hint,
            "followup_case": followup_case,
            "followup_cases": followup_cases,
            "followup_entries": followup_entries,
            "manual_settlements": settlements,
            "timeline": timeline,
            "product_queue": product_queue,
            "queue": queue,
            "selected_asset_id": selected_id,
            "detail": detail,
        }

    def _fetch_city_by_asset(
        self, pairs: list[tuple[int, str]]
    ) -> dict[tuple[int, str], str]:
        """批量取城市：发行优先，空则监控；皆无则「未知」。"""
        if not pairs:
            return {}
        from sqlalchemy import text

        unique = list(dict.fromkeys(pairs))
        city_map: dict[tuple[int, str], str] = {}
        with self._engine.connect() as conn:
            for pid, ac in unique:
                row = conn.execute(
                    text(
                        """
                        SELECT COALESCE(
                            NULLIF(TRIM(iss.city), ''),
                            NULLIF(TRIM(mon.city), ''),
                            :unknown
                        ) AS city
                        FROM (SELECT 1) AS _
                        LEFT JOIN LATERAL (
                            SELECT i.city
                            FROM trust_product_issuance_asset_records i
                            WHERE i.trust_product_id = :pid
                              AND (
                                  split_part(i.custody_asset_code, '-', 1) = :asset_code
                                  OR i.custody_asset_code = :asset_code
                              )
                            ORDER BY i.issue_date DESC NULLS LAST, i.id DESC
                            LIMIT 1
                        ) iss ON TRUE
                        LEFT JOIN LATERAL (
                            SELECT m.city
                            FROM trust_asset_monitor_records m
                            WHERE m.trust_product_id = :pid
                              AND m.asset_code = :asset_code
                            ORDER BY m.data_date DESC NULLS LAST, m.id DESC
                            LIMIT 1
                        ) mon ON TRUE
                        """
                    ),
                    {
                        "pid": pid,
                        "asset_code": ac,
                        "unknown": ISSUANCE_CITY_UNKNOWN,
                    },
                ).fetchone()
                city_map[(pid, ac)] = (
                    str(row.city) if row else ISSUANCE_CITY_UNKNOWN
                )
        return city_map

    def get_asset_list(
        self,
        *,
        trust_product_id: int | None = None,
        data_date: str | None = None,
        delinquency_bucket: str | None = None,
        delinquency_buckets: list[str] | None = None,
        trust_marker: str | None = None,
        trust_markers: list[str] | None = None,
        followup_status: str | None = None,
        followup_statuses: list[str] | None = None,
        cities: list[str] | None = None,
        trust_product_ids: list[int] | None = None,
        prefer_trust_product_id: int | None = None,
        prefer_asset_code: str | None = None,
    ) -> dict:
        """Return asset_list dict (asset_code-based) for render.py.

        trust_product_ids: None = 全部产品；非空 = 多选限定。
        delinquency_buckets / trust_markers / followup_statuses / cities:
        None = 不限；非空 = 组合筛选。
        prefer_*：当前资产主编号；若命中筛选结果，翻到其所在页（页长 limit），页内全序不变。
        """
        ids = trust_product_ids
        if ids is None and trust_product_id is not None:
            ids = [trust_product_id]
        scope_pid = ids[0] if ids and len(ids) == 1 else None
        resolved_date = self._monitor.resolve_latest_data_date(scope_pid, data_date)
        if resolved_date is None:
            return {"data_date": None, "items": []}

        buckets = delinquency_buckets
        if buckets is None and delinquency_bucket:
            buckets = [delinquency_bucket]
        markers = trust_markers
        if markers is None and trust_marker:
            markers = [trust_marker]
        statuses = followup_statuses
        if statuses is None and followup_status:
            statuses = [followup_status]

        rows = self._monitor.fetch_asset_queue(
            data_date=resolved_date,
            trust_markers=markers,
            delinquency_buckets=buckets,
            trust_product_ids=ids,
            prefer_trust_product_id=prefer_trust_product_id,
            prefer_asset_code=prefer_asset_code,
        )
        pairs = [(int(r["trust_product_id"]), str(r["asset_code"])) for r in rows]
        city_map = self._fetch_city_by_asset(pairs) if cities else {}

        from app import manual_settlement as ms

        settlement_sums: dict[tuple[int, str], float] = {}
        if rows:
            with self._engine.connect() as conn:
                settlement_sums = ms.settlement_sums_by_asset_code(
                    conn,
                    product_ids=ids,
                    asset_codes=[str(r["asset_code"]) for r in rows],
                )

        items = []
        for row in rows:
            ac = row["asset_code"]
            pid = int(row["trust_product_id"])
            custodies = list(row.get("custody_asset_codes") or [])
            remaining = float(row.get("remaining_amount") or 0)
            overdue_days = row.get("overdue_days")
            settlement_sum = float(
                settlement_sums.get((pid, str(ac).strip()), 0) or 0
            )
            if settlement_sum:
                _, remaining = ms.apply_amount_overlay(
                    row.get("repaid_amount"), remaining, settlement_sum
                )

            if checks_service.is_es_closed(remaining):
                bucket = "ES"
                overdue_days = None
            else:
                bucket = checks_service.calc_risk_level(int(overdue_days or 0), remaining)

            if not matches_any_delinquency_bucket_filter(bucket, buckets):
                continue

            followup_count = self._followup.count_entries_by_asset_code(pid, ac)
            mark = self._marks.fetch_mark(pid, ac, resolved_date)
            internal_status = mark.get("internal_status")
            trust_mark_val = mark.get("trust_marker")

            if markers and trust_mark_val not in markers:
                continue
            if not _match_internal_status_filter(internal_status or "", statuses):
                continue

            if cities:
                city_filter = city_map.get((pid, str(ac)), ISSUANCE_CITY_UNKNOWN)
                if city_filter not in cities:
                    continue
            else:
                city_filter = None

            items.append(
                {
                    "asset_code": ac,
                    "trust_product_id": pid,
                    "trust_product_name": row.get("trust_product_name"),
                    "overdue_days": overdue_days,
                    "remaining_amount": remaining,
                    "delinquency_bucket": bucket,
                    "followup_count": followup_count,
                    "internal_status": internal_status,
                    "custody_asset_codes": custodies,
                    "city": city_filter,
                }
            )
        return {"data_date": resolved_date, "items": items}

    @staticmethod
    def build_asset_panel_dto(detail: dict) -> dict:
        """Map get_detail() output to the ``asset`` slice used by render.py."""
        resolved_asset = detail.get("asset_code")
        if not resolved_asset:
            return {}
        return {
            "asset_code": resolved_asset,
            "custody_asset_codes": list(detail.get("custody_asset_codes") or []),
            "selected_trust_asset_id": detail.get("selected_asset_id"),
            "selected_split": detail.get("detail"),
            "summary": detail.get("summary"),
            "checks": detail.get("checks"),
            "issuance_records": detail.get("issuance_records") or [],
            "repayment": detail.get("repayment") or {},
            "manual_settlements": detail.get("manual_settlements") or [],
            "monitor": detail.get("monitor") or {},
            "trust_mark": detail.get("trust_mark"),
            "timeline": detail.get("timeline") or [],
            "ops": detail.get("ops"),
            "spatial_hint": detail.get("spatial_hint"),
            "followup_case": detail.get("followup_case"),
            "followup_cases": detail.get("followup_cases") or [],
            "followup_entries": detail.get("followup_entries") or [],
        }

    @staticmethod
    def _build_workbench_filters(
        *,
        trust_product_id: int | None,
        delinquency_bucket: str | None,
        delinquency_buckets: list[str] | None,
        list_product_id: int | None,
        list_product_ids: list[int] | None,
        list_product_scope_explicit: bool,
        trust_marker: str | None,
        trust_markers: list[str] | None,
        followup_status: str | None,
        followup_statuses: list[str] | None,
        cities: list[str] | None,
    ) -> tuple[dict, list[int] | None]:
        if list_product_scope_explicit:
            effective_ids = list_product_ids
            if effective_ids is None and list_product_id is not None:
                effective_ids = [list_product_id]
        else:
            effective_ids = [trust_product_id] if trust_product_id is not None else None

        buckets = delinquency_buckets
        if buckets is None and delinquency_bucket:
            buckets = [delinquency_bucket]
        markers = trust_markers
        if markers is None and trust_marker:
            markers = [trust_marker]
        statuses = followup_statuses
        if statuses is None and followup_status:
            statuses = [followup_status]

        filters = {
            "trust_product_id": trust_product_id,
            "delinquency_bucket": buckets[0] if buckets and len(buckets) == 1 else None,
            "delinquency_buckets": buckets,
            "list_product_id": list_product_id,
            "list_product_ids": effective_ids,
            "list_product_scope_explicit": list_product_scope_explicit,
            "trust_marker": markers[0] if markers and len(markers) == 1 else None,
            "trust_markers": markers,
            "followup_status": statuses[0] if statuses and len(statuses) == 1 else None,
            "followup_statuses": statuses,
            "cities": cities,
        }
        return filters, effective_ids

    def get_workbench_detail_dto(
        self,
        *,
        trust_product_id: int | None = None,
        asset_code: str | None = None,
        custody_asset_code: str | None = None,
        delinquency_bucket: str | None = None,
        delinquency_buckets: list[str] | None = None,
        data_date: str | None = None,
        list_product_id: int | None = None,
        list_product_ids: list[int] | None = None,
        list_product_scope_explicit: bool = False,
        trust_asset_id: int | None = None,
        trust_marker: str | None = None,
        trust_markers: list[str] | None = None,
        followup_status: str | None = None,
        followup_statuses: list[str] | None = None,
        cities: list[str] | None = None,
    ) -> dict:
        """Detail-only DTO for fragment refresh (no asset_list query)."""
        resolved_asset = asset_code
        if not resolved_asset and custody_asset_code and trust_product_id is not None:
            resolved_asset = self.resolve_asset_code(
                trust_product_id, custody_asset_code, data_date
            )

        filters, _effective_ids = self._build_workbench_filters(
            trust_product_id=trust_product_id,
            delinquency_bucket=delinquency_bucket,
            delinquency_buckets=delinquency_buckets,
            list_product_id=list_product_id,
            list_product_ids=list_product_ids,
            list_product_scope_explicit=list_product_scope_explicit,
            trust_marker=trust_marker,
            trust_markers=trust_markers,
            followup_status=followup_status,
            followup_statuses=followup_statuses,
            cities=cities,
        )

        old = self.get_detail(
            trust_product_id=trust_product_id,
            asset_code=resolved_asset,
            trust_asset_id=trust_asset_id,
            data_date=data_date,
        )
        asset_dict = self.build_asset_panel_dto(old)
        summary = (asset_dict.get("summary") or {}) if asset_dict else {}
        followup_entries = asset_dict.get("followup_entries") or []
        return {
            "trust_product_id": trust_product_id,
            "asset_code": resolved_asset,
            "custody_asset_codes": list(old.get("custody_asset_codes") or []),
            "identity_id": old.get("identity_id"),
            "data_date": old.get("data_date"),
            "filters": filters,
            "asset": asset_dict,
            "queue_patch": {
                "trust_product_id": trust_product_id,
                "asset_code": resolved_asset,
                "internal_status": summary.get("internal_status"),
                "followup_count": len(followup_entries),
            },
        }

    def get_workbench_page_dto(
        self,
        *,
        trust_product_id: int | None = None,
        asset_code: str | None = None,
        custody_asset_code: str | None = None,
        delinquency_bucket: str | None = None,
        delinquency_buckets: list[str] | None = None,
        data_date: str | None = None,
        list_product_id: int | None = None,
        list_product_ids: list[int] | None = None,
        list_product_scope_explicit: bool = False,
        trust_asset_id: int | None = None,
        trust_marker: str | None = None,
        trust_markers: list[str] | None = None,
        followup_status: str | None = None,
        followup_statuses: list[str] | None = None,
        cities: list[str] | None = None,
    ) -> dict:
        """Build full DTO expected by render.py (asset_code-centric)."""
        resolved_asset = asset_code
        if not resolved_asset and custody_asset_code and trust_product_id is not None:
            resolved_asset = self.resolve_asset_code(
                trust_product_id, custody_asset_code, data_date
            )

        filters, effective_ids = self._build_workbench_filters(
            trust_product_id=trust_product_id,
            delinquency_bucket=delinquency_bucket,
            delinquency_buckets=delinquency_buckets,
            list_product_id=list_product_id,
            list_product_ids=list_product_ids,
            list_product_scope_explicit=list_product_scope_explicit,
            trust_marker=trust_marker,
            trust_markers=trust_markers,
            followup_status=followup_status,
            followup_statuses=followup_statuses,
            cities=cities,
        )

        old = self.get_detail(
            trust_product_id=trust_product_id,
            asset_code=resolved_asset,
            trust_asset_id=trust_asset_id,
            data_date=data_date,
        )
        resolved_date = old.get("data_date")

        asset_list = self.get_asset_list(
            trust_product_ids=effective_ids,
            data_date=resolved_date,
            delinquency_buckets=filters.get("delinquency_buckets"),
            trust_markers=filters.get("trust_markers"),
            followup_statuses=filters.get("followup_statuses"),
            cities=cities,
            prefer_trust_product_id=trust_product_id,
            prefer_asset_code=resolved_asset,
        )

        asset_dict = self.build_asset_panel_dto(old)

        return {
            "trust_product_id": trust_product_id,
            "asset_code": resolved_asset,
            "custody_asset_codes": list(old.get("custody_asset_codes") or []),
            "identity_id": old.get("identity_id"),
            "data_date": resolved_date,
            "filters": filters,
            "asset": asset_dict,
            "asset_list": asset_list,
        }

    def get_product_queue(
        self,
        trust_product_id: int,
        data_date: str | None = None,
    ) -> dict:
        resolved_date = self._monitor.resolve_latest_data_date(trust_product_id, data_date)
        if resolved_date is None:
            return {"trust_product_id": trust_product_id, "data_date": None, "items": []}

        rows = self._monitor.fetch_custody_queue(trust_product_id, resolved_date)
        items = []
        for row in rows:
            custody = row["custody_asset_code"]
            asset_code = self.resolve_asset_code(trust_product_id, custody, resolved_date)
            if not asset_code:
                continue
            items.append(
                {
                    "custody_asset_code": custody,
                    "asset_code": asset_code,
                    "overdue_days": row.get("overdue_days"),
                    "remaining_amount": float(row.get("remaining_amount") or 0),
                    "split_count": row.get("split_count"),
                    "followup_count": self._followup.count_entries_by_asset_code(
                        trust_product_id, asset_code
                    ),
                    "internal_status": self._marks.fetch_mark(
                        trust_product_id, asset_code, resolved_date
                    ).get("internal_status"),
                }
            )
        return {
            "trust_product_id": trust_product_id,
            "data_date": resolved_date,
            "items": items,
        }


def _build_timeline(
    repayment_items: list[dict],
    entries: list[dict],
    attachments_by_entry: dict[int, list] | None = None,
) -> list[dict]:
    events: list[dict] = []
    for item in repayment_items:
        occurred = item.get("repayment_date") or item.get("synced_at") or item.get("created_at")
        events.append(
            {
                "event_type": "repayment",
                "occurred_at": occurred,
                "title": f"还款 期次 {item.get('period_no') or '—'}",
                "amount": item.get("actual_repayment_amount"),
                "period_no": item.get("period_no"),
                "source_asset_code": item.get("source_asset_code") or item.get("asset_code"),
                "custody_asset_code": item.get("custody_asset_code"),
                "legacy": False,
            }
        )
    for entry in entries:
        eid = int(entry["id"])
        entry_attachments = (attachments_by_entry or {}).get(eid, [])
        events.append(
            {
                "event_type": "followup",
                "occurred_at": entry.get("created_at"),
                "title": f"跟进 · {entry.get('case_category') or '事项'}",
                "owner_name": entry.get("owner_name"),
                "overdue_reason": entry.get("overdue_reason"),
                "follow_up_plan": entry.get("follow_up_plan"),
                "entry_type": entry.get("entry_type"),
                "entry_id": eid,
                "case_id": entry.get("case_id"),
                "attachments": entry_attachments,
                "legacy": False,
            }
        )
    events.sort(key=lambda e: str(e.get("occurred_at") or ""), reverse=True)
    return events


def build_overdue_workbench_service(engine: Engine) -> OverdueWorkbenchService:
    return OverdueWorkbenchService(engine)
