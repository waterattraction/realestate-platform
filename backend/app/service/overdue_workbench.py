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
from app.overdue.buckets import matches_delinquency_bucket_filter

DEFAULT_DELINQUENCY_BUCKET = "M2_PLUS"


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
        code_mismatch = self._repayment.fetch_code_mismatch_summary(
            trust_product_id, resolved_asset
        )
        canonical_recent_repay = self._repayment.max_repayment_date_by_canonical_asset_code(
            trust_product_id, resolved_asset
        )

        queue = []
        for row in splits_raw:
            remaining = float(row.get("remaining_amount") or 0)
            is_es = checks_service.is_es_closed(remaining)
            od_val = None if is_es else int(row.get("overdue_days") or 0)
            bucket = (
                "ES"
                if is_es
                else checks_service.calc_risk_level(int(row.get("overdue_days") or 0), remaining)
            )
            checks = checks_service.run_asset_checks(
                float(row.get("initial_transfer_amount") or 0),
                float(row.get("repaid_amount") or 0),
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
                    "repaid_amount": float(row.get("repaid_amount") or 0),
                    "remaining_amount": remaining,
                    "checks": checks,
                    "followup_id": active.get("id") if active else None,
                    "followup_status": active.get("status") if active else None,
                    "followup_owner": active.get("owner_name") if active else None,
                    "followup_reason": active.get("overdue_reason") if active else None,
                    "followup_plan": active.get("follow_up_plan") if active else None,
                    "followup_feedback": active.get("trust_feedback") if active else None,
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

        custody_checks = checks_service.run_custody_checks(
            queue, repayment_total, code_mismatch=code_mismatch
        )

        custody_agg = {
            "initial_transfer_amount": sum(q["initial_transfer_amount"] for q in queue),
            "repaid_amount": sum(q["repaid_amount"] for q in queue),
            "remaining_amount": sum(q["remaining_amount"] for q in queue),
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
                custody_agg["delinquency_bucket"] = checks_service.calc_risk_level(
                    int(custody_agg["overdue_days"] or 0),
                    remaining_sum,
                )

        recent_repay = canonical_recent_repay
        if recent_repay is None and repayment_items:
            recent_repay = repayment_items[0].get("repayment_date")
            if recent_repay is not None:
                recent_repay = str(recent_repay)

        case_row = self._followup.fetch_case_by_asset_code(
            trust_product_id, resolved_asset, active_only=False
        )
        entry_list: list[dict] = []
        if case_row:
            entry_list = self._followup.fetch_entries_by_case_id(int(case_row["id"]))

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
            "last_payment_date": canonical_recent_repay,
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
            "followup_entries": followup_entries,
            "timeline": timeline,
            "product_queue": product_queue,
            "queue": queue,
            "selected_asset_id": selected_id,
            "detail": detail,
        }

    def get_asset_list(
        self,
        *,
        trust_product_id: int | None,
        data_date: str | None = None,
        delinquency_bucket: str = DEFAULT_DELINQUENCY_BUCKET,
        trust_marker: str | None = None,
        followup_status: str | None = None,
    ) -> dict:
        """Return asset_list dict (asset_code-based) for render.py."""
        resolved_date = self._monitor.resolve_latest_data_date(trust_product_id, data_date)
        if resolved_date is None:
            return {"data_date": None, "items": []}

        rows = self._monitor.fetch_asset_queue(
            trust_product_id,
            resolved_date,
            trust_marker=trust_marker,
            followup_status=followup_status,
            delinquency_bucket=delinquency_bucket or DEFAULT_DELINQUENCY_BUCKET,
        )
        items = []
        for row in rows:
            ac = row["asset_code"]
            pid = row["trust_product_id"]
            custodies = list(row.get("custody_asset_codes") or [])
            remaining = float(row.get("remaining_amount") or 0)
            overdue_days = row.get("overdue_days")

            if checks_service.is_es_closed(remaining):
                bucket = "ES"
            else:
                bucket = checks_service.calc_risk_level(int(overdue_days or 0), remaining)

            if not matches_delinquency_bucket_filter(bucket, delinquency_bucket):
                continue

            followup_count = self._followup.count_entries_by_asset_code(pid, ac)
            mark = self._marks.fetch_mark(pid, ac, resolved_date)
            internal_status = mark.get("internal_status")

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
                }
            )
        return {"data_date": resolved_date, "items": items}

    def get_workbench_page_dto(
        self,
        *,
        trust_product_id: int | None = None,
        asset_code: str | None = None,
        custody_asset_code: str | None = None,
        delinquency_bucket: str = "M2_PLUS",
        data_date: str | None = None,
        list_product_id: int | None = None,
        list_product_scope_explicit: bool = False,
        trust_asset_id: int | None = None,
        trust_marker: str | None = None,
        followup_status: str | None = None,
    ) -> dict:
        """Build full DTO expected by render.py (asset_code-centric)."""
        resolved_asset = asset_code
        if not resolved_asset and custody_asset_code and trust_product_id is not None:
            resolved_asset = self.resolve_asset_code(
                trust_product_id, custody_asset_code, data_date
            )

        filters = {
            "trust_product_id": trust_product_id,
            "delinquency_bucket": delinquency_bucket,
            "list_product_id": list_product_id,
            "list_product_scope_explicit": list_product_scope_explicit,
            "trust_marker": trust_marker,
            "followup_status": followup_status,
        }

        old = self.get_detail(
            trust_product_id=trust_product_id,
            asset_code=resolved_asset,
            trust_asset_id=trust_asset_id,
            data_date=data_date,
        )
        resolved_date = old.get("data_date")

        list_pid = list_product_id if list_product_scope_explicit else trust_product_id

        asset_list = self.get_asset_list(
            trust_product_id=list_pid,
            data_date=resolved_date,
            delinquency_bucket=delinquency_bucket,
            trust_marker=trust_marker,
            followup_status=followup_status,
        )

        custody_codes = list(old.get("custody_asset_codes") or [])

        asset_dict: dict = {}
        if resolved_asset:
            asset_dict = {
                "asset_code": resolved_asset,
                "custody_asset_codes": custody_codes,
                "selected_trust_asset_id": old.get("selected_asset_id"),
                "selected_split": old.get("detail"),
                "summary": old.get("summary"),
                "checks": old.get("checks"),
                "issuance_records": old.get("issuance_records") or [],
                "repayment": old.get("repayment") or {},
                "monitor": old.get("monitor") or {},
                "trust_mark": old.get("trust_mark"),
                "timeline": old.get("timeline") or [],
                "ops": old.get("ops"),
                "followup_case": old.get("followup_case"),
                "followup_entries": old.get("followup_entries") or [],
            }

        return {
            "trust_product_id": trust_product_id,
            "asset_code": resolved_asset,
            "custody_asset_codes": custody_codes,
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
                "title": f"跟进 · {entry.get('status_snapshot') or '—'}",
                "status_snapshot": entry.get("status_snapshot"),
                "owner_name": entry.get("owner_name"),
                "overdue_reason": entry.get("overdue_reason"),
                "follow_up_plan": entry.get("follow_up_plan"),
                "trust_feedback": entry.get("trust_feedback"),
                "note": entry.get("note"),
                "entry_type": entry.get("entry_type"),
                "entry_id": eid,
                "attachments": entry_attachments,
                "legacy": False,
            }
        )
    events.sort(key=lambda e: str(e.get("occurred_at") or ""), reverse=True)
    return events


def build_overdue_workbench_service(engine: Engine) -> OverdueWorkbenchService:
    return OverdueWorkbenchService(engine)
